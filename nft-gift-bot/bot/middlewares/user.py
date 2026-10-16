from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject, User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from services.user_service import UserService


class UserMiddleware(BaseMiddleware):
    """
    Авто-регистрирует пользователя и кладёт объект User в data['db_user'].
    Зависит от DatabaseMiddleware (должен идти после него).
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user: TgUser | None = data.get("event_from_user")
        session: AsyncSession | None = data.get("session")

        if tg_user and not tg_user.is_bot and session:
            service = UserService(session)
            db_user, _ = await service.register_or_update(tg_user)
            data["db_user"] = db_user

        return await handler(event, data)
