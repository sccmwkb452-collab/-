from aiogram.filters import BaseFilter
from aiogram.types import Message

from config import settings


class AdminFilter(BaseFilter):
    """Пропускает только пользователей из BOT_ADMIN_IDS."""

    async def __call__(self, message: Message) -> bool:
        if not message.from_user:
            return False
        return message.from_user.id in settings.bot_admin_ids
