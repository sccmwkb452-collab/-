from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import User
from nft_gift_bot.repositories import UserRepository


class UserService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = UserRepository(session)

    async def ensure(self, telegram_id: int, username: str | None, first_name: str | None, now: datetime) -> User:
        return await self._repo.upsert(
            telegram_id, (username or None) and username[:64], (first_name or None) and first_name[:128], now
        )

    async def by_telegram_id(self, telegram_id: int) -> User | None:
        return await self._repo.get_by_telegram_id(telegram_id)

    async def get(self, user_id: int) -> User | None:
        return await self._repo.get(user_id)
