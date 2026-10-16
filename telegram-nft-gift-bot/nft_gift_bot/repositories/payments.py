from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import Payment, PaymentStatus


class PaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, payment_id: int) -> Payment | None:
        return await self.session.get(Payment, payment_id)

    async def get_for_user(self, payment_id: int, user_id: int) -> Payment | None:
        return await self.session.scalar(
            select(Payment).where(Payment.id == payment_id, Payment.user_id == user_id)
        )

    async def memo_exists(self, memo: str) -> bool:
        return await self.session.scalar(select(Payment.id).where(Payment.memo == memo)) is not None

    async def tx_hash_used(self, tx_hash: str) -> bool:
        return await self.session.scalar(select(Payment.id).where(Payment.ton_tx_hash == tx_hash)) is not None

    async def get_open_for_user(self, user_id: int, kind: str, now: datetime) -> Payment | None:
        return await self.session.scalar(
            select(Payment)
            .where(
                Payment.user_id == user_id,
                Payment.kind == kind,
                Payment.status == PaymentStatus.PENDING,
                Payment.expires_at > now,
            )
            .order_by(Payment.id.desc())
        )

    def add(self, payment: Payment) -> None:
        self.session.add(payment)

    async def list_pending(self) -> list[Payment]:
        result = await self.session.scalars(
            select(Payment).where(Payment.status == PaymentStatus.PENDING).order_by(Payment.id)
        )
        return list(result)

    async def mark_paid_if_pending(
        self, payment_id: int, tx_hash: str, sender: str | None, paid_at: datetime
    ) -> bool:
        """Atomic PENDING -> PAID transition; returns False if someone else already processed it."""
        result = await self.session.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
            .values(status=PaymentStatus.PAID, ton_tx_hash=tx_hash, ton_sender=sender, paid_at=paid_at)
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount == 1

    async def set_status_if_pending(self, payment_id: int, status: str, error: str | None = None) -> bool:
        result = await self.session.execute(
            update(Payment)
            .where(Payment.id == payment_id, Payment.status == PaymentStatus.PENDING)
            .values(status=status, error_message=error)
            .execution_options(synchronize_session="fetch")
        )
        return result.rowcount == 1

    async def list_for_user(self, user_id: int, limit: int = 10) -> list[Payment]:
        result = await self.session.scalars(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.id.desc()).limit(limit)
        )
        return list(result)

    async def list_recent(self, limit: int = 20, status: str | None = None) -> list[Payment]:
        stmt = select(Payment).order_by(Payment.id.desc()).limit(limit)
        if status:
            stmt = stmt.where(Payment.status == status)
        return list(await self.session.scalars(stmt))

    async def revenue_nano(self) -> int:
        return int(
            await self.session.scalar(
                select(func.coalesce(func.sum(Payment.amount_nano), 0)).where(Payment.status == PaymentStatus.PAID)
            )
            or 0
        )

    async def count_by_status(self) -> dict[str, int]:
        rows = await self.session.execute(select(Payment.status, func.count(Payment.id)).group_by(Payment.status))
        return {status: count for status, count in rows.all()}
