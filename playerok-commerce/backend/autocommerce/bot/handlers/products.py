"""📦 Товары: list with category filters and search, product card, pricing
details, price change, publication, competitor observations, codes stock."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from aiogram import F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy.ext.asyncio import AsyncSession

from ...database.enums import COMPLIANCE_LABELS, CONFIDENCE_LABELS, Confidence, DeliveryType, ProductStatus
from ...database.models import ResearchScore, SupplierProduct
from ...services import catalog, inventory, listings, repricing, research
from ...services.audit import Actor
from ...services.pricing import STATUS_LABELS
from ...shared.errors import DomainError
from ...shared.timeutil import fmt_dt
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, empty, esc, kb, money, nav, pager, pct, short

router = make_router("products")
PER_PAGE = 8
GROUPS = [
    ("all", "Все"),
    ("telegram", "Telegram"),
    ("steam", "Steam"),
    ("giftcards", "Карты"),
    ("games", "Игры"),
    ("roblox", "Roblox"),
    ("promotion", "Продвижение"),
    ("subscriptions", "Подписки"),
]
STATUS_ICON = {ProductStatus.ACTIVE: "🟢", ProductStatus.DRAFT: "📝", ProductStatus.PAUSED: "⏸", ProductStatus.ARCHIVED: "🗄"}


async def list_screen(session: AsyncSession, group: str, page: int, query: str = "") -> tuple[str, object]:
    rows, total = await catalog.search_products(
        session, query=query, group=None if group in ("all", "q") else group, page=page, per_page=PER_PAGE
    )
    head = f"📦 <b>Товары</b>{f' · поиск «{esc(query)}»' if query else ''}\n<i>Всего: {total}</i>\n{SEP}"
    if not rows:
        head += "\n" + empty("Товаров нет. Создайте товар из каталога поставщика или вручную.")
    chips = [b(("• " if g == group else "") + label, f"prd:list:{g}:1") for g, label in GROUPS]
    buttons = [
        [b(f"{STATUS_ICON.get(p.status, '•')} {short(p.name, 30)} · {money(p.current_price or p.recommended_price)}", f"prd:open:{p.id}")]
        for p in rows
    ]
    return head, kb(
        chips[:4],
        chips[4:],
        *buttons,
        pager(f"prd:list:{group}", page, total, PER_PAGE),
        [b("🔍 Поиск", "prd:search"), b("➕ Свой товар", "prd:new")],
        [b("🏪 Из каталога поставщика", "sup:list"), b("📤 Экспорт", "prd:export")],
        nav(),
    )


@router.callback_query(F.data.startswith("prd:list:"))
async def product_list(cb: CallbackQuery, session: AsyncSession) -> None:
    _, _, group, page = cb.data.split(":")
    text, markup = await list_screen(session, group, int(page))
    await show(cb, text, markup)


@router.callback_query(F.data == "prd:search")
async def search(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "prd_search", "Введите часть названия или артикула", back="prd:list:all:1")


@on_input("prd_search")
async def search_input(message: Message, ctx: dict) -> None:
    await ctx["state"].clear()
    text, markup = await list_screen(ctx["session"], "q", 1, message.text.strip()[:100])
    await message.answer(text, reply_markup=markup)


async def card(session: AsyncSession, product_id: int) -> tuple[str, object]:
    p = await catalog.get_product(session, product_id)
    result, cost, policy = await repricing.evaluate_product(session, p)
    market, snap = await repricing.market_input(session, p.id)
    score = await session.get(ResearchScore, p.id)
    sp = await session.get(SupplierProduct, p.preferred_supplier_product_id) if p.preferred_supplier_product_id else None
    stock = await inventory.stock(session, p.id) if p.delivery_type is DeliveryType.CODE else None
    compliance = catalog.compliance_of(p)
    lines = [
        f"📦 <b>{esc(p.name)}</b>",
        f"<code>{esc(p.sku)}</code> · {esc(p.category.name)}",
        f"{STATUS_ICON.get(p.status, '•')} {p.status.value} · {COMPLIANCE_LABELS[compliance]}",
        SEP,
    ]
    if sp is not None and sp.price is not None:
        lines.append(
            f"🏪 Цена поставщика: <b>{sp.price.normalize():f} {sp.currency}</b>{' / ' + str(sp.price_unit) + ' шт' if sp.price_unit > 1 else ''} ({esc(sp.supplier.name)})"
        )
    elif p.manual_unit_cost is not None:
        lines.append(f"🏪 Себестоимость (вручную): <b>{money(p.manual_unit_cost)}</b>")
    else:
        lines.append("🏪 Цена поставщика: — (нет источника)")
    if market is not None and market.competitor_min is not None:
        med = f" · медиана {money(market.competitor_median)}" if market.competitor_median else ""
        offers = f" · {market.offers_count} предл." if market.offers_count is not None else ""
        lines.append(f"🏁 Конкуренты: мин {money(market.competitor_min)}{med}{offers} <i>({fmt_dt(market.observed_at)})</i>")
    else:
        lines.append("🏁 Конкуренты: нет наблюдений")
    lines += [
        f"💡 Рекомендуемая цена: <b>{money(result.recommended_price)}</b>",
        f"🔻 Минимальная цена: {money(result.min_price)}",
        f"🏷 Текущая цена: {money(p.current_price)}",
        f"🧮 Полная себестоимость: {money(result.breakdown.full_cost if result.breakdown else None)}",
    ]
    if result.recommended is not None:
        lines.append(f"📈 Чистая прибыль: <b>{money(result.recommended.net_profit)}</b> · маржа {pct(result.recommended.margin_pct)}")
    if score is not None:
        demand = score.factors.get("demand", {})
        comp = score.factors.get("competition", {})
        lines.append(
            f"🔥 Спрос: {esc(demand.get('value') or '—')} <i>({esc(CONFIDENCE_LABELS[Confidence(demand.get('confidence', 'none'))])})</i>"
        )
        lines.append(f"⚔️ Конкуренция: {esc(comp.get('value') or 'нет данных')}")
    if stock is not None:
        lines.append(f"📥 Склад кодов: {stock['available']} свободно · {stock['reserved']} в резерве · {stock['issued']} выдано")
    lines += [
        f"📚 Источник: {esc(cost.source or '—')}",
        f"🕒 Проверка цены: {fmt_dt(cost.price_captured_at)}",
        f"Статус: {STATUS_LABELS.get(result.status, result.status)}",
    ]
    for note in result.notes[:3]:
        lines.append(f"• <i>{esc(note)}</i>")
    toggle = (
        b("⏸ Приостановить", f"prd:status:{p.id}:paused")
        if p.status is ProductStatus.ACTIVE
        else b("▶️ Активировать", f"prd:status:{p.id}:active", style="success")
    )
    rows = [
        [b("🔄 Пересчитать", f"prd:reprice:{p.id}"), b("✏️ Изменить цену", f"prd:price:{p.id}")],
        [b("📝 Опубликовать", f"prd:publish:{p.id}", style="primary"), toggle],
        [b("🏁 Цены конкурентов", f"prd:obs:{p.id}"), b("🧮 Подробный расчёт", f"prd:calc:{p.id}")],
    ]
    second = [b("💸 Себестоимость", f"prd:cost:{p.id}")]
    if p.delivery_type is DeliveryType.CODE:
        second.append(b("📥 Добавить коды", f"prd:codes:{p.id}"))
    rows.append(second)
    rows.append(nav("prd:list:all:1"))
    return "\n".join(lines), kb(*rows)


@router.callback_query(F.data.startswith("prd:open:"))
async def open_product(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await card(session, int(cb.data.split(":")[2]))
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("prd:reprice:"))
async def reprice(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    pid = int(cb.data.split(":")[2])
    product = await catalog.get_product(session, pid)
    result = await repricing.reprice_product(session, product, actor=actor)
    await research.compute(session, product)
    await cb.answer(STATUS_LABELS.get(result.status, result.status)[:190])
    text, markup = await card(session, pid)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("prd:calc:"))
async def calc_details(cb: CallbackQuery, session: AsyncSession) -> None:
    pid = int(cb.data.split(":")[2])
    p = await catalog.get_product(session, pid)
    result, cost, policy = await repricing.evaluate_product(session, p)
    if result.breakdown is None:
        await show(cb, f"🧮 <b>Расчёт</b>\n{SEP}\n" + "\n".join(esc(n) for n in result.notes), kb(nav(f"prd:open:{pid}")))
        return
    br = result.breakdown
    ev = result.recommended
    lines = [
        f"🧮 <b>Расчёт: {esc(short(p.name, 40))}</b>",
        SEP,
        f"Закупка: {money(br.purchase_rub)}"
        + (
            f" ({cost.purchase_price.normalize():f} {cost.purchase_currency} × {cost.fx_rate} ₽)"
            if cost.purchase_currency != "RUB" and cost.purchase_price is not None
            else ""
        ),
        f"Комиссия поставщика: {money(br.supplier_fee_rub)}",
        f"Конвертация валюты ({pct(policy.conversion_fee_pct)}): {money(br.conversion_rub)}",
        f"Прочие расходы: {money(br.other_costs_rub)}",
        f"<b>Полная себестоимость: {money(br.full_cost)}</b>",
        "",
        f"Доля расходов от цены продажи: {pct(br.sale_rate_pct)}",
        f"• комиссия PlayerOK {pct(p.category.marketplace_commission_pct)}, платёжная {pct(policy.payment_fee_pct)}, резерв на возвраты {pct(policy.refund_reserve_pct)}, вывод {pct(policy.withdrawal_fee_pct)} от выплаты",
        "",
        f"Минимальная цена: <b>{money(result.min_price)}</b>",
        f"<i>= наибольшая из: прибыль ≥ {money(policy.min_profit_rub)}, маржа ≥ {pct(policy.min_margin_pct)}, рентабельность ≥ {pct(policy.min_roi_pct)}; с округлением вверх</i>",
        f"Целевая цена: {money(result.target_price)}",
        f"Цена позиционирования: {money(result.competitive_price)}",
    ]
    if ev is not None:
        lines += [
            "",
            f"При цене {money(ev.price)}:",
            f"• комиссия PlayerOK {money(ev.marketplace_fee)} · резерв {money(ev.refund_reserve)} · вывод {money(ev.withdrawal_fee)}",
            f"• валовая прибыль {money(ev.gross_profit)}",
            f"• <b>чистая прибыль {money(ev.net_profit)}</b> · маржа {pct(ev.margin_pct)} · рентабельность {pct(ev.roi_pct)}",
        ]
    lines.append(f"\n<i>Комиссия категории: {esc(p.category.commission_source)}</i>")
    await show(cb, "\n".join(lines), kb(nav(f"prd:open:{pid}")))


@router.callback_query(F.data.startswith("prd:price:"))
async def ask_price(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "pricing.manage")
    pid = int(cb.data.split(":")[2])
    await ask(cb, state, "prd_price", "Новая цена продажи в рублях (например, 1590)", back=f"prd:open:{pid}", product_id=pid)


def parse_money(text: str) -> Decimal:
    try:
        value = Decimal(text.replace(" ", "").replace(",", ".").replace("₽", ""))
    except InvalidOperation as exc:
        raise DomainError("Нужно число, например 1590 или 1590,50") from exc
    if value <= 0 or value > Decimal("10000000"):
        raise DomainError("Сумма должна быть больше нуля")
    return value


@on_input("prd_price")
async def price_input(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    product = await catalog.get_product(session, ctx["product_id"])
    await repricing.apply_price(session, product, parse_money(message.text), actor)
    await ctx["state"].clear()
    text, markup = await card(session, product.id)
    await message.answer("✅ Цена изменена\n\n" + text, reply_markup=markup)


@router.callback_query(F.data.startswith("prd:cost:"))
async def ask_cost(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "products.manage")
    pid = int(cb.data.split(":")[2])
    await ask(
        cb,
        state,
        "prd_cost",
        "Себестоимость одной единицы в рублях (используется, если товар не связан с поставщиком)",
        back=f"prd:open:{pid}",
        product_id=pid,
    )


@on_input("prd_cost")
async def cost_input(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    product = await catalog.get_product(session, ctx["product_id"], lock=True)
    await catalog.update_product(session, product, {"manual_unit_cost": parse_money(message.text)}, actor)
    await repricing.reprice_product(session, product, actor=actor)
    await ctx["state"].clear()
    text, markup = await card(session, product.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.startswith("prd:status:"))
async def set_status(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "products.manage")
    _, _, pid, status = cb.data.split(":")
    product = await catalog.get_product(session, int(pid), lock=True)
    await catalog.set_status(session, product, ProductStatus(status), actor)
    text, markup = await card(session, product.id)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("prd:publish:"))
async def publish(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "listings.manage")
    product = await catalog.get_product(session, int(cb.data.split(":")[2]))
    listing = await listings.create(session, product, actor)
    await listings.prepare(session, listing, actor)
    from .listings import listing_card

    text, markup = await listing_card(session, listing.id)
    await show(cb, "✅ Объявление подготовлено\n\n" + text, markup)


@router.callback_query(F.data.startswith("prd:obs:"))
async def ask_observation(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "pricing.manage")
    pid = int(cb.data.split(":")[2])
    await ask(
        cb,
        state,
        "prd_obs",
        "Цены конкурентов на PlayerOK сейчас: <b>минимальная медиана количество_предложений</b>\nНапример: <code>1790 1850 12</code> (медиану и количество можно не указывать)",
        back=f"prd:open:{pid}",
        product_id=pid,
    )


@on_input("prd_obs")
async def observation_input(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    parts = message.text.replace(",", ".").split()
    if not parts:
        raise DomainError("Введите хотя бы минимальную цену")
    data = {"competitor_min": parse_money(parts[0])}
    if len(parts) > 1:
        data["competitor_median"] = parse_money(parts[1])
    if len(parts) > 2:
        if not parts[2].isdigit():
            raise DomainError("Количество предложений — целое число")
        data["offers_count"] = int(parts[2])
    product = await catalog.get_product(session, ctx["product_id"])
    await research.add_observation(session, product, data, actor)
    await repricing.reprice_product(session, product, actor=actor)
    await research.compute(session, product)
    await ctx["state"].clear()
    text, markup = await card(session, product.id)
    await message.answer("✅ Наблюдение сохранено (дата — сейчас)\n\n" + text, reply_markup=markup)


@router.callback_query(F.data.startswith("prd:codes:"))
async def ask_codes(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "inventory.manage")
    pid = int(cb.data.split(":")[2])
    await ask(
        cb,
        state,
        "prd_codes",
        "Отправьте коды — по одному в строке. Сообщение с кодами будет удалено из чата сразу после сохранения. Повторяющиеся коды не добавляются.",
        back=f"prd:open:{pid}",
        product_id=pid,
    )


@on_input("prd_codes")
async def codes_input(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    codes = [line for line in message.text.splitlines() if line.strip()][:1000]
    product = await catalog.get_product(session, ctx["product_id"])
    result = await inventory.add_codes(session, product, codes, actor)
    try:
        await message.delete()
    except Exception:  # noqa: BLE001 - deletion is best effort
        pass
    await ctx["state"].clear()
    text, markup = await card(session, product.id)
    await message.answer(
        f"📥 Добавлено: <b>{result.added}</b> · дубликатов: {result.duplicates} · отклонено: {result.rejected}\n<i>Коды сохранены в зашифрованном виде.</i>\n\n{text}",
        reply_markup=markup,
    )


@router.callback_query(F.data == "prd:new")
async def new_product(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "products.manage")
    cats = await catalog.list_categories(session)
    rows = [
        [b(f"{'🛑' if c.compliance_status.value in ('blocked', 'no_legal_source') else '•'} {short(c.name, 34)}", f"prd:newcat:{c.code}")]
        for c in cats
    ]
    await show(cb, "➕ <b>Новый товар</b>\nВыберите категорию:", kb(*rows, nav("prd:list:all:1")))


@router.callback_query(F.data.startswith("prd:newcat:"))
async def new_product_category(cb: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    code = cb.data.split(":", 2)[2]
    cat = await catalog.get_category(session, code)
    await ask(
        cb,
        state,
        "prd_new_name",
        f"Категория: <b>{esc(cat.name)}</b>\nНазвание товара (как его увидит покупатель):",
        back="prd:new",
        category_code=code,
    )


@on_input("prd_new_name")
async def new_name_input(message: Message, ctx: dict) -> None:
    await ctx["state"].update_data(kind="prd_new_cost", name=message.text.strip()[:200])
    await message.answer(
        "Себестоимость одной единицы в рублях (сколько вы платите за товар):", reply_markup=kb([b("✖️ Отмена", "cancel:prd:list:all:1")])
    )


@on_input("prd_new_cost")
async def new_cost_input(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    product = await catalog.create_product(
        session, {"name": ctx["name"], "category_code": ctx["category_code"], "manual_unit_cost": parse_money(message.text)}, actor
    )
    await repricing.reprice_product(session, product, actor=actor, notify_owner=False)
    await ctx["state"].clear()
    text, markup = await card(session, product.id)
    await message.answer("✅ Товар создан (черновик)\n\n" + text, reply_markup=markup)


@router.callback_query(F.data == "prd:export")
async def export(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "analytics.export")
    from aiogram.types import BufferedInputFile

    from ...services import exports

    data, name, _ = await exports.products_export(session, "xlsx")
    await cb.message.answer_document(BufferedInputFile(data, filename=name), caption="📤 Товары и расчёт цен")
    await cb.answer()
