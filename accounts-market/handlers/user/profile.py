"""Personal account: profile, purchases, operations."""

from __future__ import annotations

import math

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message
from aiogram.filters import Command
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot import media
from bot.callbacks import Nav, Orders, OrderView, Txs
from bot.ui import Screen, show
from database.models import Order, OrderStatus, Transaction, TxKind, User
from keyboards import user as kb
from orders import service as orders
from services import users
from services.formatting import date, dt, esc, money, signed_money
from services.shop_settings import ShopSettings

router = Router(name="profile")

ORDERS_PAGE = 6
TX_PAGE = 10

TX_LABELS = {
    TxKind.TOPUP: "💎 Пополнение",
    TxKind.PURCHASE: "🛒 Покупка",
    TxKind.REFUND: "↩️ Возврат",
    TxKind.REFERRAL: "🎁 Реферальный бонус",
    TxKind.ADMIN: "🛠 Корректировка",
    TxKind.TOPUP_REFUND: "↩️ Возврат пополнения",
}


async def profile_screen(session: AsyncSession, user: User, shop: ShopSettings) -> Screen:
    await session.refresh(user)
    stats = await users.profile_stats(session, user.id)
    name = f"@{esc(user.username)}" if user.username else esc(user.full_name or "Пользователь")
    text = (
        f"👤 <b>Личный кабинет</b> · {name}\n\n"
        f"🆔 Telegram ID: <code>{user.id}</code>\n"
        f"📅 Регистрация: {date(user.created_at)}\n"
        f"💰 Баланс: <b>{money(user.balance)}</b>\n\n"
        f"🛒 Покупок: {stats.purchases}\n"
        f"💵 Сумма покупок: {money(stats.spent)}\n\n"
        f"🎁 Приглашено: {stats.referrals} · с покупками: {stats.referrals_with_purchases}\n"
        f"💸 Заработано на рефералах: {money(stats.referral_earned)}"
    )
    return Screen(text, kb.profile(), await media.banner("profile", shop.shop_name))


@router.callback_query(Nav.filter(F.to == "profile"))
async def profile(callback: CallbackQuery, session: AsyncSession, user: User, shop: ShopSettings) -> None:
    await show(callback, await profile_screen(session, user, shop))


@router.message(Command("profile"))
async def profile_command(message: Message, session: AsyncSession, user: User, shop: ShopSettings) -> None:
    await show(message, await profile_screen(session, user, shop))


@router.callback_query(Orders.filter())
async def orders_list(
    callback: CallbackQuery, callback_data: Orders, session: AsyncSession, user: User, shop: ShopSettings
) -> None:
    page = max(callback_data.page, 0)
    items, total = await orders.user_orders(session, user.id, ORDERS_PAGE, page * ORDERS_PAGE)
    pages = max(1, math.ceil(total / ORDERS_PAGE))
    if total:
        text = (
            "📦 <b>Мои покупки</b>\n\n"
            f"Всего заказов: {total}. Нажмите на заказ, чтобы открыть данные товара.\n\n"
            "✅ выполнен · ↩️ возврат"
        )
    else:
        text = "📦 <b>Мои покупки</b>\n\nЗдесь появятся ваши заказы. Выберите товар в каталоге 🛍"
    await show(callback, Screen(text, kb.orders_list(items, page, pages), await media.banner("orders", shop.shop_name)))


@router.callback_query(OrderView.filter())
async def order_view(
    callback: CallbackQuery,
    callback_data: OrderView,
    session: AsyncSession,
    user: User,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    order = await session.get(Order, callback_data.id)
    if order is None or order.user_id != user.id:  # never show someone else's order
        callback_answer.text, callback_answer.show_alert = "Заказ не найден", True
        return
    lines = [
        f"📦 <b>Заказ {order.number}</b>",
        "",
        f"Товар: {esc(order.product_title)}",
        f"Сумма: {money(order.price)}",
        f"Дата: {dt(order.created_at)}",
    ]
    content = None
    if order.status == OrderStatus.COMPLETED:
        lines.append("Статус: ✅ выполнен")
        content = order.item.content
        lines += ["", "🔑 <b>Данные товара</b>", f"<pre>{esc(content)}</pre>"]
    else:
        lines.append("Статус: ↩️ средства возвращены на баланс")
        if order.refund_reason:
            lines.append(f"Причина: {esc(order.refund_reason)}")
    # Order content is sent as text: it can be long and must stay copyable.
    await show(callback, Screen("\n".join(lines), kb.order_view(order, callback_data.page, content)))


@router.callback_query(Txs.filter())
async def transactions(
    callback: CallbackQuery, callback_data: Txs, session: AsyncSession, user: User, shop: ShopSettings
) -> None:
    page = max(callback_data.page, 0)
    total = await session.scalar(select(func.count(Transaction.id)).where(Transaction.user_id == user.id)) or 0
    rows = (
        await session.execute(
            select(Transaction)
            .where(Transaction.user_id == user.id)
            .order_by(Transaction.id.desc())
            .limit(TX_PAGE)
            .offset(page * TX_PAGE)
        )
    ).scalars()
    lines = ["💳 <b>История операций</b>", ""]
    for tx in rows:
        label = TX_LABELS.get(tx.kind, tx.kind)
        lines.append(f"{label} · <b>{signed_money(tx.amount)}</b>\n<i>{dt(tx.created_at)} · баланс {money(tx.balance_after)}</i>")
    if total == 0:
        lines.append("Операций пока не было.")
    pages = max(1, math.ceil(total / TX_PAGE))
    await show(
        callback,
        Screen("\n".join(lines), kb.paged(lambda n: Txs(page=n), page, pages, kb.btn("👤 Кабинет", Nav(to="profile")))),
    )
