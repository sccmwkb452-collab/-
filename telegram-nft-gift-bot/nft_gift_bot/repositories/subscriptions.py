from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import Subscription, SubscriptionStatus


class SubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_user(self, user_id: int) -> Subscription | None:
        return await self.session.scalar(select(Subscription).where(Subscription.user_id == user_id))

    def add(self, subscription: Subscription) -> None:
        self.session.add(subscription)

    async def list_active_expired_by(self, now: datetime) -> list[Subscription]:
        result = await self.session.scalars(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at <= now
            )
        )
        return list(result)

    async def list_needing_warning(self, now: datetime, until: datetime) -> list[Subscription]:
        result = await self.session.scalars(
            select(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.expires_at > now,
                Subscription.expires_at <= until,
                Subscription.expiry_notified_at.is_(None),
            )
        )
        return list(result)

    async def count_active(self, now: datetime) -> int:
        return int(
            await self.session.scalar(
                select(func.count(Subscription.id)).where(
                    Subscription.status == SubscriptionStatus.ACTIVE, Subscription.expires_at > now
                )
            )
            or 0
        )
