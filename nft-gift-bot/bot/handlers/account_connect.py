"""Раздел «Подключить аккаунт» — Business Bot API интеграция."""
import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery
from sqlalchemy.ext.asyncio import AsyncSession

from bot.keyboards.main_menu import back_kb, connect_account_kb
from bot.ui.rich_text import RichTextBuilder, e
from bot.ui.templates import connect_account_info
from database.models.user import User

logger = logging.getLogger(__name__)
router = Router(name="account_connect")


@router.callback_query(F.data == "connect:info")
async def cb_connect_info(callback: CallbackQuery, db_user: User) -> None:
    text, entities = connect_account_info()
    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=connect_account_kb(),
    )
    await callback.answer()


@router.callback_query(F.data == "connect:verify")
async def cb_connect_verify(
    callback: CallbackQuery,
    db_user: User,
    session: AsyncSession,
) -> None:
    """
    Проверяем, подключён ли Business-аккаунт.
    Telegram посылает business_connection_id в апдейтах от бизнес-аккаунтов.
    Реальная проверка — через бизнес-апдейты. Здесь показываем статус.
    """
    rt = RichTextBuilder()
    rt.custom_emoji("link").text(" ").bold("Проверка подключения").newline()
    rt.text("─" * 26).newline(2)
    rt.text(f"{e('warning')} Автоматическая проверка через").newline()
    rt.text("Business Bot API пока не активна.").newline(2)
    rt.italic(
        "Убедись, что добавил бота в Telegram Business\n"
        "и попробуй отправить любое сообщение — \n"
        "бот получит твой business_connection_id."
    )
    text, entities = rt.build()

    await callback.message.edit_text(
        text=text,
        entities=entities,
        reply_markup=back_kb("connect:info"),
    )
    await callback.answer("Проверка выполнена", show_alert=False)
    logger.info("User %d checked Business connection status", db_user.telegram_id)
