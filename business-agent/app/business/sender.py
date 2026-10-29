"""Отправка сообщений от имени бизнес-аккаунта с честной обработкой ошибок.

Повтор выполняется только при RetryAfter (сообщение точно не отправлено). При сетевой
ошибке результат неизвестен — повтор мог бы продублировать сообщение, поэтому не повторяем.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot
from aiogram.exceptions import (
    TelegramBadRequest,
    TelegramForbiddenError,
    TelegramNetworkError,
    TelegramRetryAfter,
)

logger = logging.getLogger(__name__)


@dataclass
class SendResult:
    ok: bool
    message_id: int | None = None
    error: str | None = None
    kind: str | None = None  # no_rights | chat_unavailable | forbidden | network | bad_request


def classify_bad_request(text: str) -> str:
    t = text.lower()
    if "not enough rights" in t or "business_peer_usage_missing" in t or "bot_access_forbidden" in t:
        return "no_rights"
    if "chat not found" in t or "peer_id_invalid" in t or "user not found" in t or "business_peer_invalid" in t:
        return "chat_unavailable"
    return "bad_request"


class BusinessSender:
    def __init__(self, bot: Bot, max_retry_after: int = 2) -> None:
        self.bot = bot
        self.max_retry_after = max_retry_after

    async def _call(self, coro_factory) -> SendResult:
        for _ in range(self.max_retry_after + 1):
            try:
                msg = await coro_factory()
                return SendResult(True, message_id=getattr(msg, "message_id", None))
            except TelegramRetryAfter as exc:
                await asyncio.sleep(min(exc.retry_after, 60))
            except TelegramForbiddenError as exc:
                return SendResult(False, error=exc.message, kind="forbidden")
            except TelegramBadRequest as exc:
                return SendResult(False, error=exc.message, kind=classify_bad_request(exc.message))
            except TelegramNetworkError as exc:
                return SendResult(False, error=f"сеть: {exc.message}; доставка неизвестна", kind="network")
        return SendResult(False, error="Telegram ограничил частоту отправки", kind="flood")

    async def send_text(self, connection_id: str, chat_id: int, text: str) -> SendResult:
        return await self._call(lambda: self.bot.send_message(
            chat_id, text, business_connection_id=connection_id, parse_mode=None))

    async def send_media(self, connection_id: str, chat_id: int, kind: str, file_id: str) -> SendResult:
        method = {"sticker": self.bot.send_sticker, "animation": self.bot.send_animation,
                  "photo": self.bot.send_photo, "video": self.bot.send_video}.get(kind)
        if method is None:
            return SendResult(False, error=f"тип {kind} не поддерживается", kind="bad_request")
        return await self._call(lambda: method(chat_id, file_id, business_connection_id=connection_id))

    async def delete(self, connection_id: str, message_ids: list[int]) -> SendResult:
        try:
            await self.bot.delete_business_messages(business_connection_id=connection_id, message_ids=message_ids)
            return SendResult(True)
        except TelegramBadRequest as exc:
            return SendResult(False, error=exc.message, kind=classify_bad_request(exc.message))
        except (TelegramForbiddenError, TelegramNetworkError) as exc:
            return SendResult(False, error=exc.message, kind="forbidden")
