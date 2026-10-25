"""Checkout: balance/stock check, confirmation, atomic purchase and delivery."""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from aiogram import Router
from aiogram.exceptions import TelegramAPIError
from aiogram.types import CallbackQuery
from aiogram.utils.callback_answer import CallbackAnswer
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from bot import media
from bot.callbacks import Buy, BuyOk
from bot.ui import Screen, show
from catalog import service as catalog
from database.models import Order, User
from handlers.user.catalog import categories, product_screen
from keyboards import user as kb
from orders import service as orders
from services.errors import (
    AccessRestricted,
    InsufficientFunds,
    OutOfStock,
    PriceChanged,
    ProductUnavailable,
    ShopError,
)
from services.formatting import esc, money
from services.shop_settings import ShopSettings

router = Router(name="purchase")
log = logging.getLogger(__name__)

# Second line of defence against double taps inside one process; the database
# idempotency key and row locks are what actually guarantee a single charge.
_locks: defaultdict[int, asyncio.Lock] = defaultdict(asyncio.Lock)


def delivery_text(order: Order, content: str) -> str:
    return (
        f"📦 <b>Заказ {order.number}</b>\n"
        f"Товар: {esc(order.product_title)}\n"
        f"Сумма: {money(order.price)}\n\n"
        f"🔑 <b>Данные товара</b>\n<pre>{esc(content)}</pre>\n\n"
        "Сохраните данные. Они также доступны в разделе «📦 Мои покупки»."
    )


async def insufficient_screen(shop: ShopSettings, product_id: int, price: int, balance: int, src: str, page: int) -> Screen:
    text = (
        "💎 <b>Недостаточно средств</b>\n\n"
        f"Стоимость: <b>{money(price)}</b>\n"
        f"Ваш баланс: {money(balance)}\n"
        f"Не хватает: <b>{money(price - balance)}</b>\n\n"
        "Пополните баланс и вернитесь к товару: он будет ждать вас в каталоге."
    )
    return Screen(text, kb.insufficient(product_id, src, page), await media.banner("warning", shop.shop_name))


@router.callback_query(Buy.filter())
async def checkout(
    callback: CallbackQuery,
    callback_data: Buy,
    session: AsyncSession,
    user: User,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    view = await catalog.get_product(session, callback_data.id)
    if view is None:
        callback_answer.text, callback_answer.show_alert = "Товар больше недоступен", True
        await categories(callback, session, shop)
        return
    src, page = callback_data.src, callback_data.page
    p = view.product
    if not catalog.is_buyable(view):
        callback_answer.text, callback_answer.show_alert = "Товара нет в наличии", True
        await show(callback, await product_screen(view, shop, src, page))
        return
    if p.price != callback_data.price:
        callback_answer.text, callback_answer.show_alert = f"Цена изменилась: теперь {money(p.price)}", True
        await show(callback, await product_screen(view, shop, src, page))
        return
    if user.balance < p.price:
        await show(callback, await insufficient_screen(shop, p.id, p.price, user.balance, src, page))
        return
    text = (
        "🛒 <b>Подтверждение покупки</b>\n\n"
        f"Товар: <b>{esc(p.title)}</b>\n"
        f"Категория: {esc(p.category.title)}\n"
        + (f"Регион: {esc(p.region)}\n" if p.region else "")
        + f"\n💰 К оплате: <b>{money(p.price)}</b>\n"
        f"💳 Баланс сейчас: {money(user.balance)}\n"
        f"💳 Баланс после покупки: {money(user.balance - p.price)}\n\n"
        "Средства спишутся с баланса, а данные товара придут сразу после подтверждения."
    )
    nonce = orders.new_nonce()
    await show(
        callback,
        Screen(text, kb.confirm_purchase(p.id, p.price, nonce, src, page), await media.banner("checkout", shop.shop_name)),
    )


@router.callback_query(BuyOk.filter())
async def confirm(
    callback: CallbackQuery,
    callback_data: BuyOk,
    session: AsyncSession,
    sm: async_sessionmaker[AsyncSession],
    user: User,
    shop: ShopSettings,
    callback_answer: CallbackAnswer,
) -> None:
    lock = _locks[user.id]
    if lock.locked():
        callback_answer.text = "⏳ Заказ уже обрабатывается…"
        return
    try:
        async with lock:
            try:
                result = await orders.purchase(
                    sm,
                    user_id=user.id,
                    product_id=callback_data.id,
                    expected_price=callback_data.price,
                    nonce=callback_data.nonce,
                )
            except InsufficientFunds:
                await session.refresh(user)
                await show(callback, await insufficient_screen(shop, callback_data.id, callback_data.price, user.balance, "c", 0))
                return
            except (OutOfStock, PriceChanged) as exc:
                callback_answer.text, callback_answer.show_alert = exc.message, True
                view = await catalog.get_product(session, callback_data.id)
                if view is not None:
                    await show(callback, await product_screen(view, shop, "c", 0))
                return
            except (ProductUnavailable, AccessRestricted, ShopError) as exc:
                callback_answer.text, callback_answer.show_alert = exc.message or "Покупка недоступна", True
                await categories(callback, session, shop)
                return
    finally:
        if not lock.locked():
            _locks.pop(user.id, None)

    order = result.order
    if not result.created:
        callback_answer.text = "Этот заказ уже оформлен"
    await session.refresh(user)
    text = (
        f"✅ <b>Заказ {order.number} оформлен</b>\n\n"
        f"Товар: {esc(order.product_title)}\n"
        f"Списано: <b>{money(order.price)}</b>\n"
        f"Баланс: {money(user.balance)}\n\n"
        "Данные товара отправлены отдельным сообщением ниже и сохранены в «📦 Мои покупки»."
    )
    await show(callback, Screen(text, kb.purchase_done(order.id), await media.banner("success", shop.shop_name)))
    if result.created:
        await callback.bot.send_message(user.id, delivery_text(order, result.content))
        log.info("order %s completed", order.number)
        if result.referral_tx is not None:
            try:
                await callback.bot.send_message(
                    result.referral_tx.user_id,
                    f"🎁 Начислен реферальный бонус: <b>+{money(result.referral_tx.amount)}</b>\n"
                    "Ваш приглашённый совершил покупку.",
                )
            except TelegramAPIError:
                pass
