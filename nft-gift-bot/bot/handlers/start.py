import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import main_menu_kb
from bot.ui.templates import welcome_back, welcome_new
from database.models.user import User
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)
router = Router(name="start")


async def _send_menu(message: Message, db_user: User, session: AsyncSession) -> None:
    has_sub = await SubscriptionService(session).has_active(db_user.id)
    is_new = db_user.created_at == db_user.updated_at

    text, entities = welcome_new(db_user) if is_new else welcome_back(db_user)
    await message.answer(
        text=text,
        entities=entities,
        reply_markup=main_menu_kb(has_subscription=has_sub),
    )
    logger.info("User %d called /start [new=%s has_sub=%s]", db_user.telegram_id, is_new, has_sub)


@router.message(CommandStart())
async def cmd_start(message: Message, db_user: User, session: AsyncSession) -> None:
    await _send_menu(message, db_user, session)


@router.message(Command("menu"))
async def cmd_menu(message: Message, db_user: User, session: AsyncSession) -> None:
    await _send_menu(message, db_user, session)
