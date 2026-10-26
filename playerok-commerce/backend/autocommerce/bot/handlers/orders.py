"""🛒 Заказы: filters, search, order card with every operator action, new
order wizard, code reveal with auto-deletion."""

from __future__ import annotations

import asyncio
import logging
import re
from decimal import Decimal

from aiogram import Bot, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ...config import get_settings
from ...database.enums import ORDER_STATUS_LABELS, DeliveryType, OrderStatus, ProductStatus
from ...database.models import Order, OrderEvent
from ...services import catalog, inventory, orders, suppliers
from ...services.audit import Actor
from ...shared.errors import DomainError
from ...shared.timeutil import fmt_dt
from ..core import ask, make_router, on_input, require, show
from ..ui import SEP, b, confirm, empty, esc, kb, money, nav, pager, short
from .products import parse_money

router = make_router("orders")
log = logging.getLogger(__name__)
PER_PAGE = 8
S = OrderStatus
FILTERS = [
    ("attention", "⚠️ Требуют внимания"),
    ("new", "🆕 Новые"),
    ("pending_purchase", "🛒 Ждут закупки"),
    ("pending_confirmation", "✋ Ждут подтверждения"),
    ("ready_for_delivery", "📦 Готовы к выдаче"),
    ("delivered", "📤 Выданы"),
    ("completed", "✅ Завершены"),
    ("all", "📋 Все"),
]


@router.callback_query(F.data == "ord:home")
async def home(cb: CallbackQuery, session: AsyncSession) -> None:
    counts = dict((await session.execute(select(Order.status, func.count()).group_by(Order.status))).all())
    attention = (await session.execute(select(func.count()).where(Order.needs_attention.is_(True)))).scalar_one()
    lines = ["🛒 <b>Заказы</b>", SEP]
    if counts:
        lines += [f"{ORDER_STATUS_LABELS[s]}: <b>{c}</b>" for s, c in sorted(counts.items(), key=lambda x: list(S).index(x[0]))]
    else:
        lines.append(empty("Заказов пока нет. PlayerOK без API: внесите сделку кнопкой «Новый заказ» или импортируйте CSV в веб-панели."))
    rows = []
    for i in range(0, len(FILTERS), 2):
        rows.append(
            [
                b(label + (f" ({attention})" if code == "attention" and attention else ""), f"ord:list:{code}:1")
                for code, label in FILTERS[i : i + 2]
            ]
        )
    await show(cb, "\n".join(lines), kb(*rows, [b("➕ Новый заказ", "ord:new", style="primary"), b("🔍 Поиск", "ord:search")], nav()))


@router.callback_query(F.data.startswith("ord:list:"))
async def order_list(cb: CallbackQuery, session: AsyncSession) -> None:
    _, _, flt, page = cb.data.split(":")
    page_n = int(page)
    rows, total = await orders.list_orders(
        session,
        status=None if flt in ("all", "attention") else flt,
        attention=flt == "attention",
        page=page_n,
        per_page=PER_PAGE,
    )
    label = dict(FILTERS).get(flt, ORDER_STATUS_LABELS.get(S(flt), flt) if flt in S._value2member_map_ else flt)
    text = f"🛒 <b>{esc(label)}</b> · {total}\n{SEP}" + ("" if rows else "\n" + empty("Здесь пусто"))
    buttons = [
        [
            b(
                f"{ORDER_STATUS_LABELS[o.status].split()[0]} {o.number}{' 🧪' if o.is_test else ''} · {money(o.total_amount)} · {short(o.buyer_name or '—', 14)}",
                f"ord:open:{o.id}",
            )
        ]
        for o in rows
    ]
    await show(cb, text, kb(*buttons, pager(f"ord:list:{flt}", page_n, total, PER_PAGE), nav("ord:home")))


@router.callback_query(F.data == "ord:search")
async def search(cb: CallbackQuery, state: FSMContext) -> None:
    await ask(cb, state, "ord_search", "Номер заказа (PO-000123), номер сделки PlayerOK или ник покупателя", back="ord:home")


