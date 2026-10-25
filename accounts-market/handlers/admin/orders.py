"""Admin: orders, search, refunds."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from admin.states import OrderSearch
from bot.callbacks import Adm
from bot.ui import Screen, show
from database.models import Order, OrderStatus, User
from keyboards import admin as akb
from keyboards.user import btn, rows
from orders import service as orders
from services.errors import ShopError
from services.formatting import clip, dt, esc, money

router = Router(name="admin_orders")
PAGE = 8


@router.callback_query(Adm.filter(F.s == "ords"))
async def orders_list(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext) -> None:
    await state.clear()
    refunded = callback_data.v == "r"
    cond = Order.status == (OrderStatus.REFUNDED if refunded else OrderStatus.COMPLETED)
    total = await session.scalar(select(func.count(Order.id)).where(cond)) or 0
    pages = max(1, math.ceil(total / PAGE))
    page = min(max(callback_data.p, 0), pages - 1)
    items = (
        await session.execute(select(Order).where(cond).order_by(Order.id.desc()).limit(PAGE).offset(page * PAGE))
    ).scalars()
    buttons = [
        (f"{o.number} · {clip(o.product_title, 22)} · {money(o.price)}", Adm(s="ord", id=o.id, p=page, v=callback_data.v))
        for o in items
    ]
    title = "↩️ <b>Возвращённые заказы</b>" if refunded else "🛒 <b>Заказы</b>"
    extra = [
        [btn("🔎 Найти по номеру", Adm(s="osearch"), style="primary")],
        [btn("🛒 Выполненные" if refunded else "↩️ Возвраты", Adm(s="ords", v="" if refunded else "r"))],
    ]
    await show(
        callback,
        Screen(f"{title}\n\nВсего: {total}", akb.listing(buttons, page, pages, lambda n: Adm(s="ords", p=n, v=callback_data.v), extra)),
    )


async def order_screen(session: AsyncSession, order: Order, page: int = 0, v: str = "") -> Screen:
    buyer = await session.get(User, order.user_id)
    who = f"@{esc(buyer.username)}" if buyer and buyer.username else esc(buyer.full_name if buyer else "")
    lines = [
        f"🛒 <b>Заказ {order.number}</b>",
        "",
        f"Покупатель: {who} · <code>{order.user_id}</code>",
        f"Товар: {esc(order.product_title)} (#{order.product_id})",
        f"Сумма: <b>{money(order.price)}</b>",
        f"Создан: {dt(order.created_at)}",
        f"Единица товара: #{order.item_id}",
    ]
    if order.status == OrderStatus.COMPLETED:
        lines.append("Статус: ✅ выполнен")
    else:
        lines += [
            "Статус: ↩️ возврат",
            f"Дата возврата: {dt(order.refunded_at)}",
            f"Причина: {esc(order.refund_reason or '—')}",
            f"Оформил: <code>{order.refunded_by}</code>",
        ]
    kb_lines = []
    if order.status == OrderStatus.COMPLETED:
        kb_lines.append([btn("↩️ Отменить и вернуть средства", Adm(s="oref", id=order.id), style="danger")])
    kb_lines.append([btn("👤 Покупатель", Adm(s="usr", id=order.user_id))])
    kb_lines.append([akb.back("ords", "◀️ К заказам", p=page, v=v)])
    return Screen("\n".join(lines), rows(*kb_lines))


@router.callback_query(Adm.filter(F.s == "ord"))
async def order_card(callback: CallbackQuery, callback_data: Adm, session: AsyncSession, state: FSMContext, callback_answer: CallbackAnswer) -> None:
    await state.clear()
    order = await session.get(Order, callback_data.id, populate_existing=True)
    if order is None:
        callback_answer.text = "Заказ не найден"
        return
    await show(callback, await order_screen(session, order, callback_data.p, callback_data.v))


@router.callback_query(Adm.filter(F.s == "osearch"))
async def search_prompt(callback: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(OrderSearch.number)
    await show(callback, Screen("🔎 Отправьте номер заказа, например <code>AM-000123</code> или <code>123</code>.", akb.cancel("ords")))


@router.message(OrderSearch.number, F.text)
async def search(message: Message, state: FSMContext, session: AsyncSession) -> None:
    order_id = orders.parse_order_number(message.text)
    order = await session.get(Order, order_id) if order_id else None
    if order is None:
        await message.answer("Заказ не найден. Попробуйте ещё раз.", reply_markup=akb.cancel("ords"))
        return
    await state.clear()
    await show(message, await order_screen(session, order))


@router.callback_query(Adm.filter(F.s == "oref"))
async def refund_prompt(callback: CallbackQuery, callback_data: Adm, state: FSMContext) -> None:
    await state.set_state(OrderSearch.refund_reason)
    await state.update_data(order_id=callback_data.id)
    text = (
        "↩️ <b>Возврат средств</b>\n\n"
        "Сумма заказа вернётся на баланс покупателя, единица товара будет отозвана и не попадёт в продажу.\n\n"
        "Отправьте причину возврата (обязательно, она попадёт в журнал и будет видна покупателю):"
    )
    await show(callback, Screen(text, akb.cancel("ord", id=callback_data.id)))


@router.message(OrderSearch.refund_reason, F.text)
async def refund_reason(message: Message, state: FSMContext, session: AsyncSession) -> None:
    reason = message.text.strip()
    order_id = (await state.get_data())["order_id"]
    if len(reason) < 3 or len(reason) > 256:
        await message.answer("Причина: от 3 до 256 символов.", reply_markup=akb.cancel("ord", id=order_id))
        return
    await state.update_data(reason=reason)
    order = await session.get(Order, order_id)
    await message.answer(
        f"Подтвердите возврат <b>{money(order.price)}</b> по заказу {order.number}.\nПричина: {esc(reason)}",
        reply_markup=akb.confirm(Adm(s="orefok", id=order_id), Adm(s="ord", id=order_id), "↩️ Вернуть средства"),
    )


@router.callback_query(Adm.filter(F.s == "orefok"))
async def refund(
    callback: CallbackQuery,
    callback_data: Adm,
    state: FSMContext,
    session: AsyncSession,
    sm: async_sessionmaker[AsyncSession],
    callback_answer: CallbackAnswer,
) -> None:
    data = await state.get_data()
    reason = data.get("reason")
    if not reason or data.get("order_id") != callback_data.id:
        callback_answer.text, callback_answer.show_alert = "Сначала укажите причину возврата", True
        return
    await state.clear()
    try:
        result = await orders.refund_order(sm, callback_data.id, callback.from_user.id, reason)
    except ShopError as exc:
        callback_answer.text, callback_answer.show_alert = exc.message, True
        return
    order = result.order
    if result.refunded:
        callback_answer.text = "Средства возвращены"
        try:
            await callback.bot.send_message(
                order.user_id,
                f"↩️ По заказу {order.number} оформлен возврат: <b>+{money(order.price)}</b> на баланс.\n"
                f"Причина: {esc(reason)}",
            )
        except TelegramAPIError:
            pass
    else:
        callback_answer.text, callback_answer.show_alert = "Возврат по этому заказу уже был оформлен", True
    await show(callback, await order_screen(session, await session.get(Order, order.id, populate_existing=True)))
