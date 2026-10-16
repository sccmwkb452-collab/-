from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.user import User
from database.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        result = await self._session.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def get_or_create(
        self,
        telegram_id: int,
        first_name: str,
        username: str | None = None,
        last_name: str | None = None,
        language_code: str | None = None,
        is_bot: bool = False,
    ) -> tuple[User, bool]:
        """Возвращает (user, created). created=True если пользователь только что создан."""
        user = await self.get_by_telegram_id(telegram_id)
        if user is not None:
            # Синхронизируем изменившиеся поля профиля
            updated = False
            if user.username != username:
                user.username = username
                updated = True
            if user.first_name != first_name:
                user.first_name = first_name
                updated = True
            if user.last_name != last_name:
                user.last_name = last_name
                updated = True
            if updated:
                await self._session.flush()
            return user, False

        user = await self.create(
            telegram_id=telegram_id,
            first_name=first_name,
            username=username,
            last_name=last_name,
            language_code=language_code,
            is_bot=is_bot,
        )
        return user, True

    async def count_total(self) -> int:
        from sqlalchemy import func
        result = await self._session.execute(
            select(func.count()).select_from(User)
        )
        return result.scalar_one()

    async def set_admin(self, telegram_id: int, is_admin: bool = True) -> User | None:
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.is_admin = is_admin
            await self._session.flush()
        return user
