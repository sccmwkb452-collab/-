"""Orchestrates TON payment creation, verification and subscription activation."""
import logging
import random
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models.payment import TonPayment, TonPaymentStatus
from database.models.subscription import SubscriptionPlan, SubscriptionStatus
from database.repositories.payment_repo import TonPaymentRepository
from database.repositories.bot_setting_repo import BotSettingRepository
from database.repositories.subscription_repo import SubscriptionRepository
from payments.ton.client import TonCenterClient
from payments.ton.verifier import TonPaymentVerifier

logger = logging.getLogger(__name__)

SETTING_SUB_DURATION_DAYS = "sub_duration_days"
DEFAULT_SUB_DURATION_DAYS = 30

SETTING_SUB_PRICE_TON = "sub_price_ton"
DEFAULT_SUB_PRICE_TON = 10.0


def _make_payment_comment() -> str:
    digits = "".join(random.choices(string.digits, k=8))
    return f"NFT{digits}"


@dataclass
class PaymentInitResult:
    payment: TonPayment
    amount_ton: float
    recipient_address: str
    payment_comment: str
    expires_at: datetime


@dataclass
class PaymentCheckResult:
    activated: bool
    reason: str


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._payment_repo = TonPaymentRepository(session)
        self._sub_repo = SubscriptionRepository(session)
        self._setting_repo = BotSettingRepository(session)

    async def _get_sub_duration(self) -> int:
        raw = await self._setting_repo.get(SETTING_SUB_DURATION_DAYS)
        if raw and raw.isdigit():
            return int(raw)
        return DEFAULT_SUB_DURATION_DAYS

    async def _get_sub_price(self) -> float:
        raw = await self._setting_repo.get(SETTING_SUB_PRICE_TON)
        if raw:
            try:
                price = float(raw)
                if price > 0:
                    return price
            except ValueError:
                pass
        return DEFAULT_SUB_PRICE_TON

    async def set_sub_price(self, price: float) -> None:
        await self._setting_repo.set(SETTING_SUB_PRICE_TON, str(price))

    async def init_payment(self, user_id: int) -> PaymentInitResult:
        """Create a pending TonPayment with a unique comment. Returns payment details."""
        now = datetime.now(tz=timezone.utc)
        expires_at = now + timedelta(minutes=settings.payment_window_minutes)
        comment = _make_payment_comment()
        amount_ton = await self._get_sub_price()

        payment = await self._payment_repo.create(
            user_id=user_id,
            payment_comment=comment,
            created_at=now,
            expires_at=expires_at,
        )
        logger.info(
            "TON payment initiated: user_id=%d comment=%s expires=%s amount=%.2f TON",
            user_id,
            comment,
            expires_at.isoformat(),
            amount_ton,
        )
        return PaymentInitResult(
            payment=payment,
            amount_ton=amount_ton,
            recipient_address=settings.ton_recipient_address,
            payment_comment=comment,
            expires_at=expires_at,
        )

    async def get_pending(self, user_id: int) -> TonPayment | None:
        return await self._payment_repo.get_pending_for_user(user_id)

    async def check_and_activate(
        self, payment_comment: str
    ) -> PaymentCheckResult:
        """
        Verify the blockchain tx and activate the subscription atomically.

        NEVER activates based on user input alone — always verifies the actual
        on-chain transaction before crediting the subscription.
        """
        # Lock the payment row to prevent concurrent double-activation
        payment = await self._payment_repo.get_by_comment_for_update(payment_comment)
        if payment is None:
            return PaymentCheckResult(activated=False, reason="Payment record not found")

        if payment.status != TonPaymentStatus.PENDING:
            return PaymentCheckResult(
                activated=False,
                reason=f"Payment already in status: {payment.status.value}",
            )

        now = datetime.now(tz=timezone.utc)
        if payment.expires_at < now:
            await self._payment_repo.set_status(payment, TonPaymentStatus.EXPIRED)
            return PaymentCheckResult(activated=False, reason="Payment window expired")

        # ── Blockchain verification ───────────────────────────────────────────
        client = TonCenterClient(
            api_key=settings.toncenter_api_key,
            network=settings.ton_network,
        )
        required_ton = await self._get_sub_price()
        verifier = TonPaymentVerifier(
            client=client,
            recipient_address=settings.ton_recipient_address,
            required_ton=required_ton,
        )
        result = await verifier.verify(payment_comment)

        if not result.ok:
            logger.info(
                "TON verification failed for comment=%s: %s",
                payment_comment,
                result.reason,
            )
            return PaymentCheckResult(activated=False, reason=result.reason)

        tx = result.tx
        assert tx is not None

        # ── Double-spend guard ────────────────────────────────────────────────
        if await self._payment_repo.tx_hash_exists(tx.tx_hash):
            await self._payment_repo.set_status(payment, TonPaymentStatus.DUPLICATE)
            logger.warning("Duplicate tx_hash=%s blocked for user_id=%d", tx.tx_hash, payment.user_id)
            return PaymentCheckResult(activated=False, reason="Transaction already credited")

        # ── Create subscription ───────────────────────────────────────────────
        duration_days = await self._get_sub_duration()
        start = datetime.now(tz=timezone.utc)
        sub = await self._sub_repo.create(
            user_id=payment.user_id,
            plan=SubscriptionPlan.BASIC,
            status=SubscriptionStatus.ACTIVE,
            price_paid=required_ton,
            currency="TON",
            started_at=start,
            expires_at=start + timedelta(days=duration_days),
        )

        await self._payment_repo.confirm(
            payment=payment,
            tx_hash=tx.tx_hash,
            amount_nanoton=tx.amount_nanoton,
            subscription_id=sub.id,
        )

        logger.info(
            "Subscription activated: user_id=%d sub_id=%d tx_hash=%s duration=%d days",
            payment.user_id,
            sub.id,
            tx.tx_hash,
            duration_days,
        )
        return PaymentCheckResult(activated=True, reason="ok")

    async def expire_old_pending(self) -> int:
        return await self._payment_repo.expire_old_pending()

    async def set_sub_duration(self, days: int) -> None:
        await self._setting_repo.set(SETTING_SUB_DURATION_DAYS, str(days))