@on_input("ord_search")
async def search_input(message: Message, ctx: dict) -> None:
    await ctx["state"].clear()
    rows, total = await orders.list_orders(ctx["session"], query=message.text.strip()[:100], per_page=10)
    if len(rows) == 1:
        text, markup = await order_card(ctx["session"], rows[0].id)
        await message.answer(text, reply_markup=markup)
        return
    buttons = [[b(f"{ORDER_STATUS_LABELS[o.status].split()[0]} {o.number} · {money(o.total_amount)}", f"ord:open:{o.id}")] for o in rows]
    await message.answer(f"🔍 Найдено: {total}" + ("" if rows else "\n" + empty("ничего")), reply_markup=kb(*buttons, nav("ord:home")))


async def order_card(session: AsyncSession, order_id: int) -> tuple[str, object]:
    o = await orders.get_order(session, order_id)
    lines = [
        f"🛒 <b>Заказ {o.number}</b>{' 🧪 тест' if o.is_test else ''}",
        f"Сделка PlayerOK: <code>{esc(o.external_id)}</code> · {esc(o.source)}",
        f"Покупатель: {esc(o.buyer_name or '—')}",
        f"Статус: <b>{ORDER_STATUS_LABELS[o.status]}</b>",
    ]
    if o.status_reason:
        lines.append(f"<i>{esc(short(o.status_reason, 400))}</i>")
    if o.automation_paused:
        lines.append("⏸ Автоматизация по заказу приостановлена")
    lines.append(SEP)
    code_buttons = []
    for item in o.items:
        lines.append(f"• {esc(item.product.name)} × {item.quantity} — {money(item.unit_price)}")
        codes = await inventory.assigned(session, item.id)
        for c in codes:
            lines.append(f"   🔑 {esc(c.code_mask)} ({c.status.value}{', тест' if c.is_test else ''})")
            code_buttons.append(b(f"👁 Код {c.code_mask[-4:]}", f"code:show:{c.id}"))
        so = await suppliers.latest_for_item(session, item.id)
        if so is not None:
            lines.append(f"   🏪 Закупка: {so.status.value}{' (тест)' if so.is_test else ''} · {money(so.cost_rub)}")
    data = {k: v for k, v in (o.buyer_data or {}).items() if not k.startswith("_")}
    if data:
        lines.append("Данные покупателя: " + ", ".join(f"{esc(k)}: <code>{esc(v)}</code>" for k, v in data.items()))
    lines += [SEP, f"💰 Сумма: <b>{money(o.total_amount)}</b>"]
    if o.status is S.COMPLETED:
        lines.append(f"Комиссия: {money(o.marketplace_fee)} · себестоимость: {money(o.cost_total)}")
        lines.append(f"📈 Чистая прибыль: <b>{money(o.net_profit) if o.net_profit is not None else 'нет себестоимости'}</b>")
    lines.append(f"🕒 {fmt_dt(o.placed_at)}")
    events = (
        (await session.execute(select(OrderEvent).where(OrderEvent.order_id == o.id).order_by(OrderEvent.id.desc()).limit(4)))
        .scalars()
        .all()
    )
    if events:
        lines.append("\n<b>История</b>")
        lines += [f"• {fmt_dt(e.created_at)} — {esc(short(e.message, 70))} ({esc(e.actor)})" for e in events]
    if o.notes:
        lines.append(f"\n📝 {esc(short(o.notes, 300))}")

    rows: list[list] = []
    oid = o.id
    if o.status is S.PENDING_REVIEW:
        rows.append([b("▶️ Продолжить", f"ord:continue:{oid}", style="success"), b("✖️ Отменить", f"ord:cancel:{oid}")])
    if o.status is S.PENDING_CONFIRMATION:
        rows.append([b("✅ Закупить", f"ord:buy:{oid}", style="success"), b("🛒 Куплю вручную", f"ord:manual:{oid}")])
    if o.status is S.PENDING_PURCHASE:
        row = [b("✅ Закуплено вручную", f"ord:bought:{oid}", style="success")]
        if any(i.product.delivery_type is DeliveryType.CODE for i in o.items):
            row.append(b("📥 Добавить коды", f"ord:codes:{oid}"))
        rows.append(row)
    if o.status is S.PROCESSING:
        rows.append([b("🔄 Проверить у поставщика", f"ord:poll:{oid}")])
    if o.status is S.ERROR:
        rows.append([b("🔁 Повторить", f"ord:retry:{oid}", style="primary"), b("▶️ Продолжить вручную", f"ord:continue:{oid}")])
    if code_buttons:
        rows += [code_buttons[i : i + 2] for i in range(0, min(len(code_buttons), 6), 2)]
    if o.status in (S.READY_FOR_DELIVERY, S.DISPUTE) and o.status is not S.DELIVERED:
        rows.append([b("📤 Выдано покупателю", f"ord:delivered:{oid}", style="success")])
    if o.status in (S.DELIVERED, S.DISPUTE):
        rows.append([b("✅ Покупатель подтвердил", f"ord:confirmed:{oid}", style="success")])
    if o.status not in orders.FINAL:
        rows.append([b("⚖️ Спор", f"ord:dispute:{oid}"), b("↩️ Возврат", f"ord:refund:{oid}", style="danger")])
        rows.append(
            [
                b(
                    "▶️ Возобновить автоматизацию" if o.automation_paused else "⏸ Пауза автоматизации",
                    f"ord:{'resume' if o.automation_paused else 'pause'}:{oid}",
                ),
                b("🔀 Статус", f"ord:st:{oid}"),
            ]
        )
    elif o.status is S.COMPLETED:
        rows.append([b("↩️ Возврат", f"ord:refund:{oid}", style="danger"), b("⚖️ Спор", f"ord:dispute:{oid}")])
    rows.append([b("💬 Сообщение", f"msg:new:{oid}"), b("⭐ Отзыв", f"msg:review:{oid}"), b("📝 Заметка", f"ord:note:{oid}")])
    if o.items and o.items[0].listing_id:
        rows.append([b("📝 Объявление", f"lst:open:{o.items[0].listing_id}")])
    rows.append([b("🔄 Обновить", f"ord:open:{oid}")] + nav("ord:home"))
    return "\n".join(lines), kb(*rows)


