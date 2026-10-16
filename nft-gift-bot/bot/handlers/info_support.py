"""Раздел «Информация и поддержка»."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import support_kb
from bot.ui.rich_text import RichTextBuilder
from bot.ui.templates import info_and_support
from config import settings
from database.models.user import User

logger = logging.getLogger(__name__)
router = Router(name="info_support")


@router.callback_query(F.data == "info:main")
async def cb_info_main(callback: CallbackQuery, db_user: User) -> None:
    # Базовый текст из шаблона + дописываем ID пользователя как code-entity
    text, entities = info_and_support(settings.support_username)

    # Добавляем ID через RichTextBuilder, дописывая к уже готовому тексту
    rt = RichTextBuilder()
    rt._parts = [text]
    rt._entities = entities
    rt.code(str(db_user.telegram_id))

    final_text, final_entities = rt.build()

    await callback.message.edit_text(
        text=final_text,
        entities=final_entities,
        reply_markup=support_kb(settings.support_username),
    )
    await callback.answer()
