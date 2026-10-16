"""Раздел «Купить подписку» / «Моя подписка»."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_kb, subscription_plans_kb
from bot.ui.templates import (
    subscription_active,
    subscription_none,
    subscription_plans,
)
from config import settings
from database.models.user import User
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = Router(name="subscription")


@router.callback_query(F.data == "sub:plans")
async def cb_sub_plans(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    """Список тарифных планов."""
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
    """Детали активной подписки или экран «нет подписки»."""
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
    """Инициация покупки подписки (заглушка — платёжный провайдер подключается отдельно)."""
    plan_key = callback.data.split(":")[-1]  # "basic" или "premium"
    plan_label = "Basic" if plan_key == "basic" else "Premium"
    stars = (
        settings.sub_basic_price_stars
        if plan_key == "basic"
        else settings.sub_premium_price_stars
    )
    await callback.answer(
        f"⏳ Подготовка инвойса {plan_label} — {stars} ⭐...",
        show_alert=True,
    )
    logger.info(
        "User %d initiated subscription purchase: plan=%s stars=%d",
        db_user.telegram_id,
        plan_key,
        stars,
    )
