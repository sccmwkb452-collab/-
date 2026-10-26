"""📈 Аналитика, 💰 Прибыль и цены, 🔎 Поиск товаров, 📊 Отчёты."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.enums import CONFIDENCE_LABELS, Confidence
from ...services import analytics, app_settings, exports, fx, reports, repricing, research
from ...services.audit import Actor
from ...services.pricing import STATUS_LABELS, CostInput, calculate
from ...shared.errors import DomainError
from ...shared.timeutil import fmt_dt, utcnow
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, empty, esc, kb, money, nav, onoff, pct, short

router = make_router("insights")

PERIOD_BUTTONS = [("today", "Сегодня"), ("yesterday", "Вчера"), ("7d", "7 дней"), ("30d", "30 дней"), ("90d", "90 дней")]


def _dt(value: str | None):
    return datetime.fromisoformat(value) if value else None


async def analytics_screen(session: AsyncSession, code: str, start=None, end=None, include_test: bool = False) -> tuple[str, object]:
    p = analytics.period(code, start, end)
    m = await analytics.metrics(session, p, include_test=include_test)
    totals = await analytics.recorded_totals(session)
    br = await analytics.breakdown(session, p, include_test=include_test)
    sources = ", ".join(f"{k}: {v}" for k, v in totals["deals_by_source"].items()) or "нет"
    lines = [
        f"📈 <b>Аналитика · {esc(p.label)}</b>{' · с тестовыми' if include_test else ''}",
        SEP,
        "📥 <b>Данные в системе</b>",
        f"Сделок: <b>{totals['deals']}</b> · отзывов: <b>{totals['reviews']}</b> · транзакций: <b>{totals['transactions']}</b>",
        f"Источник: ручной ввод и импорт ({esc(sources)}); API PlayerOK нет",
        f"Обновлено: {fmt_dt(_dt(totals['last_update']))}",
        SEP,
        f"🛒 Заказов: <b>{m['orders']}</b> · ✅ завершено: <b>{m['completed']}</b>",
        f"✖️ Отмен: {m['cancelled']} · ↩️ возвратов: {m['refunds']} · ⚖️ споров: {m['disputes']}",
        f"⭐ Отзывов: {m['reviews']}" + (f" · средняя оценка {m['avg_review_rating']}" if m["avg_review_rating"] else ""),
        "",
        f"💰 Выручка: <b>{money(m['revenue'])}</b>",
        f"💸 Закупка: {money(m['purchase_costs'])} · 🏦 комиссии: {money(m['fees'])}",
        f"📈 Чистая прибыль: <b>{money(m['net_profit'])}</b>" + (f" · маржа {pct(m['margin_pct'])}" if m["margin_pct"] else ""),
        f"🧾 Средний чек: {money(m['avg_check'])}",
        f"⏱ Среднее время до выдачи: {m['avg_processing_minutes'] if m['avg_processing_minutes'] is not None else '—'} мин",
    ]
    if m["orders_without_cost"]:
        lines.append(f"⚠️ Сделок без себестоимости: {m['orders_without_cost']} — их прибыль не учтена")
    ops = m["automation_ops"]
    lines += [
        "",
        f"🤖 Автоопераций: {ops['ok']} · подсказок: {ops['suggested']} · пропусков: {ops['skipped']} · ошибок: {ops['error']}",
        f"📦 Авто-готовность к выдаче: {m['auto_ready_share']} %"
        if m["auto_ready_share"] is not None
        else "📦 Авто-готовность к выдаче: нет данных",
        f"🛠 Ошибок интеграций: {m['integration_errors']}",
        f"👁 Конверсия: нет данных — {esc(m['conversion_note'])}",
    ]
    if br["top_profit"]:
        lines.append("\n🏆 <b>Топ по прибыли</b>")
        lines += [
            f"• {esc(short(x['name'], 30))}: {money(x['profit_before_withdrawal'])} ({x['quantity']} шт)" for x in br["top_profit"][:5]
        ]
    if br["categories"]:
        lines.append("\n🗂 <b>По категориям</b>")
        lines += [f"• {esc(short(c['category'], 28))}: {money(c['revenue'])} · {c['quantity']} шт" for c in br["categories"][:6]]
    chips = [b(("• " if c == code else "") + label, f"ana:{c}") for c, label in PERIOD_BUTTONS]
    return "\n".join(lines), kb(
        chips[:3],
        chips[3:] + [b("📅 Период…", "ana:custom")],
        [b("🏪 Поставщики", f"anaS:{code}"), b("🔄 Синхронизация", "ana:sync")],
        [
            b("📤 Excel", f"anaX:{code}:xlsx"),
            b("📄 CSV", f"anaX:{code}:csv"),
            b("🧪 Тестовые: " + ("да" if include_test else "нет"), f"anaT:{code}:{'0' if include_test else '1'}"),
        ],
        nav(),
    )


@router.callback_query(F.data.regexp(r"^ana:(today|yesterday|7d|30d|90d)$"))
async def analytics_view(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await analytics_screen(session, cb.data.split(":")[1])
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("anaT:"))
async def analytics_test_toggle(cb: CallbackQuery, session: AsyncSession) -> None:
    _, code, flag = cb.data.split(":")
    text, markup = await analytics_screen(session, code, include_test=flag == "1")
    await show(cb, text, markup)


@router.callback_query(F.data == "ana:custom")
async def custom(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "ana_custom", "Период в формате <code>01.10.2026-25.10.2026</code>", back="ana:30d")


@on_input("ana_custom")
async def custom_input(message: Message, ctx: dict) -> None:
    try:
        a, _, z = message.text.replace(" ", "").partition("-")
        start = datetime.strptime(a, "%d.%m.%Y").date()
        end = datetime.strptime(z, "%d.%m.%Y").date()
    except ValueError as exc:
        raise DomainError("Формат: 01.10.2026-25.10.2026") from exc
    await ctx["state"].clear()
    text, markup = await analytics_screen(ctx["session"], "custom", start, end)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("anaX:"))
async def export(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "analytics.export")
    _, code, fmt = cb.data.split(":")
    data, name, _ = await exports.analytics_export(session, analytics.period(code), fmt)
    await cb.message.answer_document(BufferedInputFile(data, filename=name), caption=f"📤 Аналитика: {analytics.PERIODS.get(code, code)}")
    await cb.answer()


@router.callback_query(F.data.startswith("anaS:"))
async def suppliers_view(cb: CallbackQuery, session: AsyncSession) -> None:
    code = cb.data.split(":")[1]
    br = await analytics.breakdown(session, analytics.period(code))
    lines = ["🏪 <b>Эффективность поставщиков</b>", SEP]
    if not br["suppliers"]:
        lines.append(empty("Закупок за период не было"))
    for s in br["suppliers"]:
        lines.append(
            f"<b>{esc(s['supplier'])}</b>: {s['orders']} закупок · успешно {s['succeeded']} · ошибок {s['failed']} · {money(s['spend_rub'])}"
        )
    await show(cb, "\n".join(lines), kb(nav(f"ana:{code}")))


@router.callback_query(F.data == "ana:sync")
async def sync_view(cb: CallbackQuery, session: AsyncSession) -> None:
    rows = await analytics.sync_overview(session)
    icons = {"succeeded": "🟢", "failed": "🔴", "partial": "🟡", "running": "⏳", "unavailable": "⚪️"}
    lines = ["🔄 <b>Статус синхронизации</b>", SEP]
    for r in rows:
        lines.append(
            f"{icons.get(r['status'], '•')} <b>{esc(r['source'])}</b> ({esc(r['kind'])}): получено {r['received']}, сохранено {r['saved']}, ошибок {r['errors']}"
        )
        lines.append(f"   {fmt_dt(_dt(r['finished_at'] or r['started_at']))} · <i>{esc(short(r['message'], 120))}</i>")
    await show(cb, "\n".join(lines), kb([b("💱 Обновить курсы ЦБ", "prc:fxsync")], nav("ana:30d")))


# --- 💰 Прибыль и цены --------------------------------------------------------------

FIELD_LABELS = {
    "min_profit_rub": ("Минимальная чистая прибыль", "₽"),
    "min_margin_pct": ("Минимальная маржинальность", "%"),
    "min_roi_pct": ("Минимальная рентабельность", "%"),
    "refund_reserve_pct": ("Резерв на возвраты", "% от цены"),
    "target_profit_rub": ("Целевая прибыль", "₽"),
    "target_margin_pct": ("Целевая маржинальность", "%"),
    "max_market_deviation_pct": ("Допустимое отклонение от рынка", "%"),
    "max_discount_pct": ("Максимальная скидка", "%"),
    "max_purchase_budget_rub": ("Бюджет автозакупок в сутки", "₽"),
    "max_price_age_minutes": ("Допустимый возраст цены поставщика", "мин"),
    "max_market_age_hours": ("Возраст данных о конкурентах", "ч"),
    "payment_fee_pct": ("Платёжная комиссия", "% от цены"),
    "withdrawal_fee_pct": ("Комиссия вывода", "% от выплаты"),
    "conversion_fee_pct": ("Стоимость конвертации валюты", "%"),
    "other_costs_rub": ("Прочие расходы на единицу", "₽"),
    "price_step": ("Шаг цены", "₽"),
    "undercut_rub": ("Шаг ниже конкурента", "₽"),
}


@router.callback_query(F.data == "prc:home")
async def pricing_home(cb: CallbackQuery, session: AsyncSession) -> None:
    policy = await repricing.global_policy(session)
    values = policy.to_values()
    lines = ["💰 <b>Прибыль и цены</b>", "<i>Общие правила. Для категорий и товаров — переопределения в веб-панели.</i>", SEP]
    for key, (label, unit) in FIELD_LABELS.items():
        v = values.get(key)
        lines.append(f"{label}: <b>{esc(v if v is not None else 'не задано')}</b> {unit if v is not None else ''}")
    lines.append("\n🛡 Цена ниже минимальной не применяется; при устаревшей цене поставщика публикация и изменение цены останавливаются.")
    buttons = [b(short(label, 30), f"prc:edit:{key}") for key, (label, _) in FIELD_LABELS.items()]
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    await show(cb, "\n".join(lines), kb([b("🧮 Калькулятор", "prc:calc", style="primary"), b("💱 Курсы ЦБ", "prc:fx")], *rows, nav()))


@router.callback_query(F.data.startswith("prc:edit:"))
async def edit_field(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "pricing.manage")
    key = cb.data.split(":")[2]
    label, unit = FIELD_LABELS[key]
    await ask(
        cb, state, "prc_value", f"{label}, {unit}. Новое значение (число; «-» — сбросить целевую прибыль):", back="prc:home", field=key
    )


@on_input("prc_value")
async def value_input(message: Message, ctx: dict) -> None:
    raw = message.text.strip().replace(",", ".")
    value = None if raw == "-" else raw
    if value is not None:
        try:
            Decimal(value)
        except Exception as exc:
            raise DomainError("Нужно число") from exc
    try:
        await repricing.save_rule(ctx["session"], "global", {ctx["field"]: value}, ctx["actor"])
    except ValueError as exc:
        raise DomainError(str(exc)) from exc
    from ...services import jobs

    await jobs.enqueue(ctx["session"], "products.reprice_all", {}, dedupe_key="reprice_all")
    await ctx["state"].clear()
    await message.answer(
        "✅ Сохранено. Цены всех товаров пересчитываются в фоне.", reply_markup=kb([b("💰 Прибыль и цены", "prc:home")], nav())
    )


@router.callback_query(F.data == "prc:calc")
async def calc(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(
        cb,
        state,
        "prc_calc",
        "Калькулятор минимальной цены. Введите: <b>закупка валюта комиссия_площадки%</b>\nНапример: <code>15 USD 10</code> или <code>900 RUB 20</code>. Можно добавить цену продажи: <code>15 USD 10 1700</code>",
        back="prc:home",
    )


@on_input("prc_calc")
async def calc_input(message: Message, ctx: dict) -> None:
    parts = message.text.replace(",", ".").split()
    if len(parts) < 3:
        raise DomainError("Нужно минимум три значения: закупка, валюта, комиссия")
    try:
        purchase, currency, commission = Decimal(parts[0]), parts[1].upper(), Decimal(parts[2].rstrip("%"))
        sale = Decimal(parts[3]) if len(parts) > 3 else None
    except Exception as exc:
        raise DomainError("Проверьте числа: например 15 USD 10 1700") from exc
    session = ctx["session"]
    policy = await repricing.global_policy(session)
    rate = await fx.latest_rate(session, currency)
    result = calculate(
        CostInput(purchase, currency, rate[0] if rate else None, marketplace_commission_pct=commission, price_captured_at=utcnow()),
        policy,
        current_price=sale,
    )
    lines = ["🧮 <b>Расчёт</b>", SEP, STATUS_LABELS.get(result.status, result.status)]
    if result.breakdown:
        lines += [
            f"Курс: {rate[0] if rate else '—'} ₽ ({fmt_dt(rate[1]) if rate and rate[1] else 'RUB'})",
            f"Полная себестоимость: <b>{money(result.breakdown.full_cost)}</b>",
            f"Доля расходов от цены: {pct(result.breakdown.sale_rate_pct)}",
            f"🔻 Минимальная цена: <b>{money(result.min_price)}</b>",
            f"🎯 Целевая цена: {money(result.target_price)}",
        ]
        if result.recommended:
            lines.append(f"При целевой: прибыль {money(result.recommended.net_profit)} · маржа {pct(result.recommended.margin_pct)}")
        if result.current:
            c = result.current
            lines.append(
                f"\nПри цене {money(c.price)}: прибыль <b>{money(c.net_profit)}</b> · маржа {pct(c.margin_pct)} · рентабельность {pct(c.roi_pct)}"
            )
            if c.violations:
                lines += [f"⚠️ {esc(v)}" for v in c.violations]
    lines += [f"• <i>{esc(n)}</i>" for n in result.notes]
    await ctx["state"].clear()
    await message.answer("\n".join(lines), reply_markup=kb([b("🧮 Ещё расчёт", "prc:calc")], nav("prc:home")))


@router.callback_query(F.data == "prc:fx")
async def fx_view(cb: CallbackQuery, session: AsyncSession) -> None:
    rates = await fx.rates_overview(session)
    lines = ["💱 <b>Курсы ЦБ РФ</b>", SEP]
    lines += [f"{r['currency']}: <b>{r['rate']}</b> ₽ ({r['date'][:10] if r['date'] else ''})" for r in rates] or [
        empty("Курсы ещё не загружены")
    ]
    lines.append("\n<i>Источник: cbr.ru/scripts/XML_daily.asp. Обновляются каждые 6 часов.</i>")
    await show(cb, "\n".join(lines), kb([b("🔄 Обновить сейчас", "prc:fxsync")], nav("prc:home")))


@router.callback_query(F.data == "prc:fxsync")
async def fx_sync(cb: CallbackQuery, session: AsyncSession) -> None:
    run = await fx.sync_cbr(session)
    await cb.answer(run.message[:190], show_alert=run.status.value != "succeeded")
    await fx_view(cb, session)


# --- 🔎 Поиск товаров (Market Research) ----------------------------------------------


@router.callback_query(F.data == "res:home")
async def research_home(cb: CallbackQuery, session: AsyncSession) -> None:
    rows, total = await research.ranking(session, limit=10)
    lines = [
        "🔎 <b>Поиск выгодных товаров</b>",
        "<i>Рейтинг ваших товаров. Спрос подтверждается только своими продажами; число предложений конкурентов — косвенный признак, не продажи.</i>",
        SEP,
    ]
    if not rows:
        lines.append(empty("Рейтинг пуст: создайте товары и нажмите «Пересчитать»"))
    for i, (p, s) in enumerate(rows, 1):
        lines.append(f"{i}. <b>{esc(short(p.name, 34))}</b> — {s.total_score:.0f}/100 · достоверность: {CONFIDENCE_LABELS[s.confidence]}")
    buttons = [[b(f"{i}. {short(p.name, 30)}", f"res:item:{p.id}")] for i, (p, _) in enumerate(rows, 1)]
    await show(
        cb,
        "\n".join(lines),
        kb(*buttons, [b("🔄 Пересчитать", "res:recompute"), b("🏪 Позиции поставщиков", "res:opp:1")], nav()),
    )


@router.callback_query(F.data == "res:recompute")
async def recompute(cb: CallbackQuery, session: AsyncSession) -> None:
    n = await research.recompute_all(session)
    await cb.answer(f"Пересчитано товаров: {n}")
    await research_home(cb, session)


FACTOR_LABELS = {
    "demand": "🔥 Спрос",
    "margin": "💰 Маржа",
    "turnover": "🔁 Оборот капитала",
    "competition": "⚔️ Конкуренция",
    "supplier_stability": "📉 Стабильность закупочной цены",
    "dispute_risk": "⚖️ Риск возврата или спора",
    "supplier_reliability": "🏪 Надёжность поставщика",
    "freshness": "🕒 Свежесть данных",
    "auto_delivery": "🤖 Автоматическая выдача",
    "restrictions": "🛡 Ограничения",
}


@router.callback_query(F.data.startswith("res:item:"))
async def research_item(cb: CallbackQuery, session: AsyncSession) -> None:
    from ...database.models import ResearchScore
    from ...services import catalog

    pid = int(cb.data.split(":")[2])
    product = await catalog.get_product(session, pid)
    score = await session.get(ResearchScore, pid) or await research.compute(session, product)
    lines = [
        f"🔎 <b>{esc(product.name)}</b>",
        f"Итог: <b>{score.total_score:.0f}/100</b> · достоверность: {CONFIDENCE_LABELS[score.confidence]}",
        SEP,
    ]
    if score.excluded_reason:
        lines.append(f"🛑 {esc(score.excluded_reason)}")
    for key, label in FACTOR_LABELS.items():
        f = score.factors.get(key)
        if not f:
            continue
        val = f"{f['score']:.0f}/100 · " if f.get("score") is not None else ""
        conf = (
            CONFIDENCE_LABELS[Confidence(f["confidence"])]
            if f.get("confidence") in Confidence._value2member_map_
            else f.get("confidence_label", "")
        )
        lines.append(f"{label}: {val}{esc(f.get('value') or 'нет данных')}")
        lines.append(f"   <i>{esc(f.get('basis'))} · {esc(conf)}{(' · ' + fmt_dt(_dt(f['at']))) if f.get('at') else ''}</i>")
    lines.append(f"\nРассчитано: {fmt_dt(score.computed_at)}")
    await show(
        cb, "\n".join(lines), kb([b("📦 Карточка товара", f"prd:open:{pid}"), b("🏁 Цены конкурентов", f"prd:obs:{pid}")], nav("res:home"))
    )


@router.callback_query(F.data.startswith("res:opp:"))
async def opportunities(cb: CallbackQuery, session: AsyncSession) -> None:
    page = int(cb.data.split(":")[2])
    items, total = await research.supplier_opportunities(session, limit=8, offset=(page - 1) * 8)
    lines = [
        "🏪 <b>Позиции поставщиков без товара</b>",
        "<i>Себестоимость и минимальная цена PlayerOK по правилам прибыли. Сравните с ценами на PlayerOK и создайте товар.</i>",
        SEP,
    ]
    if not items:
        lines.append(empty("Нет данных: синхронизируйте поставщиков (раздел «Поставщики»)"))
    for x in items:
        lines.append(f"• <b>{esc(short(x['name'], 40))}</b> ({esc(x['supplier'])})")
        lines.append(f"   закупка {money(x['cost_rub'])} → мин. цена <b>{money(x['min_price'])}</b> · {esc(x['compliance'])}")
    from ..ui import pager

    buttons = [[b(f"➕ {short(x['name'], 32)}", f"sup:item:{x['id']}")] for x in items]
    await show(cb, "\n".join(lines), kb(*buttons, pager("res:opp", page, total, 8), nav("res:home")))


# --- 📊 Отчёты ------------------------------------------------------------------------


@router.callback_query(F.data == "rep:home")
async def reports_home(cb: CallbackQuery, session: AsyncSession) -> None:
    daily = await app_settings.get_setting(session, "reports.daily")
    weekly = await app_settings.get_setting(session, "reports.weekly")
    lines = [
        "📊 <b>Отчёты</b>",
        SEP,
        f"Ежедневный (за вчера): {onoff(daily['enabled'])} · в {daily['hour']}:00",
        f"Еженедельный: {onoff(weekly['enabled'])} · день {weekly['weekday']} в {weekly['hour']}:00",
        "<i>Отчёты приходят в Telegram всем, у кого есть доступ.</i>",
    ]
    await show(
        cb,
        "\n".join(lines),
        kb(
            [b("📅 Сводка за вчера", "rep:show:yesterday"), b("🗓 Сводка за 7 дней", "rep:show:7d")],
            [b(f"Ежедневный: {'выкл' if daily['enabled'] else 'вкл'}", "rep:toggle:daily"), b("🕘 Час отчёта", "rep:hour")],
            [b(f"Еженедельный: {'выкл' if weekly['enabled'] else 'вкл'}", "rep:toggle:weekly")],
            [b("📤 Excel за 30 дней", "anaX:30d:xlsx"), b("📤 Товары", "prd:export")],
            nav(),
        ),
    )


@router.callback_query(F.data.startswith("rep:show:"))
async def show_report(cb: CallbackQuery, session: AsyncSession) -> None:
    code = cb.data.split(":")[2]
    await show(cb, "📊 <b>Сводка</b>\n" + await reports.summary_text(session, code), kb(nav("rep:home")))


@router.callback_query(F.data.startswith("rep:toggle:"))
async def toggle_report(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "settings.manage")
    key = f"reports.{cb.data.split(':')[2]}"
    value = await app_settings.get_setting(session, key)
    value["enabled"] = not value["enabled"]
    await app_settings.set_setting(session, key, value, actor)
    await reports_home(cb, session)


@router.callback_query(F.data == "rep:hour")
async def report_hour(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "settings.manage")
    await ask(cb, state, "rep_hour", "Час отправки ежедневного отчёта (0–23, по часовому поясу магазина)", back="rep:home")


@on_input("rep_hour")
async def report_hour_input(message: Message, ctx: dict) -> None:
    if not message.text.strip().isdigit():
        raise DomainError("Нужно число от 0 до 23")
    value = await app_settings.get_setting(ctx["session"], "reports.daily")
    value["hour"] = int(message.text.strip())
    await app_settings.set_setting(ctx["session"], "reports.daily", value, ctx["actor"])
    await ctx["state"].clear()
    await message.answer("✅ Сохранено", reply_markup=kb([b("📊 Отчёты", "rep:home")], nav()))
