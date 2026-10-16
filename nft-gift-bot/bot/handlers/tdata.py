"""Раздел «Купить Tdata»."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery

from bot.keyboards.main_menu import tdata_shop_kb
from bot.ui.templates import tdata_shop_info
from config import settings
from database.models.user import User

logger = logging.getLogger(__name__)
router = Router(name="tdata")


@router.callback_query(F.data == "tdata:contact")
async def cb_tdata_contact(callback: CallbackQuery, db_user: User) -> None:
    await callback.answer(
        f"Открываю чат с менеджером @{settings.support_username}",
        show_alert=True,
    )
    logger.info("User %d requested tdata manager contact", db_user.telegram_id)
