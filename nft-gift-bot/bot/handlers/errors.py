import logging

from aiogram import Router
from aiogram.filters import ExceptionTypeFilter
from aiogram.types import ErrorEvent

logger = logging.getLogger(__name__)

router = Router(name="errors")


@router.errors(ExceptionTypeFilter(Exception))
async def handle_any_error(event: ErrorEvent) -> bool:
    logger.exception(
        "Unhandled error on update_id=%s: %r",
        getattr(event.update, "update_id", "?"),
        event.exception,
    )

    update = event.update
    notify_msg = (
        "⚠️ <b>Что-то пошло не так</b>\n\n"
        "Произошла непредвиденная ошибка. Попробуй ещё раз "
        "или используй /start для перезапуска."
    )

    if update.callback_query:
        try:
            await update.callback_query.answer("⚠️ Ошибка. Попробуй позже.", show_alert=True)
        except Exception:
            pass

    target_message = None
    if update.message:
        target_message = update.message
    elif update.callback_query and update.callback_query.message:
        target_message = update.callback_query.message

    if target_message:
        try:
            await target_message.answer(notify_msg, parse_mode="HTML")
        except Exception:
            pass

    return True  # помечает ошибку как обработанную
