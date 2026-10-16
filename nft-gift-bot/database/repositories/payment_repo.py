"""Repository for TonPayment with SELECT FOR UPDATE to prevent double-credit."""
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.payment import TonPayment, TonPaymentStatus

logger = logging.getLogger(__name__)


class TonPaymentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        user_id: int,
        payment_comment: str,
        created_at: datetime,
        expires_at: datetime,
    ) -> TonPayment:
        payment = TonPayment(
            user_id=user_id,
            payment_comment=payment_comment,
            status=TonPaymentStatus.PENDING,
            created_at=created_at,
            expires_at=expires_at,
        )
        self._session.add(payment)
        await self._session.flush()
        await self._session.refresh(payment)
        return payment

    async def get_pending_for_user(self, user_id: int) -> TonPayment | None:
        """Return most recent PENDING payment for user, or None."""
        result = await self._session.execute(
            select(TonPayment)
            .where(
                TonPayment.user_id == user_id,
                TonPayment.status == TonPaymentStatus.PENDING,
            )
            .order_by(TonPayment.created_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_by_comment_for_update(self, payment_comment: str) -> TonPayment | None:
        """Lock the row for atomic confirm — prevents double-credit."""
        result = await self._session.execute(
            select(TonPayment)
            .where(TonPayment.payment_comment == payment_comment)
            .with_for_update()
        )
        return result.scalar_one_or_none()

    async def tx_hash_exists(self, tx_hash: str) -> bool:
        """True if this tx_hash was already credited to any payment."""
        result = await self._session.execute(
            select(TonPayment.id)
            .where(TonPayment.tx_hash == tx_hash)
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def confirm(
        self,
        payment: TonPayment,
        tx_hash: str,
        amount_nanoton: int,
        subscription_id: int,
    ) -> TonPayment:
        payment.tx_hash = tx_hash
        payment.amount_nanoton = amount_nanoton
        payment.status = TonPaymentStatus.CONFIRMED
        payment.confirmed_at = datetime.now(tz=timezone.utc)
        payment.subscription_id = subscription_id
        await self._session.flush()
        return payment

    async def set_status(self, payment: TonPayment, status: TonPaymentStatus) -> TonPayment:
        payment.status = status
        await self._session.flush()
        return payment

    async def expire_old_pending(self) -> int:
        """Mark all PENDING payments whose window has passed as EXPIRED."""
        now = datetime.now(tz=timezone.utc)
        result = await self._session.execute(
            update(TonPayment)
            .where(
                TonPayment.status == TonPaymentStatus.PENDING,
                TonPayment.expires_at < now,
            )
            .values(status=TonPaymentStatus.EXPIRED)
        )
        return result.rowcount
