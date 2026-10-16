from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database.models import User


class UserMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")

        if tg_user and session:
            result = await session.execute(
                select(User).where(User.telegram_id == tg_user.id)
            )
            user = result.scalar_one_or_none()

            if user is None:
                user = User(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    first_name=tg_user.first_name or "Unknown",
                    last_name=tg_user.last_name,
                    language_code=tg_user.language_code,
                    is_bot=tg_user.is_bot,
                )
                session.add(user)
                await session.flush()
            else:
                # Sync profile changes
                user.username = tg_user.username
                user.first_name = tg_user.first_name or user.first_name
                user.last_name = tg_user.last_name

            data["user"] = user

        return await handler(event, data)
