from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import Subscription, SubscriptionStatus
from nft_gift_bot.repositories import SubscriptionRepository


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SubscriptionRepository(session)

    async def get(self, user_id: int) -> Subscription | None:
        return await self._repo.get_by_user(user_id)

    async def is_active(self, user_id: int, now: datetime) -> bool:
        sub = await self._repo.get_by_user(user_id)
        return sub is not None and sub.status == SubscriptionStatus.ACTIVE and sub.expires_at > now

    async def extend(self, user_id: int, days: int, now: datetime) -> Subscription:
        """Activate or renew. Renewal of an active subscription stacks on top of the remaining time."""
        if days <= 0:
            raise ValueError("days must be positive")
        sub = await self._repo.get_by_user(user_id)
        if sub is None:
            sub = Subscription(user_id=user_id, starts_at=now, expires_at=now + timedelta(days=days))
            self._repo.add(sub)
        else:
            still_active = sub.status == SubscriptionStatus.ACTIVE and sub.expires_at > now
            base = sub.expires_at if still_active else now
            if not still_active:
                sub.starts_at = now
            sub.expires_at = base + timedelta(days=days)
            sub.status = SubscriptionStatus.ACTIVE
            sub.expiry_notified_at = None
        return sub

    async def expire_due(self, now: datetime) -> list[Subscription]:
        expired = await self._repo.list_active_expired_by(now)
        for sub in expired:
            sub.status = SubscriptionStatus.EXPIRED
        return expired

    async def take_expiry_warnings(self, now: datetime, window: timedelta) -> list[Subscription]:
        due = await self._repo.list_needing_warning(now, now + window)
        for sub in due:
            sub.expiry_notified_at = now
        return due

    async def count_active(self, now: datetime) -> int:
        return await self._repo.count_active(now)