@router.callback_query(F.data.startswith("ord:open:"))
async def open_order(cb: CallbackQuery, session: AsyncSession) -> None:
    text, markup = await order_card(session, int(cb.data.split(":")[2]))
    await show(cb, text, markup)


SIMPLE = {
    "continue": orders.continue_after_review,
    "retry": orders.retry,
    "buy": orders.confirm_purchase,
    "manual": orders.choose_manual_purchase,
    "delivered": orders.mark_delivered,
    "confirmed": orders.mark_buyer_confirmed,
}
TOASTS = {
    "continue": "Обработка продолжена",
    "retry": "Повторная обработка",
    "buy": "Закупка подтверждена",
    "manual": "Отмечено: закупка вручную",
    "delivered": "Отмечено как выданное",
    "confirmed": "Сделка завершена",
}


@router.callback_query(F.data.regexp(r"^ord:(continue|retry|buy|manual|delivered|confirmed):\d+$"))
async def simple_action(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    _, action, oid = cb.data.split(":")
    require(actor, "suppliers.purchase" if action == "buy" else "orders.manage")
    order = await orders.get_order(session, int(oid), lock=True)
    await SIMPLE[action](session, order, actor)
    await cb.answer(TOASTS[action])
    text, markup = await order_card(session, int(oid))
    await show(cb, text, markup)


@router.callback_query(F.data.regexp(r"^ord:(pause|resume):\d+$"))
async def pause(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "orders.manage")
    _, action, oid = cb.data.split(":")
    order = await orders.get_order(session, int(oid), lock=True)
    await orders.pause_automation(session, order, action == "pause", actor)
    text, markup = await order_card(session, int(oid))
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("ord:poll:"))
async def poll(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    oid = int(cb.data.split(":")[2])
    await orders.poll(session, oid)
    text, markup = await order_card(session, oid)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("ord:bought:"))
