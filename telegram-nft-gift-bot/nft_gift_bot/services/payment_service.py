"""Invoices and server-side confirmation of TON payments."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import Payment, PaymentKind, PaymentStatus
from nft_gift_bot.payments.ton import new_memo
from nft_gift_bot.payments.toncenter import ChainClient
from nft_gift_bot.payments.verifier import IncomingTransfer, find_payment_transfer
from nft_gift_bot.repositories import PaymentRepository
from nft_gift_bot.services.subscription_service import SubscriptionService

logger = logging.getLogger(__name__)


@dataclass
class ConfirmedPayment:
    payment: Payment
    tx_hash: str


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = PaymentRepository(session)
        self._subscriptions = SubscriptionService(session)

    async def create_subscription_invoice(
        self, user_id: int, amount_nano: int, days: int, ttl: timedelta, now: datetime
    ) -> Payment:
        """Reuse an open invoice so repeated taps don't spawn many pending payments."""
        existing = await self._repo.get_open_for_user(user_id, PaymentKind.SUBSCRIPTION, now)
        if existing is not None and existing.amount_nano == amount_nano and existing.subscription_days == days:
            return existing
        if existing is not None:
            await self._repo.set_status_if_pending(existing.id, PaymentStatus.CANCELLED, "superseded")
        memo = new_memo()
        while await self._repo.memo_exists(memo):
            memo = new_memo()
        payment = Payment(
            user_id=user_id,
            kind=PaymentKind.SUBSCRIPTION,
            amount_nano=amount_nano,
            subscription_days=days,
            memo=memo,
            expires_at=now + ttl,
            created_at=now,
        )
        self._repo.add(payment)
        await self._session.flush()
        return payment

    async def cancel(self, payment_id: int, user_id: int) -> bool:
        payment = await self._repo.get_for_user(payment_id, user_id)
        if payment is None:
            return False
        return await self._repo.set_status_if_pending(payment.id, PaymentStatus.CANCELLED)

    async def _confirm(self, payment: Payment, transfer: IncomingTransfer, now: datetime) -> bool:
        if not await self._repo.mark_paid_if_pending(payment.id, transfer.tx_hash, transfer.sender, now):
            return False
        await self._subscriptions.extend(payment.user_id, payment.subscription_days, now)
        logger.info("payment confirmed", extra={"payment_id": payment.id, "user_id": payment.user_id})
        return True

    async def process_pending(
        self, chain: ChainClient, receiver_address: str, now: datetime, only_payment_id: int | None = None
    ) -> list[ConfirmedPayment]:
        """Match pending invoices against real incoming transactions; expire stale invoices.

        Late payments (arrived after the invoice expired but before we saw it) are
        still honoured: the money is on-chain with our unique memo, so the
        transaction must have been created against this invoice.
        """
        pending = await self._repo.list_pending()
        if only_payment_id is not None:
            pending = [p for p in pending if p.id == only_payment_id]
        if not pending:
            return []
        transfers = await chain.get_incoming_transfers(receiver_address)
        confirmed: list[ConfirmedPayment] = []
        used = {t.tx_hash for t in transfers if await self._repo.tx_hash_used(t.tx_hash)}
        for payment in pending:
            match = find_payment_transfer(
                transfers,
                payment.memo,
                payment.amount_nano,
                used_hashes=used,
                not_before_utime=int(payment.created_at.timestamp()) - 60,
            )
            if match is not None:
                used.add(match.tx_hash)
                if await self._confirm(payment, match, now):
                    confirmed.append(ConfirmedPayment(payment=payment, tx_hash=match.tx_hash))
            elif payment.expires_at <= now - timedelta(hours=24):
                # Grace period of 24h for slow wallets/indexer lag before giving up.
                await self._repo.set_status_if_pending(payment.id, PaymentStatus.EXPIRED)
        return confirmed

    async def list_for_user(self, user_id: int, limit: int = 10) -> list[Payment]:
        return await self._repo.list_for_user(user_id, limit)
