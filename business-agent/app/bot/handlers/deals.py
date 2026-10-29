from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from sqlalchemy import select

from app.ai.state import normalize_currency, to_decimal
from app.bot.callbacks import Cb
from app.bot.handlers.common import show
from app.bot.inputs import ask, input_field
from app.bot.ui import STATUS_RU, btn, deal_actions, deal_card, kb, onoff
from app.core.audit import audit
from app.core.owners import get_policy
from app.db.models import ACTIVE_DEAL_STATUSES, Contact, Deal, DealStatus, MarketPrice
from app.deals.manager import DealError
from app.nft.pages import find_gift_links
from app.nft.valuation import attributes_from_page, compare_offer, parse_price_line, valuate
from app.trading.policy import spent_today

router = Router(name="deals")


def _money_or_none(text):
    if text == "-":
        return True, None
    value = to_decimal(text)
    return (value is not None and value > 0), value


def _policy_field(key, prompt, attr, kind="money"):
    @input_field(key, prompt, "deals:policy")
    async def setter(session, owner, text, **_):
        policy = await get_policy(session, owner.id)
        if kind == "money":
            ok, value = _money_or_none(text)
            if not ok:
                return False, "Нужно положительное число или «-»"
        elif kind == "int":
            if not text.isdigit():
                return False, "Нужно целое число"
            value = int(text)
        elif kind == "currency":
            value = None if text == "-" else normalize_currency(text)
            if text != "-" and value is None:
                return False, "Не распознал валюту"
        elif kind == "currencies":
            value = [] if text == "-" else [normalize_currency(c) for c in text.split(",")]
            if None in value:
                return False, "Не распознал валюту"
        elif kind == "list":
            value = [] if text == "-" else [x.strip() for x in text.split(",") if x.strip()]
        elif kind == "ids":
            parts = [] if text == "-" else [x.strip() for x in text.split(",")]
            if not all(p.isdigit() for p in parts):
                return False, "Нужны числовые Telegram ID через запятую"
            value = [int(p) for p in parts]
        setattr(policy, attr, value)
        await audit(session, "policy_changed", owner_id=owner.id, actor="user", field=attr, value=str(value))
        return True, "Сохранено."
    return setter


_policy_field("pol_max_deal", "Максимальная сумма одной сделки («-» — без лимита):", "max_deal_amount")
_policy_field("pol_budget", "Дневной бюджет покупок (обязателен для авто-режима и оплаты через API; «-» — не задан):", "daily_budget")
_policy_field("pol_budget_cur", "Валюта дневного бюджета (например TON):", "budget_currency", "currency")
_policy_field("pol_concurrent", "Максимум одновременных сделок:", "max_concurrent_deals", "int")
_policy_field("pol_auto_max", "Максимальная цена за единицу в авто-режиме:", "auto_max_price")
_policy_field("pol_auto_cur", "Валюты авто-режима через запятую:", "auto_currencies", "currencies")
_policy_field("pol_auto_cat", "Категории товаров авто-режима через запятую (например <code>NFT, подарок</code>; «-» — любые):", "auto_categories", "list")
_policy_field("pol_auto_sellers", "Допустимые продавцы для авто-режима — Telegram ID через запятую («-» — любые):", "auto_allowed_sellers", "ids")
_policy_field("pol_cooldown", "Пауза между повторными покупками у одного продавца, часов:", "repeat_purchase_cooldown_hours", "int")


@input_field("market_price", "Добавьте рыночные данные строками:\n<code>PlushPepe floor 12.5 TON</code>\n"
             "<code>PlushPepe sale 15 TON model=Pumpkin backdrop=Black source=Fragment</code>\n"
             "Только реальные наблюдения — по ним строится оценка.", "deals:nft")
async def market_price(session, owner, text, **_):
    added, bad = 0, []
    for line in text.splitlines():
        if not line.strip():
            continue
        row = parse_price_line(line)
        if row is None:
            bad.append(line)
            continue
        session.add(MarketPrice(owner_id=owner.id, **row))
        added += 1
    if not added:
        return False, "Не распознал ни одной строки"
    await audit(session, "market_prices_added", owner_id=owner.id, actor="user", count=added)
    return True, f"Добавлено: {added}" + (f"\nНе распознано: {escape('; '.join(bad))}" if bad else "")


