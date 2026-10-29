from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject, Update

from app.core.dedup import claim_update
from app.core.owners import get_or_create_owner


class DedupMiddleware(BaseMiddleware):
    """Повторно доставленное обновление (рестарт, ретраи Telegram) не обрабатывается дважды."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]], event: Update,
                       data: dict[str, Any]) -> Any:
        key = f"{self.ctx.bot.id}:{event.update_id}"
        if not await claim_update(self.ctx.sessions, key):
            return None
        return await handler(event, data)


class PanelMiddleware(BaseMiddleware):
    """Доступ к панели — только по Telegram ID из ADMIN_IDS / ALLOWED_USER_IDS.
    Открывает сессию БД и загружает владельца."""

    def __init__(self, ctx) -> None:
        self.ctx = ctx

    async def __call__(self, handler, event: TelegramObject, data: dict[str, Any]) -> Any:
        user = getattr(event, "from_user", None)
        if isinstance(event, Message) and event.business_connection_id:
            return await handler(event, data)  # бизнес-сообщения обрабатывает отдельный роутер
        if user is None or not self.ctx.settings.can_use_panel(user.id):
            if isinstance(event, CallbackQuery):
                await event.answer("Нет доступа", show_alert=True)
            elif isinstance(event, Message) and event.chat.type == "private":
                await event.answer("⛔️ Доступ к панели не выдан. Обратитесь к администратору.")
            return None
        async with self.ctx.sessions() as session:
            data["session"] = session
            data["owner"] = await get_or_create_owner(session, user.id, user.first_name, user.username)
            data["ctx"] = self.ctx
            data["is_admin"] = self.ctx.settings.is_admin(user.id)
            result = await handler(event, data)
            await session.commit()
            return result
