from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Order, OrderStatus, Payment, PaymentStatus, User


@dataclass(frozen=True)
class Stats:
    users: int
    users_today: int
    users_week: int
    buyers: int
    orders: int
    orders_today: int
    revenue: int
    revenue_today: int
    topups: int
    topups_sum: int
    pending_payments: int
    refunds: int
    refunds_sum: int
    payment_refunds: int
    balances: int
    top: list[tuple[str, int, int]]  # title, sold, revenue


async def collect(session: AsyncSession) -> Stats:
    now = datetime.now(timezone.utc)
    day, week = now - timedelta(days=1), now - timedelta(days=7)

    async def scalar(stmt) -> int:
        return int(await session.scalar(stmt) or 0)

    done = Order.status == OrderStatus.COMPLETED
    top_rows = await session.execute(
        select(Order.product_title, func.count(Order.id), func.sum(Order.price))
        .where(done)
        .group_by(Order.product_title)
        .order_by(func.count(Order.id).desc())
        .limit(5)
    )
    return Stats(
        users=await scalar(select(func.count(User.id))),
        users_today=await scalar(select(func.count(User.id)).where(User.created_at >= day)),
        users_week=await scalar(select(func.count(User.id)).where(User.created_at >= week)),
        buyers=await scalar(select(func.count(func.distinct(Order.user_id))).where(done)),
        orders=await scalar(select(func.count(Order.id)).where(done)),
        orders_today=await scalar(select(func.count(Order.id)).where(done, Order.created_at >= day)),
        revenue=await scalar(select(func.sum(Order.price)).where(done)),
        revenue_today=await scalar(select(func.sum(Order.price)).where(done, Order.created_at >= day)),
        topups=await scalar(select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PAID)),
        topups_sum=await scalar(select(func.sum(Payment.amount)).where(Payment.status == PaymentStatus.PAID)),
        pending_payments=await scalar(select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)),
        refunds=await scalar(select(func.count(Order.id)).where(Order.status == OrderStatus.REFUNDED)),
        refunds_sum=await scalar(select(func.sum(Order.price)).where(Order.status == OrderStatus.REFUNDED)),
        payment_refunds=await scalar(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.REFUNDED)
        ),
        balances=await scalar(select(func.sum(User.balance))),
        top=[(t, int(n), int(s or 0)) for t, n, s in top_rows.all()],
    )
