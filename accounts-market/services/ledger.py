"""Balance changes. Every change goes through here and leaves a ledger row."""

from __future__ import annotations

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Transaction, User
from services.errors import InsufficientFunds


async def change_balance(
    session: AsyncSession,
    user_id: int,
    amount: int,
    kind: str,
    *,
    order_id: int | None = None,
    payment_id: int | None = None,
    admin_id: int | None = None,
    comment: str | None = None,
) -> Transaction:
    """Atomically adds `amount` (may be negative) to the balance.

    The UPDATE itself refuses to go below zero, so concurrent debits can never
    overdraw. Duplicate credits for the same order/payment are rejected by the
    partial unique indexes on `transactions` (IntegrityError).
    """
    result = await session.execute(
        update(User)
        .where(User.id == user_id, User.balance + amount >= 0)
        .values(balance=User.balance + amount)
        .returning(User.balance)
    )
    new_balance = result.scalar_one_or_none()
    if new_balance is None:
        raise InsufficientFunds()
    tx = Transaction(
        user_id=user_id,
        amount=amount,
        balance_after=new_balance,
        kind=kind,
        order_id=order_id,
        payment_id=payment_id,
        admin_id=admin_id,
        comment=comment,
    )
    session.add(tx)
    await session.flush()
    return tx
