import logging

from aiogram.types import User as TgUser
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.user import User
from database.repositories.user_repo import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def register_or_update(self, tg_user: TgUser) -> tuple[User, bool]:
        """
        Регистрирует нового пользователя или обновляет данные существующего.
        Возвращает (user, is_new).
        """
        user, is_new = await self._repo.get_or_create(
            telegram_id=tg_user.id,
            first_name=tg_user.first_name or "Unknown",
            username=tg_user.username,
            last_name=tg_user.last_name,
            language_code=tg_user.language_code,
            is_bot=tg_user.is_bot,
        )

        if is_new:
            logger.info(
                "New user registered: telegram_id=%d, username=%r",
                user.telegram_id,
                user.username,
            )

        return user, is_new

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self._repo.get_by_telegram_id(telegram_id)

    async def get_total_users(self) -> int:
        return await self._repo.count_total()
