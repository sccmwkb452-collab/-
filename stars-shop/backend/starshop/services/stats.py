"""Dashboard metrics.

Terminology (shown in the UI as well):
* turnover — money captured for orders paid in the period (gross);
* refunds — money returned for orders refunded in the period;
* profit — for completed orders that have cost data:
  total − cost; orders without cost data are excluded and counted;
* cash balance — what the payment providers report, if their API allows.
DEMO orders are excluded from money metrics unless explicitly requested.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from sqlalchemy import and_, distinct, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import DeliveryStatus, OrderStatus, PaymentStatus, ShopMode, WebhookStatus
from ..database.models import DeliveryTask, Order, Payment, PaymentWebhookEvent, User, UserActivityDay
from ..shared.money import money
from ..shared.timeutil import utcnow

PERIODS = {"day": 1, "week": 7, "month": 30, "quarter": 90}


@dataclass(slots=True)
class Period:
    start: datetime
    end: datetime
    days: int


def period_for(name: str) -> Period:
    days = PERIODS.get(name, 7)
    tz = ZoneInfo(get_settings().display_timezone)
    now_local = utcnow().astimezone(tz)
    start_local = (now_local - timedelta(days=days - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    return Period(start=start_local, end=utcnow() + timedelta(seconds=1), days=days)


def _mode_filter(include_demo: bool):
    return literal(True) if include_demo else Order.mode == ShopMode.production


async def dashboard(session: AsyncSession, period_name: str, include_demo: bool = False) -> dict:
    p = period_for(period_name)
    mode = _mode_filter(include_demo)
    in_period = lambda col: and_(col >= p.start, col < p.end)  # noqa: E731

    users_total = await session.scalar(select(func.count()).select_from(User)) or 0
    users_new = await session.scalar(select(func.count()).select_from(User).where(in_period(User.created_at))) or 0
    orders_created = await session.scalar(select(func.count()).select_from(Order).where(mode, in_period(Order.created_at))) or 0
    paid_row = (
        await session.execute(select(func.count(), func.coalesce(func.sum(Order.total), 0)).where(mode, in_period(Order.paid_at)))
    ).one()
    paid_count, turnover = int(paid_row[0]), Decimal(paid_row[1])
    refunds = Decimal(await session.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(mode, in_period(Order.refunded_at))) or 0)

    completed_q = select(
        func.count(),
        func.count(Order.cost_amount),
        func.coalesce(func.sum(Order.total).filter(Order.cost_amount.is_not(None)), 0),
        func.coalesce(func.sum(Order.cost_amount), 0),
    ).where(mode, Order.status == OrderStatus.completed, in_period(Order.completed_at))
    completed_count, with_cost, revenue_with_cost, cost_sum = (await session.execute(completed_q)).one()

    active_users = (
        await session.scalar(select(func.count(distinct(UserActivityDay.user_id))).where(UserActivityDay.day >= p.start.date())) or 0
    )
    paying_users = await session.scalar(select(func.count(distinct(Order.user_id))).where(mode, in_period(Order.paid_at))) or 0

    in_processing = (
        await session.scalar(
            select(func.count()).select_from(Order).where(mode, Order.status.in_((OrderStatus.paid, OrderStatus.processing)))
        )
        or 0
    )
    awaiting_payment = (
        await session.scalar(
            select(func.count()).select_from(Order).where(mode, Order.status.in_((OrderStatus.created, OrderStatus.pending_payment)))
        )
        or 0
    )
    needs_attention = (
        await session.scalar(select(func.count()).select_from(DeliveryTask).where(DeliveryTask.status == DeliveryStatus.needs_attention))
        or 0
    )
    failed_orders = await session.scalar(select(func.count()).select_from(Order).where(mode, Order.status == OrderStatus.failed)) or 0
    payment_errors = (
        await session.scalar(
            select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.failed, in_period(Payment.updated_at))
        )
        or 0
    )
    webhook_errors = (
        await session.scalar(
            select(func.count())
            .select_from(PaymentWebhookEvent)
            .where(
                PaymentWebhookEvent.status.in_((WebhookStatus.rejected, WebhookStatus.failed)), in_period(PaymentWebhookEvent.received_at)
            )
        )
        or 0
    )
    refund_pending = (
        await session.scalar(select(func.count()).select_from(Payment).where(Payment.status == PaymentStatus.refund_pending)) or 0
    )

    return {
        "period": {"name": period_name, "start": p.start.isoformat(), "end": p.end.isoformat(), "include_demo": include_demo},
        "currency": get_settings().shop_currency,
        "users": {"total": users_total, "new": users_new, "active": active_users, "paying": paying_users},
        "orders": {
            "created": orders_created,
            "paid": paid_count,
            "completed": int(completed_count),
            "in_processing": in_processing,
            "awaiting_payment": awaiting_payment,
        },
        "money": {
            "turnover": str(money(turnover)),
            "refunds": str(money(refunds)),
            "net_turnover": str(money(turnover - refunds)),
            "average_check": str(money(turnover / paid_count)) if paid_count else None,
            "profit": str(money(Decimal(revenue_with_cost) - Decimal(cost_sum))) if with_cost else None,
            "profit_orders_with_cost": int(with_cost),
            "profit_orders_total": int(completed_count),
        },
        "conversion": (round(paying_users / active_users * 100, 1) if active_users else None),
        "problems": {
            "delivery_needs_attention": needs_attention,
            "delivery_failed": failed_orders,
            "payment_errors": payment_errors,
            "webhook_rejected": webhook_errors,
            "refund_pending": refund_pending,
        },
    }


async def sales_series(session: AsyncSession, granularity: str, points: int, include_demo: bool = False) -> list[dict]:
    if granularity not in ("day", "week", "month"):
        granularity = "day"
    tz_name = get_settings().display_timezone
    tz = ZoneInfo(tz_name)
    now_local = utcnow().astimezone(tz)
    if granularity == "day":
        start_local = (now_local - timedelta(days=points - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
    elif granularity == "week":
        start_local = (now_local - timedelta(weeks=points - 1)).replace(hour=0, minute=0, second=0, microsecond=0)
        start_local -= timedelta(days=start_local.weekday())
    else:
        y, m = now_local.year, now_local.month - (points - 1)
        while m <= 0:
            m += 12
            y -= 1
        start_local = now_local.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)

    bucket = func.date_trunc(granularity, func.timezone(tz_name, Order.paid_at)).label("bucket")
    rows = (
        await session.execute(
            select(bucket, func.count(), func.coalesce(func.sum(Order.total), 0))
            .where(_mode_filter(include_demo), Order.paid_at >= start_local)
            .group_by(bucket)
            .order_by(bucket)
        )
    ).all()
    by_bucket = {r[0].date(): (int(r[1]), Decimal(r[2])) for r in rows}

    result = []
    cursor = start_local.date()
    for _ in range(points):
        orders, revenue = by_bucket.get(cursor, (0, Decimal(0)))
        result.append({"bucket": cursor.isoformat(), "orders": orders, "turnover": str(money(revenue))})
        if granularity == "day":
            cursor = cursor + timedelta(days=1)
        elif granularity == "week":
            cursor = cursor + timedelta(weeks=1)
        else:
            cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return result
