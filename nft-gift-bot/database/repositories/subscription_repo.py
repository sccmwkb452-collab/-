from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.subscription import Subscription, SubscriptionStatus
from database.repositories.base import BaseRepository


class SubscriptionRepository(BaseRepository[Subscription]):
    model = Subscription

    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session)

    async def get_active(self, user_id: int) -> Subscription | None:
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            select(Subscription)
            .where(
                Subscription.user_id == user_id,
                Subscription.status == SubscriptionStatus.ACTIVE,
                (Subscription.expires_at == None) | (Subscription.expires_at > now),  # noqa: E711
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_user(
        self, user_id: int, limit: int = 10
    ) -> list[Subscription]:
        result = await self._session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .order_by(Subscription.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def expire_outdated(self) -> int:
        """Помечает просроченные подписки как EXPIRED. Возвращает кол-во обновлённых."""
        from sqlalchemy import update
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            update(Subscription)
            .where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at <= now,
                Subscription.expires_at != None,  # noqa: E711
            )
            .values(status=SubscriptionStatus.EXPIRED)
        )
        await self._session.flush()
        return result.rowcount
