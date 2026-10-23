from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject
from aiogram.types import User as TgUser

from ..database.session import get_sessionmaker
from ..services.app_settings import load_runtime_settings
from ..services.users import upsert_telegram_user
from ..shared.telegram_auth import TelegramUser


class DbMiddleware(BaseMiddleware):
    """Opens a DB session per update, loads runtime settings and the shop
    user (created on first contact; /start payload drives referrals)."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg: TgUser | None = data.get("event_from_user")
        async with get_sessionmaker()() as session:
            runtime = await load_runtime_settings(session)
            data["session"] = session
            data["runtime"] = runtime
            if tg is not None and not tg.is_bot:
                start_param = None
                if isinstance(event, Message) and event.text and event.text.startswith("/start "):
                    start_param = event.text.split(maxsplit=1)[1].strip()[:64]
                user, _ = await upsert_telegram_user(
                    session,
                    TelegramUser(
                        id=tg.id,
                        first_name=tg.first_name or "",
                        last_name=tg.last_name,
                        username=tg.username,
                        language_code=tg.language_code,
                        is_premium=bool(tg.is_premium),
                    ),
                    runtime=runtime,
                    start_param=start_param,
                    bot_started=True,
                )
                data["db_user"] = user
            try:
                result = await handler(event, data)
                await session.commit()
                return result
            except BaseException:
                await session.rollback()
                raise
