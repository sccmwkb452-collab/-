from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.bot import texts
from nft_gift_bot.bot.notifier import notify_admins
from nft_gift_bot.config.settings import Settings
from nft_gift_bot.handlers.common import respond
from nft_gift_bot.keyboards.main import MENU_ITEMS, MENU_SUPPORT
from nft_gift_bot.models import User
from nft_gift_bot.services.support_service import SupportError, SupportService

router = Router(name="support")

ERRORS = {
    "empty": "Сообщение пустое.",
    "too_long": "Сообщение слишком длинное (до 2000 символов).",
    "too_many_open": "У вас уже есть открытые обращения. Дождитесь ответа.",
}


class SupportStates(StatesGroup):
    waiting_message = State()


@router.message(F.text == MENU_SUPPORT)
async def support(message: Message, state: FSMContext, emoji: dict) -> None:
    await state.set_state(SupportStates.waiting_message)
    await respond(message, texts.support_prompt(emoji))


@router.message(SupportStates.waiting_message, F.text, ~F.text.in_(MENU_ITEMS))
async def support_message(
    message: Message, state: FSMContext, session: AsyncSession, settings: Settings, db_user: User, emoji: dict
) -> None:
    await state.clear()
    try:
        ticket = await SupportService(session).create_ticket(db_user.id, message.text or "")
    except SupportError as exc:
        await respond(message, texts.error(emoji, ERRORS.get(str(exc), "Не удалось создать обращение.")))
        return
    await respond(message, texts.support_created(emoji, ticket.id))
    await notify_admins(
        message.bot, settings.admin_id_set,
        f"🆘 Обращение №{ticket.id} от {db_user.telegram_id}:\n{ticket.message[:500]}\n\nОтветить: /reply {ticket.id} <текст>",
    )
