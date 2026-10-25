from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from services import shop_settings, users

log = logging.getLogger(__name__)

Handler = Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]]


class ContextMiddleware(BaseMiddleware):
    """Opens a DB session per update, registers the user and loads shop settings.

    The session is committed after the handler. Services that need their own
    strict transaction (purchases, payments) use the sessionmaker `sm`.
    """

    def __init__(self, sm: async_sessionmaker[AsyncSession], admin_ids: frozenset[int]) -> None:
        self.sm = sm
        self.admin_ids = admin_ids

    async def __call__(self, handler: Handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        tg_user = data.get("event_from_user")
        chat = data.get("event_chat")
        async with self.sm() as session:
            data["session"] = session
            data["sm"] = self.sm
            data["admin_ids"] = self.admin_ids
            data["shop"] = await shop_settings.load(session)
            if tg_user is not None and not tg_user.is_bot and (chat is None or chat.type == "private"):
                user, created = await users.get_or_create(
                    session, tg_user.id, tg_user.username, tg_user.full_name
                )
                if user.bot_blocked:
                    user.bot_blocked = False  # they wrote to us again
                await session.commit()
                data["user"] = user
                data["user_is_new"] = created
                data["is_admin"] = tg_user.id in self.admin_ids
                if user.is_banned and not data["is_admin"]:
                    await self._restricted(event, user.ban_reason)
                    return None
            elif isinstance(event, Update) and (event.message or event.callback_query):
                return None  # groups and channels are not served
            result = await handler(event, data)
            await session.commit()
            return result

    @staticmethod
    async def _restricted(event: TelegramObject, reason: str | None) -> None:
        text = "⛔ Доступ к магазину ограничен." + (f"\nПричина: {reason}" if reason else "")
        inner = event.event if isinstance(event, Update) else event
        if isinstance(inner, CallbackQuery):
            await inner.answer(text, show_alert=True)
        elif isinstance(inner, Message):
            await inner.answer(text)
