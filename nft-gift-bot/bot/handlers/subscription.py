"""Раздел «Купить подписку» / «Моя подписка»."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_kb, subscription_plans_kb, ton_payment_kb
from bot.ui.rich_text import RichTextBuilder
from bot.ui.templates import (
    subscription_active,
    subscription_none,
    subscription_plans,
)
from config import settings
from database.models.user import User
from payments.payment_service import PaymentService
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = Router(name="subscription")


@router.callback_query(F.data == "sub:plans")
async def cb_sub_plans(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    text, entities = subscription_plans(
        basic_stars=settings.sub_basic_price_stars,
        premium_stars=settings.sub_premium_price_stars,
        basic_days=settings.sub_basic_duration_days,
        premium_days=settings.sub_premium_duration_days,
    )
    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=subscription_plans_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "sub:info")
async def cb_sub_info(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    sub = await SubscriptionService(session).get_active(db_user.id)

    if sub:
        text, entities = subscription_active(sub)
        kb = back_kb()
    else:
        text, entities = subscription_none()
        kb = subscription_plans_kb()

    await callback.message.edit_text(text=text, entities=entities, reply_markup=kb)
    await callback.answer()


@router.callback_query(F.data.startswith("sub:buy:"))
async def cb_sub_buy(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    """Show TON payment instructions and create a pending payment."""
    pay_service = PaymentService(session)

    # Reuse existing pending payment if still valid
    existing = await pay_service.get_pending(db_user.id)
    if existing is None:
        result = await pay_service.init_payment(db_user.id)
        await session.commit()
        comment = result.payment_comment
        expires_at = result.expires_at
        amount_ton = result.amount_ton
        address = result.recipient_address
    else:
        comment = existing.payment_comment
        expires_at = existing.expires_at
        amount_ton = settings.sub_price_ton
        address = settings.ton_recipient_address

    rt = RichTextBuilder()
    rt.text("💎 Оплата подписки — TON\n\n")
    rt.bold("Сумма: ")
    rt.text(f"{amount_ton} TON\n")
    rt.bold("Адрес кошелька:\n")
    rt.code(address or "Не настроен — обратитесь к администратору")
    rt.text("\n\n")
    rt.bold("Комментарий к переводу:\n")
    rt.code(comment)
    rt.text("\n\n")
    rt.text("⚠️ Переведи точную сумму с комментарием. После перевода нажми кнопку ниже — ")
    rt.text("бот проверит транзакцию на блокчейне.")
    rt.text(f"\n\n⏳ Окно оплаты до: {expires_at.strftime('%H:%M UTC')}")

    text, entities = rt.build()
    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=ton_payment_kb(comment),
    )
    await callback.answer()
