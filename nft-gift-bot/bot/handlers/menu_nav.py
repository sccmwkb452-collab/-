"""Callback-хендлер навигации к главному меню (menu:main)."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import main_menu_kb
from bot.ui.templates import welcome_back
from database.models.user import User
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = Router(name="menu_nav")


@router.callback_query(F.data == "menu:main")
async def cb_main_menu(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    has_sub = await SubscriptionService(session).has_active(db_user.id)
    text, entities = welcome_back(db_user)
    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=main_menu_kb(has_subscription=has_sub),
    )
    await callback.answer()
