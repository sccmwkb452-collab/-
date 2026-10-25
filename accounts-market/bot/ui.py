"""Screen rendering: navigation edits one message instead of sending new ones."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from bot import media

log = logging.getLogger(__name__)

CAPTION_LIMIT = 1024
TEXT_LIMIT = 4096


@dataclass
class Screen:
    text: str
    kb: InlineKeyboardMarkup | None = None
    photo: tuple[str, str | BufferedInputFile] | None = None  # (cache key, file_id or upload)


class _NeedNewMessage(Exception):
    pass


def _not_modified(exc: TelegramBadRequest) -> bool:
    return "message is not modified" in exc.message


async def show(event: Message | CallbackQuery, screen: Screen, *, new: bool = False) -> Message | None:
    """Edits the message the button belongs to; sends a new one when editing is impossible."""
    if screen.photo and len(screen.text) > CAPTION_LIMIT:
        screen = Screen(screen.text, screen.kb, None)  # long screens go as text
    if len(screen.text) > TEXT_LIMIT:
        screen = Screen(screen.text[: TEXT_LIMIT - 1] + "…", screen.kb, None)

    bot: Bot = event.bot  # type: ignore[assignment]
    if isinstance(event, CallbackQuery):
        chat_id = event.from_user.id
        message = event.message if isinstance(event.message, Message) else None
        if message is not None:
            chat_id = message.chat.id
        if message is not None and not new:
            try:
                return await _edit(message, screen)
            except TelegramBadRequest as exc:
                if _not_modified(exc):
                    return message
                log.debug("edit failed, sending new message: %s", exc.message)
            except _NeedNewMessage:
                pass
            sent = await _send(bot, chat_id, screen)
            try:
                await message.delete()
            except TelegramBadRequest:
                pass  # older than 48h or already deleted: leave it
            return sent
        return await _send(bot, chat_id, screen)
    return await _send(bot, event.chat.id, screen)


async def _edit(message: Message, screen: Screen) -> Message:
    has_photo = bool(message.photo)
    if screen.photo and has_photo:
        key, file = screen.photo
        result = await message.edit_media(
            InputMediaPhoto(media=file, caption=screen.text), reply_markup=screen.kb
        )
        media.remember(key, result)
        return result if isinstance(result, Message) else message
    if not screen.photo and not has_photo and message.text is not None:
        result = await message.edit_text(screen.text, reply_markup=screen.kb)
        return result if isinstance(result, Message) else message
    raise _NeedNewMessage  # photo <-> text switch cannot be done by editing


async def _send(bot: Bot, chat_id: int, screen: Screen) -> Message:
    # One retry on a dropped connection: large banner uploads occasionally hit it.
    for attempt in (1, 2):
        try:
            if screen.photo:
                key, file = screen.photo
                sent = await bot.send_photo(chat_id, file, caption=screen.text, reply_markup=screen.kb)
                media.remember(key, sent)
                return sent
            return await bot.send_message(chat_id, screen.text, reply_markup=screen.kb)
        except TelegramNetworkError:
            if attempt == 2:
                raise
            log.warning("network error while sending a screen, retrying")
            await asyncio.sleep(1)
    raise AssertionError("unreachable")
