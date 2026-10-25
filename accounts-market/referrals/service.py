"""Referral program: attaching invitees and paying rewards for their purchases."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Order, OrderStatus, Transaction, TxKind, User
from services.ledger import change_balance
from services.shop_settings import ShopSettings

REF_PREFIX = "ref_"


def referral_link(bot_username: str, user: User) -> str:
    return f"https://t.me/{bot_username}?start={REF_PREFIX}{user.ref_code}"


def parse_start_arg(arg: str | None) -> str | None:
    if arg and arg.startswith(REF_PREFIX):
        code = arg[len(REF_PREFIX):]
        if code.isalnum() and len(code) <= 16:
            return code
    return None


async def attach_referrer(session: AsyncSession, user: User, code: str, *, is_new: bool) -> User | None:
    """Links a freshly registered user to the owner of `code`.

    Only new users can be attached (no re-assigning an existing account to a
    different inviter), and a user can never invite themselves.
    """
    if not is_new or user.referrer_id is not None:
        return None
    referrer = await session.scalar(select(User).where(User.ref_code == code))
    if referrer is None or referrer.id == user.id:
        return None
    user.referrer_id = referrer.id
    await session.flush()
    return referrer


def reward_amount(price: int, percent: float) -> int:
    return int(price * percent) // 100


async def reward_for_order(
    session: AsyncSession, order: Order, buyer: User, settings: ShopSettings
) -> Transaction | None:
    """Credits the inviter inside the purchase transaction.

    Idempotent: the ledger allows a single `referral` row per order.
    """
    if buyer.referrer_id is None or settings.referral_percent <= 0:
        return None
    if settings.referral_mode == "first":
        previous = await session.scalar(
            select(func.count(Order.id)).where(Order.user_id == buyer.id, Order.id != order.id)
        )
        if previous:
            return None
    amount = reward_amount(order.price, settings.referral_percent)
    if amount <= 0:
        return None
    return await change_balance(
        session,
        buyer.referrer_id,
        amount,
        TxKind.REFERRAL,
        order_id=order.id,
        comment=f"{settings.referral_percent:g}% с заказа {order.number}",
    )


@dataclass(frozen=True)
class RewardRow:
    created_at: datetime
    amount: int
    order_id: int


async def reward_history(session: AsyncSession, user_id: int, limit: int, offset: int) -> tuple[list[RewardRow], int]:
    base = select(Transaction).where(Transaction.user_id == user_id, Transaction.kind == TxKind.REFERRAL)
    total = await session.scalar(select(func.count()).select_from(base.subquery()))
    rows = (
        await session.execute(base.order_by(Transaction.id.desc()).limit(limit).offset(offset))
    ).scalars()
    return [RewardRow(r.created_at, r.amount, r.order_id or 0) for r in rows], int(total or 0)


async def has_completed_orders(session: AsyncSession, user_id: int) -> bool:
    return bool(
        await session.scalar(
            select(func.count(Order.id)).where(Order.user_id == user_id, Order.status == OrderStatus.COMPLETED)
        )
    )
