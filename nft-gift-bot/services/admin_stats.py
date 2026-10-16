"""Admin statistics service — aggregated counts for the panel."""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.payment import TonPayment, TonPaymentStatus
from database.models.shop import OrderStatus, ShopOrder
from database.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from database.models.user import User


@dataclass
class AdminStats:
    total_users: int = 0
    active_subs_total: int = 0
    active_subs_basic: int = 0
    active_subs_premium: int = 0
    pending_payments: int = 0
    confirmed_payments_30d: int = 0
    revenue_ton_30d: float = 0.0
    shop_orders_pending: int = 0
    shop_orders_paid: int = 0
    shop_orders_delivered: int = 0


class AdminStatsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_stats(self) -> AdminStats:
        now = datetime.now(tz=timezone.utc)
        since_30d = now - timedelta(days=30)
        stats = AdminStats()

        # Total users
        r = await self._session.execute(select(func.count()).select_from(User))
        stats.total_users = r.scalar_one()

        # Active subscriptions
        r = await self._session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                (Subscription.expires_at == None) | (Subscription.expires_at > now),  # noqa: E711
            )
        )
        stats.active_subs_total = r.scalar_one()

        r = await self._session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.plan == SubscriptionPlan.BASIC,
                (Subscription.expires_at == None) | (Subscription.expires_at > now),  # noqa: E711
            )
        )
        stats.active_subs_basic = r.scalar_one()

        r = await self._session.execute(
            select(func.count()).select_from(Subscription).where(
                Subscription.status == SubscriptionStatus.ACTIVE,
                Subscription.plan == SubscriptionPlan.PREMIUM,
                (Subscription.expires_at == None) | (Subscription.expires_at > now),  # noqa: E711
            )
        )
        stats.active_subs_premium = r.scalar_one()

        # Pending TON payments
        r = await self._session.execute(
            select(func.count()).select_from(TonPayment).where(
                TonPayment.status == TonPaymentStatus.PENDING
            )
        )
        stats.pending_payments = r.scalar_one()

        # Confirmed payments in last 30d
        r = await self._session.execute(
            select(func.count()).select_from(TonPayment).where(
                TonPayment.status == TonPaymentStatus.CONFIRMED,
                TonPayment.confirmed_at >= since_30d,
            )
        )
        stats.confirmed_payments_30d = r.scalar_one()

        # Revenue last 30d (from confirmed subscription payments — amount_nanoton / 1e9)
        r = await self._session.execute(
            select(func.sum(TonPayment.amount_nanoton)).where(
                TonPayment.status == TonPaymentStatus.CONFIRMED,
                TonPayment.confirmed_at >= since_30d,
            )
        )
        nanoton_sum = r.scalar_one() or 0
        stats.revenue_ton_30d = nanoton_sum / 1_000_000_000

        # Shop orders by status
        for status, attr in [
            (OrderStatus.PENDING, "shop_orders_pending"),
            (OrderStatus.PAID, "shop_orders_paid"),
            (OrderStatus.DELIVERED, "shop_orders_delivered"),
        ]:
            r = await self._session.execute(
                select(func.count()).select_from(ShopOrder).where(
                    ShopOrder.status == status
                )
            )
            setattr(stats, attr, r.scalar_one())

        return stats
