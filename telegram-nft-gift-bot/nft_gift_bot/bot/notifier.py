from __future__ import annotations

import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardMarkup

from nft_gift_bot.bot.ui import Rich

logger = logging.getLogger(__name__)


async def send_safe(bot: Bot, chat_id: int, rich: Rich, reply_markup: InlineKeyboardMarkup | None = None) -> bool:
    try:
        await bot.send_message(chat_id, reply_markup=reply_markup, **rich.kwargs())
        return True
    except TelegramAPIError as exc:
        logger.warning("send failed", extra={"chat_id": chat_id, "error": type(exc).__name__})
        return False


async def notify_admins(bot: Bot, admin_ids: Iterable[int], text: str) -> None:
    for admin_id in admin_ids:
        try:
            await bot.send_message(admin_id, text, parse_mode=None)
        except TelegramAPIError as exc:
            logger.warning("admin notify failed", extra={"admin_id": admin_id, "error": type(exc).__name__})
