from __future__ import annotations

import secrets
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Order, OrderStatus, Transaction, TxKind, User

_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


def new_ref_code() -> str:
    return "".join(secrets.choice(_ALPHABET) for _ in range(8))


async def get_or_create(
    session: AsyncSession, user_id: int, username: str | None, full_name: str
) -> tuple[User, bool]:
    """Returns (user, created). Safe against two first updates arriving at once."""
    full_name = (full_name or "")[:256]
    for _ in range(3):
        stmt = (
            insert(User)
            .values(id=user_id, username=username, full_name=full_name, ref_code=new_ref_code())
            .on_conflict_do_nothing(index_elements=[User.id])
            .returning(User.id)
        )
        try:
            async with session.begin_nested():
                created = (await session.execute(stmt)).scalar_one_or_none() is not None
            break
        except IntegrityError as exc:  # ref_code collision: practically impossible, retry
            if "ref_code" not in str(exc):
                raise
    else:  # pragma: no cover
        raise RuntimeError("could not allocate a referral code")

    if not created:
        await session.execute(
            update(User)
            .where(User.id == user_id)
            .values(username=username, full_name=full_name, last_seen_at=func.now())
        )
    user = await session.get(User, user_id, populate_existing=True)
    assert user is not None
    return user, created


@dataclass(frozen=True)
class ProfileStats:
    purchases: int
    spent: int
    referrals: int
    referrals_with_purchases: int
    referral_earned: int


async def profile_stats(session: AsyncSession, user_id: int) -> ProfileStats:
    purchases, spent = (
        await session.execute(
            select(func.count(Order.id), func.coalesce(func.sum(Order.price), 0)).where(
                Order.user_id == user_id, Order.status == OrderStatus.COMPLETED
            )
        )
    ).one()
    referrals = await session.scalar(select(func.count(User.id)).where(User.referrer_id == user_id))
    buyers = await session.scalar(
        select(func.count(func.distinct(Order.user_id)))
        .join(User, User.id == Order.user_id)
        .where(User.referrer_id == user_id, Order.status == OrderStatus.COMPLETED)
    )
    earned = await session.scalar(
        select(func.coalesce(func.sum(Transaction.amount), 0)).where(
            Transaction.user_id == user_id, Transaction.kind == TxKind.REFERRAL
        )
    )
    return ProfileStats(int(purchases), int(spent), int(referrals or 0), int(buyers or 0), int(earned or 0))


async def find_user(session: AsyncSession, query: str) -> User | None:
    query = query.strip()
    if query.lstrip("-").isdigit():
        return await session.get(User, int(query))
    username = query.lstrip("@").removeprefix("https://t.me/")
    if not username:
        return None
    return await session.scalar(select(User).where(func.lower(User.username) == username.lower()))
