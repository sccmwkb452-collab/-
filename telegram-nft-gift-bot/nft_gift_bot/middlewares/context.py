"""Per-update DB session, user context, emoji overrides and rate limiting."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from nft_gift_bot.config.settings import Settings
from nft_gift_bot.database.base import utcnow
from nft_gift_bot.services.rate_limit import SlidingWindowRateLimiter
from nft_gift_bot.services.settings_service import SettingsService
from nft_gift_bot.services.user_service import UserService

logger = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class DbSessionMiddleware(BaseMiddleware):
    """Opens one transaction per update: commit on success, rollback on any error."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = session_factory

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        async with self._factory() as session:
            data["session"] = session
            try:
                result = await handler(event, data)
            except Exception:
                await session.rollback()
                raise
            await session.commit()
            return result


class EmojiMiddleware(BaseMiddleware):
    """Loads admin emoji overrides, cached briefly to avoid a query per update."""

    def __init__(self, settings: Settings, ttl_seconds: float = 30.0) -> None:
        self._settings = settings
        self._ttl = ttl_seconds
        self._cached: dict[str, str] = {}
        self._loaded_at = 0.0

    def invalidate(self) -> None:
        self._loaded_at = 0.0

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        if time.monotonic() - self._loaded_at > self._ttl:
            self._cached = await SettingsService(data["session"], self._settings).emoji_overrides()
            self._loaded_at = time.monotonic()
        data["emoji"] = self._cached
        data["emoji_cache"] = self
        return await handler(event, data)


class UserContextMiddleware(BaseMiddleware):
    """Registers the sender, blocks banned users and applies rate limits.

    Applied to messages and callback queries only.
    """

    def __init__(self, limiter: SlidingWindowRateLimiter) -> None:
        self._limiter = limiter

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = getattr(event, "from_user", None)
        if tg_user is None or tg_user.is_bot:
            return None
        if not self._limiter.allow(tg_user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("Слишком много запросов. Подождите минуту.", show_alert=False)
            elif isinstance(event, Message):
                logger.info("rate limited", extra={"user_id": tg_user.id})
            return None
        user = await UserService(data["session"]).ensure(tg_user.id, tg_user.username, tg_user.first_name, utcnow())
        if user.is_blocked:
            if isinstance(event, CallbackQuery):
                await event.answer("Доступ ограничен.", show_alert=True)
            return None
        data["db_user"] = user
        return await handler(event, data)