@input_field("nft_value", "Отправьте ссылку на подарок (<code>t.me/nft/PlushPepe-7</code>), можно с ценой предложения: "
             "<code>t.me/nft/PlushPepe-7 14 TON</code>", "deals:nft")
async def nft_value(session, owner, text, ctx, **_):
    links = find_gift_links(text)
    if not links:
        return False, "Не нашёл ссылку t.me/nft/…"
    slug, number = links[0]
    try:
        page = await ctx.gifts.get(slug, number)
    except ConnectionError as exc:
        return False, f"t.me недоступен: {escape(str(exc))}"
    if page is None:
        return False, "Такого подарка нет"
    rest = text.split(maxsplit=1)[1] if len(text.split(maxsplit=1)) > 1 else ""
    parts = rest.split()
    currency = normalize_currency(parts[1]) if len(parts) > 1 else "TON"
    val = await valuate(session, owner.id, slug, attributes_from_page(page), currency=currency or "TON")
    out = f"💎 <b>{escape(page.title or slug)}</b>\n" + escape(val.render())
    if page.owner_name:
        out += f"\nВладелец (публично): {escape(page.owner_name)}"
    offer = to_decimal(parts[0]) if parts else None
    if offer is not None:
        out += "\n\n" + escape(compare_offer(offer, val))
    out += "\n\nВозможность передачи через торгового бота проверяется самим ботом при сделке."
    return True, out


async def _list(cq, session, owner):
    deals = (await session.scalars(select(Deal).where(Deal.owner_id == owner.id).order_by(Deal.id.desc()).limit(15))).all()
    lines = ["<b>🤝 Управление сделками</b>"]
    rows = [[btn("🚦 Лимиты и авто-режим", "deals", "policy"), btn("💎 Оценка NFT", "deals", "nft")]]
    if not deals:
        lines.append("Сделок пока нет. Агент подготовит сделку, когда условия будут согласованы в переписке.")
    for d in deals:
        mark = "🟡" if d.status in ACTIVE_DEAL_STATUSES else "⚪️"
        lines.append(f"{mark} #{d.id} {d.total.normalize()} {d.currency} — {STATUS_RU.get(DealStatus(d.status), d.status)}")
        rows.append([btn(f"#{d.id} {STATUS_RU.get(DealStatus(d.status), '')}", "deals", "view", d.id)])
    await show(cq, "\n".join(lines), kb(*rows))


async def _policy(cq, session, owner):
    p = await get_policy(session, owner.id)
    spent = await spent_today(session, owner.id, p.budget_currency) if p.budget_currency else None
    text = (
        "<b>🚦 Лимиты и авто-режим</b>\n"
        f"Подтверждение пользователя перед сделкой: {onoff(p.require_user_confirmation)}\n"
        f"Макс. сумма сделки: {p.max_deal_amount or '—'}\n"
        f"Дневной бюджет: {p.daily_budget or '— (не задан)'} {p.budget_currency or ''}"
        + (f" · потрачено сегодня: {spent}" if spent is not None else "") + "\n"
        f"Одновременных сделок: до {p.max_concurrent_deals}\n\n"
        f"<b>Авто-режим создания сделок:</b> {onoff(p.auto_mode_enabled)}\n"
        f"<b>Авто-оплата:</b> {onoff(p.auto_pay_enabled)}\n"
        f"Макс. цена: {p.auto_max_price or '—'}\nВалюты: {', '.join(p.auto_currencies or []) or '—'}\n"
        f"Категории: {escape(', '.join(p.auto_categories or []) or 'любые')}\n"
        f"Продавцы: {', '.join(map(str, p.auto_allowed_sellers or [])) or 'любые'}\n"
        f"Пауза повторной покупки: {p.repeat_purchase_cooldown_hours} ч\n\n"
        "Авто-режим включается только при заданных дневном бюджете, максимальной цене и валютах и при "
        "выключенном подтверждении. Бюджет никогда не превышается; неизвестные платежи учитываются как потраченные."
    )
    await show(cq, text, kb(
        [btn("✋ Подтверждение вкл/выкл", "deals", "pol_confirm")],
        [btn("💰 Макс. сделка", "deals", "f_pol_max_deal"), btn("📅 Дневной бюджет", "deals", "f_pol_budget")],
        [btn("💱 Валюта бюджета", "deals", "f_pol_budget_cur"), btn("🔢 Одновременно", "deals", "f_pol_concurrent")],
        [btn("🤖 Авто-режим вкл/выкл", "deals", "pol_auto"), btn("💸 Авто-оплата вкл/выкл", "deals", "pol_autopay")],
        [btn("🏷 Макс. цена (авто)", "deals", "f_pol_auto_max"), btn("💱 Валюты (авто)", "deals", "f_pol_auto_cur")],
        [btn("📦 Категории", "deals", "f_pol_auto_cat"), btn("👤 Продавцы", "deals", "f_pol_auto_sellers")],
        [btn("⏳ Пауза повтора", "deals", "f_pol_cooldown")],
        back="deals",
    ))


