import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import main_menu_kb
from database.models.user import User
from services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)

router = Router(name="start")

_WELCOME_NEW = """
✨ <b>Добро пожаловать в NFT Gift Bot!</b>

Привет, <b>{name}</b>! 👋

Этот бот позволяет тебе:
• 🎁 Покупать и дарить уникальные NFT-подарки Telegram
• 💎 Управлять подпиской и открывать эксклюзивные возможности
• 📊 Отслеживать историю всех операций

<i>Выбери раздел в меню ниже:</i>
"""

_WELCOME_BACK = """
👋 <b>С возвращением, {name}!</b>

<i>Выбери раздел:</i>
"""


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    db_user: User,
    session: AsyncSession,
) -> None:
    sub_service = SubscriptionService(session)
    has_sub = await sub_service.has_active(db_user.id)

    is_first_visit = (
        db_user.created_at == db_user.updated_at
        # грубая эвристика «только что создан»; точнее — через флаг в User
    )

    text_template = _WELCOME_NEW if is_first_visit else _WELCOME_BACK
    text = text_template.format(name=db_user.full_name)

    await message.answer(
        text=text,
        reply_markup=main_menu_kb(has_subscription=has_sub),
        parse_mode="HTML",
    )

    logger.info(
        "User %d (%s) called /start [has_sub=%s]",
        db_user.telegram_id,
        db_user.username,
        has_sub,
    )


@router.message(Command("menu"))
async def cmd_menu(
    message: Message,
    db_user: User,
    session: AsyncSession,
) -> None:
    sub_service = SubscriptionService(session)
    has_sub = await sub_service.has_active(db_user.id)

    await message.answer(
        "🏠 <b>Главное меню</b>",
        reply_markup=main_menu_kb(has_subscription=has_sub),
        parse_mode="HTML",
    )
