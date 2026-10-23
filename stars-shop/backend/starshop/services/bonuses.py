"""Bonus balance with an idempotent ledger.

Each movement has a ``dedup_key``; inserting the same key twice is a no-op,
so retries (webhooks, worker restarts) can never credit or debit twice.
The balance column is updated in the same transaction under a row lock.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import BonusTransaction, User
from ..shared.errors import Conflict
from ..shared.money import money


async def _apply(
    session: AsyncSession,
    user_id: int,
    amount: Decimal,
    *,
    kind: str,
    dedup_key: str,
    order_id: uuid.UUID | None = None,
    referral_id: int | None = None,
    comment: str | None = None,
    allow_partial: bool = False,
) -> Decimal:
    """Returns the amount actually applied (0 if the key was already used)."""
    user = (await session.execute(select(User).where(User.id == user_id).with_for_update())).scalar_one()
    amount = money(amount)
    if amount < 0 and user.bonus_balance + amount < 0:
        if not allow_partial:
            raise Conflict("Недостаточно бонусов", code="insufficient_bonus")
        amount = -user.bonus_balance
    if amount == 0:
        return Decimal("0")
    inserted = (
        await session.execute(
            insert(BonusTransaction)
            .values(
                user_id=user_id,
                amount=amount,
                kind=kind,
                order_id=order_id,
                referral_id=referral_id,
                dedup_key=dedup_key,
                comment=comment,
            )
            .on_conflict_do_nothing(index_elements=[BonusTransaction.dedup_key])
            .returning(BonusTransaction.id)
        )
    ).scalar_one_or_none()
    if inserted is None:
        return Decimal("0")
    user.bonus_balance = money(user.bonus_balance + amount)
    return amount


async def credit(session: AsyncSession, user_id: int, amount: Decimal, **kwargs) -> Decimal:
    if amount <= 0:
        return Decimal("0")
    return await _apply(session, user_id, amount, **kwargs)


async def debit(session: AsyncSession, user_id: int, amount: Decimal, **kwargs) -> Decimal:
    if amount <= 0:
        return Decimal("0")
    return -(await _apply(session, user_id, -amount, **kwargs))


async def spend_for_order(session: AsyncSession, user_id: int, order_id: uuid.UUID, amount: Decimal) -> None:
    await debit(session, user_id, amount, kind="order_spend", dedup_key=f"spend:{order_id}", order_id=order_id)


async def return_for_order(session: AsyncSession, user_id: int, order_id: uuid.UUID, amount: Decimal) -> None:
    """Give back bonuses spent on an order that was cancelled or refunded."""
    await credit(session, user_id, amount, kind="order_return", dedup_key=f"return:{order_id}", order_id=order_id)
