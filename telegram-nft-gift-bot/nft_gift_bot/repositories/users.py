from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        return await self.session.scalar(select(User).where(User.telegram_id == telegram_id))

    async def upsert(
        self, telegram_id: int, username: str | None, first_name: str | None, now: datetime
    ) -> User:
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(telegram_id=telegram_id, username=username, first_name=first_name, last_seen_at=now)
            self.session.add(user)
            await self.session.flush()
        else:
            user.username = username
            user.first_name = first_name
            user.last_seen_at = now
        return user

    async def list_recent(self, limit: int = 20) -> list[User]:
        result = await self.session.scalars(select(User).order_by(User.id.desc()).limit(limit))
        return list(result)

    async def count(self) -> int:
        return int(await self.session.scalar(select(func.count(User.id))) or 0)
