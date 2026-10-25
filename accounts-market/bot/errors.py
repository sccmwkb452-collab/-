"""Last-resort error handling: the user gets a short message, the log gets the traceback."""

from __future__ import annotations

import logging

from aiogram import Router
from aiogram.exceptions import TelegramAPIError, TelegramBadRequest, TelegramForbiddenError
from aiogram.types import ErrorEvent

from keyboards import user as kb

router = Router(name="errors")
log = logging.getLogger(__name__)

TEXT = "⚠️ Что-то пошло не так. Мы уже разбираемся, попробуйте ещё раз через минуту."


@router.errors()
async def on_error(event: ErrorEvent) -> bool:
    exc = event.exception
    update = event.update
    if isinstance(exc, TelegramBadRequest) and "query is too old" in exc.message:
        return True  # stale callback: nothing to answer anymore
    if isinstance(exc, TelegramForbiddenError):
        log.info("user blocked the bot: %s", exc.message)
        return True
    # Only exception type and update id: messages may contain private data.
    log.error("update %s failed: %s", update.update_id, type(exc).__name__, exc_info=exc)
    try:
        if update.callback_query:
            await update.callback_query.answer(TEXT, show_alert=True)
        elif update.message:
            await update.message.answer(TEXT, reply_markup=kb.only_home())
    except TelegramAPIError:
        pass
    return True
