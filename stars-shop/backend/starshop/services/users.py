from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, literal_column, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import get_settings
from ..database.enums import OrderStatus, ReferralStatus
from ..database.models import Order, Referral, User, UserActivityDay
from ..shared.ids import referral_code
from ..shared.telegram_auth import TelegramUser
from ..shared.timeutil import to_local, utcnow
from . import referrals
from .app_settings import RuntimeSettings

# Postgres trick: xmax = 0 only for a row inserted (not updated) by the upsert.
_INSERTED = literal_column("(xmax = 0)").label("inserted")

# Orders whose money was captured and not returned.
SPENT_STATUSES = (OrderStatus.paid, OrderStatus.processing, OrderStatus.completed, OrderStatus.failed)


async def upsert_telegram_user(
    session: AsyncSession,
    tg: TelegramUser,
    *,
    runtime: RuntimeSettings,
    start_param: str | None = None,
    bot_started: bool = False,
    track_activity: bool = False,
) -> tuple[User, bool]:
    """Create or refresh a user from *verified* Telegram data.

    Returns ``(user, created)``. Referral codes are attached only for newly
    created users."""
    now = utcnow()
    profile = {
        "username": tg.username,
        "first_name": (tg.first_name or "")[:128],
        "last_name": (tg.last_name or None) and tg.last_name[:128],
        "language_code": tg.language_code,
        "is_premium": tg.is_premium,
        "last_seen_at": now,
    }
    if tg.photo_url:
        profile["photo_url"] = tg.photo_url
    if bot_started:
        profile["bot_started"] = True

    for _ in range(5):
        stmt = (
            insert(User)
            .values(telegram_id=tg.id, referral_code=referral_code(), first_seen_at=now, **profile)
            .on_conflict_do_update(index_elements=[User.telegram_id], set_=profile)
            .returning(User.id, _INSERTED)
        )
        try:
            async with session.begin_nested():
                row = (await session.execute(stmt)).one()
            break
        except IntegrityError:  # referral_code collision, retry with a new one
            continue
    else:  # pragma: no cover - astronomically unlikely
        raise RuntimeError("could not allocate referral code")

    user_id, created = row
    user = (await session.execute(select(User).where(User.id == user_id).execution_options(populate_existing=True))).scalar_one()
    if created:
        await referrals.attach(session, user, start_param, runtime)
    if track_activity:
        day = to_local(now, get_settings().display_timezone).date()
        await session.execute(insert(UserActivityDay).values(user_id=user.id, day=day).on_conflict_do_nothing())
    return user, bool(created)


@dataclass(slots=True)
class UserStats:
    orders_count: int
    completed_count: int
    total_spent: Decimal
    last_order: Order | None
    invited_count: int
    rewarded_count: int
    first_seen_at: datetime


async def user_stats(session: AsyncSession, user: User) -> UserStats:
    orders_count = await session.scalar(
        select(func.count()).select_from(Order).where(Order.user_id == user.id, Order.status != OrderStatus.cancelled)
    )
    completed = await session.scalar(
        select(func.count()).select_from(Order).where(Order.user_id == user.id, Order.status == OrderStatus.completed)
    )
    spent = await session.scalar(
        select(func.coalesce(func.sum(Order.total), 0)).where(Order.user_id == user.id, Order.status.in_(SPENT_STATUSES))
    )
    last_order = (
        await session.execute(select(Order).where(Order.user_id == user.id).order_by(Order.created_at.desc()).limit(1))
    ).scalar_one_or_none()
    invited = await session.scalar(select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id))
    rewarded = await session.scalar(
        select(func.count()).select_from(Referral).where(Referral.referrer_id == user.id, Referral.status == ReferralStatus.rewarded)
    )
    return UserStats(
        orders_count=orders_count or 0,
        completed_count=completed or 0,
        total_spent=Decimal(spent or 0),
        last_order=last_order,
        invited_count=invited or 0,
        rewarded_count=rewarded or 0,
        first_seen_at=user.first_seen_at,
    )


def referral_link(user: User) -> str | None:
    s = get_settings()
    if not s.bot_username:
        return None
    if s.webapp_short_name:
        return f"https://t.me/{s.bot_username}/{s.webapp_short_name}?startapp=ref_{user.referral_code}"
    return f"https://t.me/{s.bot_username}?start=ref_{user.referral_code}"