@router.callback_query(Cb.filter(F.s == "deals"))
async def deals(cq: CallbackQuery, callback_data: Cb, state: FSMContext, session, owner, ctx):
    a, i = callback_data.a, callback_data.i
    if a == "show":
        return await _list(cq, session, owner)
    if a.startswith("f_"):
        return await ask(cq, state, a[2:])
    if a in ("policy", "pol_confirm", "pol_auto", "pol_autopay"):
        p = await get_policy(session, owner.id)
        if a == "pol_confirm":
            p.require_user_confirmation = not p.require_user_confirmation
        elif a in ("pol_auto", "pol_autopay"):
            attr = "auto_mode_enabled" if a == "pol_auto" else "auto_pay_enabled"
            turning_on = not getattr(p, attr)
            if turning_on:
                missing = [n for n, v in (("дневной бюджет", p.daily_budget), ("валюта бюджета", p.budget_currency),
                                          ("макс. цена", p.auto_max_price), ("валюты авто-режима", p.auto_currencies)) if not v]
                if missing:
                    return await cq.answer("Сначала задайте: " + ", ".join(missing), show_alert=True)
                if a == "pol_autopay" and not p.auto_mode_enabled:
                    return await cq.answer("Сначала включите авто-режим создания сделок", show_alert=True)
            setattr(p, attr, turning_on)
            if a == "pol_auto" and not turning_on:
                p.auto_pay_enabled = False
            await audit(session, "policy_changed", owner_id=owner.id, actor="user", field=attr, value=str(turning_on))
        return await _policy(cq, session, owner)
    if a == "nft":
        n = len((await session.scalars(select(MarketPrice.id).where(MarketPrice.owner_id == owner.id))).all())
        return await show(cq, f"<b>💎 Оценка NFT и подарков</b>\nРыночных наблюдений в базе: {n}.\n"
                              "Оценка строится только по реальным данным с указанием времени обновления.",
                          kb([btn("🔍 Оценить подарок", "deals", "f_nft_value"), btn("➕ Добавить цены", "deals", "f_market_price")],
                             back="deals"))

    deal = await session.get(Deal, i)
    if deal is None or deal.owner_id != owner.id:
        return await cq.answer("Сделка не найдена", show_alert=True)
    note = ""
    try:
        if a == "confirm":
            step = await ctx.deals.confirm_and_create(session, deal)
            note = step.message + "".join(f"\n• {p}" for p in step.problems)
        elif a == "pay":
            step = await ctx.deals.pay(session, deal)
            note = step.message + "".join(f"\n• {p}" for p in step.problems)
        elif a == "reconcile":
            note = (await ctx.deals.reconcile(session, deal)).message
        elif a == "retry_ask":
            return await show(cq, deal_card(deal, None) + "\n\n⚠️ Сверка не нашла платёж. Повтор будет отправлен с тем же "
                              "spend_id — Crypto Pay примет только один перевод с этим ключом. Повторить?",
                              kb([btn("Да, повторить", "deals", "retry", deal.id), btn("Нет", "deals", "view", deal.id)], back=None))
        elif a == "retry":
            note = (await ctx.deals.retry_payment_same_spend_id(session, deal)).message
        elif a == "cancel":
            note = (await ctx.deals.cancel(session, deal)).message
        elif a == "mark":
            note = (await ctx.deals.mark_manual(session, deal, DealStatus(callback_data.v))).message
    except DealError as exc:
        note = str(exc)
    contact = await session.get(Contact, deal.contact_id) if deal.contact_id else None
    await show(cq, deal_card(deal, contact) + (f"\n\n<i>{escape(note)}</i>" if note else ""), deal_actions(deal))