async def bought(cb: CallbackQuery, state: FSMContext, session: AsyncSession, actor: Actor) -> None:
    require(actor, "orders.manage")
    oid = int(cb.data.split(":")[2])
    order = await orders.get_order(session, oid)
    estimate = None
    for item in order.items:
        try:
            plan = await suppliers.plan_purchase(session, item)
            estimate = (estimate or Decimal(0)) + (plan.cost_rub or Decimal(0))
        except suppliers.ManualPurchaseRequired:
            if item.product.manual_unit_cost is not None:
                estimate = (estimate or Decimal(0)) + item.product.manual_unit_cost * item.quantity
    hint = f"\nОценка по данным поставщика: <b>{money(estimate)}</b> — отправьте «+», чтобы принять." if estimate else ""
    await ask(
        cb,
        state,
        "ord_bought",
        f"Сколько вы фактически заплатили за закупку, ₽?{hint}",
        back=f"ord:open:{oid}",
        order_id=oid,
        estimate=str(estimate) if estimate else None,
    )


@on_input("ord_bought")
async def bought_input(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    text = message.text.strip()
    cost = Decimal(ctx["estimate"]) if text == "+" and ctx.get("estimate") else parse_money(text)
    order = await orders.get_order(session, ctx["order_id"], lock=True)
    await orders.mark_purchased(session, order, actor, cost_rub=cost)
    await ctx["state"].clear()
    card_text, markup = await order_card(session, order.id)
    await message.answer(card_text, reply_markup=markup)


@router.callback_query(F.data.startswith("ord:codes:"))
async def codes(cb: CallbackQuery, state: FSMContext, session: AsyncSession, actor: Actor) -> None:
    require(actor, "inventory.manage")
    oid = int(cb.data.split(":")[2])
    order = await orders.get_order(session, oid)
    item = next((i for i in order.items if i.product.delivery_type is DeliveryType.CODE), None)
    if item is None:
        raise DomainError("В заказе нет товаров с кодами")
    await ask(
        cb,
        state,
        "ord_codes",
        f"Коды для «{esc(item.product.name)}» × {item.quantity} — по одному в строке. Последней строкой можно указать себестоимость одного кода: <code>цена 450</code>. Сообщение будет удалено после сохранения.",
        back=f"ord:open:{oid}",
        order_id=oid,
        item_id=item.id,
    )


@on_input("ord_codes")
async def codes_input(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    lines = [x.strip() for x in message.text.splitlines() if x.strip()]
    unit_cost = None
    if lines and re.match(r"^цена\s+[\d\s.,]+$", lines[-1], re.IGNORECASE):
        unit_cost = parse_money(lines.pop().split(None, 1)[1])
    try:
        await message.delete()
    except Exception:  # noqa: BLE001
        pass
    order = await orders.get_order(session, ctx["order_id"], lock=True)
    result = await orders.add_codes(session, order, ctx["item_id"], lines, actor, unit_cost=unit_cost)
    await ctx["state"].clear()
    text, markup = await order_card(session, order.id)
    await message.answer(
        f"📥 Добавлено: {result['added']} · дубликатов: {result['duplicates']} · отклонено: {result['rejected']}\n\n{text}",
        reply_markup=markup,
    )


@router.callback_query(F.data.regexp(r"^ord:(refund|dispute):\d+$"))
async def ask_reason(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "orders.manage")
    _, action, oid = cb.data.split(":")
    prompt = (
        "Причина возврата (будет в истории заказа). Выданные коды будут списаны."
        if action == "refund"
        else "Суть спора (будет в истории заказа). Автоматизация по заказу остановится."
    )
    await ask(cb, state, f"ord_{action}", prompt, back=f"ord:open:{oid}", order_id=int(oid))


@on_input("ord_refund")
async def refund_input(message: Message, ctx: dict) -> None:
    order = await orders.get_order(ctx["session"], ctx["order_id"], lock=True)
    await orders.refund(ctx["session"], order, ctx["actor"], message.text.strip()[:500])
    await ctx["state"].clear()
    text, markup = await order_card(ctx["session"], order.id)
    await message.answer(text, reply_markup=markup)


@on_input("ord_dispute")
async def dispute_input(message: Message, ctx: dict) -> None:
    order = await orders.get_order(ctx["session"], ctx["order_id"], lock=True)
    await orders.dispute(ctx["session"], order, ctx["actor"], message.text.strip()[:500])
    await ctx["state"].clear()
    text, markup = await order_card(ctx["session"], order.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.regexp(r"^ord:cancel:\d+$"))
async def cancel_ask(cb: CallbackQuery, actor: Actor) -> None:
    require(actor, "orders.manage")
    oid = cb.data.split(":")[2]
    text, markup = confirm(
        "Отменить заказ? Зарезервированные коды вернутся на склад.", f"ord:cancel:{oid}:y", f"ord:open:{oid}", danger=True
    )
    await show(cb, text, markup)


@router.callback_query(F.data.regexp(r"^ord:cancel:\d+:y$"))
async def cancel_do(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "orders.manage")
    oid = int(cb.data.split(":")[2])
    order = await orders.get_order(session, oid, lock=True)
    await orders.cancel(session, order, actor, "Отменён оператором в Telegram")
    text, markup = await order_card(session, oid)
    await show(cb, text, markup)


@router.callback_query(F.data.startswith("ord:note:"))
async def note(cb: CallbackQuery, state: FSMContext) -> None:
    oid = int(cb.data.split(":")[2])
    await ask(cb, state, "ord_note", "Текст заметки к заказу", back=f"ord:open:{oid}", order_id=oid)


@on_input("ord_note")
async def note_input(message: Message, ctx: dict) -> None:
    order = await orders.get_order(ctx["session"], ctx["order_id"], lock=True)
    await orders.add_note(ctx["session"], order, message.text, ctx["actor"])
    await ctx["state"].clear()
    text, markup = await order_card(ctx["session"], order.id)
    await message.answer(text, reply_markup=markup)


@router.callback_query(F.data.regexp(r"^ord:st:\d+$"))
async def status_menu(cb: CallbackQuery, session: AsyncSession) -> None:
    oid = int(cb.data.split(":")[2])
    order = await orders.get_order(session, oid)
    allowed = sorted(orders.TRANSITIONS[order.status], key=lambda s: list(S).index(s))
    rows = [[b(ORDER_STATUS_LABELS[s], f"ord:set:{oid}:{s.value}")] for s in allowed]
    await show(
        cb,
        f"🔀 <b>Ручная смена статуса {order.number}</b>\nТекущий: {ORDER_STATUS_LABELS[order.status]}\nПотребуется указать причину.",
        kb(*rows, nav(f"ord:open:{oid}")),
    )


@router.callback_query(F.data.startswith("ord:set:"))
async def status_set(cb: CallbackQuery, state: FSMContext, actor: Actor) -> None:
    require(actor, "orders.manage")
    _, _, oid, status = cb.data.split(":")
    await ask(
        cb,
        state,
        "ord_set_status",
        f"Причина перевода в «{ORDER_STATUS_LABELS[S(status)]}»",
        back=f"ord:open:{oid}",
        order_id=int(oid),
        status=status,
    )


@on_input("ord_set_status")
async def status_input(message: Message, ctx: dict) -> None:
    order = await orders.get_order(ctx["session"], ctx["order_id"], lock=True)
    await orders.set_status(ctx["session"], order, S(ctx["status"]), ctx["actor"], message.text.strip()[:500])
    await ctx["state"].clear()
    text, markup = await order_card(ctx["session"], order.id)
    await message.answer(text, reply_markup=markup)


# --- new order wizard ----------------------------------------------------------


@router.callback_query(F.data.startswith("ord:new"))
async def new_order(cb: CallbackQuery, session: AsyncSession, actor: Actor) -> None:
    require(actor, "orders.manage")
    page = int(cb.data.split(":")[2]) if cb.data.count(":") == 2 else 1
    rows, total = await catalog.search_products(session, status=ProductStatus.ACTIVE.value, page=page, per_page=PER_PAGE)
    text = "➕ <b>Новый заказ</b>\nСделка с PlayerOK вносится вручную (API нет). Выберите проданный товар:"
    if not rows:
        text += "\n\n" + empty("Нет активных товаров. Активируйте товар в разделе «Товары».")
    buttons = [[b(f"{short(p.name, 34)} · {money(p.current_price or p.recommended_price)}", f"ord:np:{p.id}")] for p in rows]
    await show(cb, text, kb(*buttons, pager("ord:new", page, total, PER_PAGE), nav("ord:home")))


@router.callback_query(F.data.startswith("ord:np:"))
async def new_order_product(cb: CallbackQuery, state: FSMContext, session: AsyncSession) -> None:
    pid = int(cb.data.split(":")[2])
    product = await catalog.get_product(session, pid)
    await ask(
        cb,
        state,
        "ord_new_ext",
        f"Товар: <b>{esc(product.name)}</b>\nНомер сделки PlayerOK (из ссылки или карточки сделки):",
        back="ord:new",
        product_id=pid,
    )


@on_input("ord_new_ext")
async def new_ext(message: Message, ctx: dict) -> None:
    product = await catalog.get_product(ctx["session"], ctx["product_id"])
    price = product.current_price or product.recommended_price
    await ctx["state"].update_data(
        kind="ord_new_price", external_id=message.text.strip()[:120], default_price=str(price) if price else None
    )
    hint = f" «+» — {money(price)}." if price else ""
    await message.answer(
        f"Цена продажи за единицу, ₽.{hint} Для нескольких штук: <code>1590 x2</code>", reply_markup=kb([b("✖️ Отмена", "cancel:ord:home")])
    )


@on_input("ord_new_price")
async def new_price(message: Message, ctx: dict) -> None:
    text = message.text.strip().lower().replace("х", "x")
    qty = 1
    if "x" in text:
        text, _, q = text.partition("x")
        if not q.strip().isdigit():
            raise DomainError("Количество после «x» — целое число")
        qty = int(q.strip())
    price = Decimal(ctx["default_price"]) if text.strip() == "+" and ctx.get("default_price") else parse_money(text.strip())
    await ctx["state"].update_data(kind="ord_new_buyer", price=str(price), quantity=qty)
    product = await catalog.get_product(ctx["session"], ctx["product_id"])
    need = f"\nДля выполнения нужно: <b>{esc(product.required_buyer_data)}</b>" if product.required_buyer_data else ""
    await message.answer(
        f"Ник покупателя на PlayerOK и, через пробел, данные для выдачи (ссылка или username).{need}\nНапример: <code>gamer777 @gamer777</code>. «-» — пропустить.",
        reply_markup=kb([b("✖️ Отмена", "cancel:ord:home")]),
    )


@on_input("ord_new_buyer")
async def new_buyer(message: Message, ctx: dict) -> None:
    session, actor = ctx["session"], ctx["actor"]
    text = message.text.strip()
    buyer, link = (None, None) if text == "-" else (text.split(None, 1) + [None])[:2]
    order, created = await orders.create_order(
        session,
        orders.NewOrder(
            external_id=ctx["external_id"],
            items=[orders.NewItem(ctx["product_id"], int(ctx["quantity"]), Decimal(ctx["price"]))],
            buyer_name=buyer,
            buyer_data={"link": link or ""},
        ),
        actor,
    )
    await ctx["state"].clear()
    card_text, markup = await order_card(session, order.id)
    prefix = "✅ Заказ создан, обработка запущена\n\n" if created else "ℹ️ Эта сделка уже внесена — повторно не создаётся\n\n"
    await message.answer(prefix + card_text, reply_markup=markup)


# --- code reveal ---------------------------------------------------------------


async def _delete_later(bot: Bot, chat_id: int, message_id: int, delay: int) -> None:
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except Exception:  # noqa: BLE001 - the user may have deleted it already
        log.debug("code message already gone")


@router.callback_query(F.data.startswith("code:show:"))
async def show_code(cb: CallbackQuery, session: AsyncSession, actor: Actor, bot: Bot) -> None:
    require(actor, "orders.reveal_codes")
    code, plain = await inventory.reveal(session, int(cb.data.split(":")[2]), actor)
    ttl = get_settings().code_reveal_ttl_seconds
    sent = await cb.message.answer(
        f"🔑 <b>Код</b>{' (тестовый)' if code.is_test else ''}:\n<code>{esc(plain)}</code>\n\n<i>Сообщение удалится через {ttl // 60} мин. Просмотр записан в журнал.</i>",
        reply_markup=kb([b("📋 Скопировать", copy=plain)]) if len(plain) <= 256 else None,
    )
    await cb.answer()
    asyncio.create_task(_delete_later(bot, sent.chat.id, sent.message_id, ttl))
