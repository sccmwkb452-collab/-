import logging

from aiogram import Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.errors(ExceptionTypeFilter(Exception))
async def handle_error(event: ErrorEvent) -> None:
    logger.exception(
        "Unhandled exception in update %s",
        event.update.update_id,
        exc_info=event.exception,
    )

    update = event.update
    message = None

    if update.message:
        message = update.message
    elif update.callback_query:
        message = update.callback_query.message
        try:
            await update.callback_query.answer(
                "⚠️ Произошла ошибка. Попробуй позже.", show_alert=True
            )
        except Exception:
            pass

    if message:
        try:
            await message.answer(
                "⚠️ <b>Что-то пошло не так</b>\n\n"
                "Произошла непредвиденная ошибка. "
                "Попробуй ещё раз или обратись в поддержку командой /start.",
                parse_mode="HTML",
            )
        except Exception:
            pass
