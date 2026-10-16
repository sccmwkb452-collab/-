import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from database.repositories.subscription_repo import SubscriptionRepository

logger = logging.getLogger(__name__)

PLAN_CONFIG: dict[SubscriptionPlan, dict] = {
    SubscriptionPlan.BASIC: {
        "price_stars": settings.sub_basic_price_stars,
        "duration_days": settings.sub_basic_duration_days,
        "label": "Basic",
    },
    SubscriptionPlan.PREMIUM: {
        "price_stars": settings.sub_premium_price_stars,
        "duration_days": settings.sub_premium_duration_days,
        "label": "Premium",
    },
}


class SubscriptionService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SubscriptionRepository(session)

    def get_plan_info(self, plan: SubscriptionPlan) -> dict:
        return PLAN_CONFIG[plan]

    async def get_active(self, user_id: int) -> Subscription | None:
        return await self._repo.get_active(user_id)

    async def has_active(self, user_id: int) -> bool:
        return await self._repo.get_active(user_id) is not None

    async def create_pending(
        self,
        user_id: int,
        plan: SubscriptionPlan,
        price_paid: float,
        currency: str = "XTR",
    ) -> Subscription:
        sub = await self._repo.create(
            user_id=user_id,
            plan=plan,
            status=SubscriptionStatus.PENDING,
            price_paid=price_paid,
            currency=currency,
        )
        logger.info("Pending subscription created: id=%d, user_id=%d, plan=%s", sub.id, user_id, plan.value)
        return sub

    async def activate(self, subscription: Subscription) -> Subscription:
        config = PLAN_CONFIG[subscription.plan]
        now = datetime.now(tz=timezone.utc)
        return await self._repo.update(
            subscription,
            status=SubscriptionStatus.ACTIVE,
            started_at=now,
            expires_at=now + timedelta(days=config["duration_days"]),
        )

    async def cancel(self, subscription: Subscription) -> Subscription:
        return await self._repo.update(subscription, status=SubscriptionStatus.CANCELLED)

    async def expire_outdated(self) -> int:
        count = await self._repo.expire_outdated()
        if count:
            logger.info("Expired %d subscription(s)", count)
        return count
