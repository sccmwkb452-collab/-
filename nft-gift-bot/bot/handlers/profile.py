"""Раздел «Профиль»."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import profile_kb
from bot.ui.templates import profile
from database.models.gift import Gift, GiftStatus
from database.models.transaction import Transaction
from database.models.user import User
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = Router(name="profile")


@router.callback_query(F.data == "profile:main")
async def cb_profile(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    sub_service = SubscriptionService(session)
    sub = await sub_service.get_active(db_user.id)

    gift_count_result = await session.execute(
        select(func.count())
        .select_from(Gift)
        .where(Gift.owner_id == db_user.id, Gift.status == GiftStatus.OWNED)
    )
    gift_count = gift_count_result.scalar_one()

    tx_count_result = await session.execute(
        select(func.count())
        .select_from(Transaction)
        .where(Transaction.user_id == db_user.id)
    )
    tx_count = tx_count_result.scalar_one()

    text, entities = profile(
        user=db_user,
        sub=sub,
        gift_count=gift_count,
        tx_count=tx_count,
    )

    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=profile_kb(has_subscription=sub is not None),
    )
    await callback.answer()
