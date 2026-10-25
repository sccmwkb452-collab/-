"""Top-ups: invoice creation, verified crediting, expiry and refunds."""

from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from database.models import Payment, PaymentStatus, TxKind
from payments.base import InvoiceRequest, PaymentProvider, ProviderError
from services.audit import log_action
from services.errors import InsufficientFunds, ShopError
from services.ledger import change_balance

log = logging.getLogger(__name__)

PaidCallback = Callable[[Payment], Awaitable[None]]


@dataclass(frozen=True)
class CheckResult:
    payment: Payment
    credited: bool  # True only for the single call that actually credited the balance


class PaymentService:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        provider: PaymentProvider,
        *,
        ttl_minutes: int = 60,
        max_amount: int = 100_000_00,
    ) -> None:
        self.sm = sessionmaker
        self.provider = provider
        self.ttl = timedelta(minutes=ttl_minutes)
        self.max_amount = max_amount
        self.on_paid: PaidCallback | None = None

    async def create(self, user_id: int, amount: int, min_amount: int, shop_name: str) -> Payment:
        if amount < min_amount:
            raise ShopError("Сумма меньше минимальной")
        if amount > self.max_amount:
            raise ShopError("Сумма больше максимальной")
        uid = secrets.token_hex(8)
        async with self.sm() as session, session.begin():
            payment = Payment(
                uid=uid,
                user_id=user_id,
                provider=self.provider.name,
                amount=amount,
                status=PaymentStatus.PENDING,
                expires_at=datetime.now(timezone.utc) + self.ttl,
            )
            session.add(payment)
        try:
            invoice = await self.provider.create_invoice(
                InvoiceRequest(uid, amount, f"{shop_name}: пополнение баланса", int(self.ttl.total_seconds()))
            )
        except ProviderError as exc:
            log.warning("invoice creation failed for payment %s: %s", payment.id, exc)
            async with self.sm() as session, session.begin():
                await session.execute(
                    Payment.__table__.update()
                    .where(Payment.id == payment.id)
                    .values(status=PaymentStatus.FAILED, last_error=str(exc)[:512])
                )
            raise ShopError("Платёжный сервис временно недоступен, попробуйте позже") from None
        async with self.sm() as session, session.begin():
            payment = await session.get(Payment, payment.id)
            payment.external_id = invoice.external_id
            payment.pay_url = invoice.pay_url
        return payment

    async def check(self, payment_id: int) -> CheckResult:
        """Asks the provider and credits the balance if the invoice is paid."""
        async with self.sm() as session:
            payment = await session.get(Payment, payment_id)
        if payment is None:
            raise ShopError("Платёж не найден")
        if payment.status not in (PaymentStatus.PENDING, PaymentStatus.EXPIRED) or not payment.external_id:
            return CheckResult(payment, False)
        try:
            status = await self.provider.fetch_status(payment.external_id)
        except ProviderError as exc:
            await self._note_error(payment.id, str(exc))
            raise ShopError("Не удалось проверить оплату, попробуйте через минуту") from None

        if status.state == "paid":
            if status.amount is not None and status.amount != payment.amount:
                await self._note_error(payment.id, f"amount mismatch: provider={status.amount}")
                log.error("payment %s amount mismatch", payment.id)
                return CheckResult(payment, False)
            return await self._credit(payment.id)

        async with self.sm() as session, session.begin():
            fresh = await session.get(Payment, payment.id, with_for_update=True)
            fresh.checked_at = func.now()
            expired = fresh.expires_at <= datetime.now(timezone.utc)
            if fresh.status == PaymentStatus.PENDING and (status.state in ("expired", "failed") or expired):
                fresh.status = PaymentStatus.EXPIRED if status.state != "failed" else PaymentStatus.FAILED
            await session.flush()
            await session.refresh(fresh)  # load server-side values before the session closes
            return CheckResult(fresh, False)

    async def check_by_external(self, external_id: str) -> CheckResult | None:
        async with self.sm() as session:
            payment_id = await session.scalar(
                select(Payment.id).where(Payment.provider == self.provider.name, Payment.external_id == external_id)
            )
        if payment_id is None:
            return None
        return await self.check(payment_id)

    async def _credit(self, payment_id: int) -> CheckResult:
        try:
            async with self.sm() as session, session.begin():
                payment = await session.get(Payment, payment_id, with_for_update=True)
                if payment.status not in (PaymentStatus.PENDING, PaymentStatus.EXPIRED):
                    return CheckResult(payment, False)
                payment.status = PaymentStatus.PAID
                payment.paid_at = func.now()
                payment.checked_at = func.now()
                payment.last_error = None
                await change_balance(session, payment.user_id, payment.amount, TxKind.TOPUP, payment_id=payment.id)
                await session.flush()
                await session.refresh(payment)
        except IntegrityError:  # already credited by a concurrent check
            async with self.sm() as session:
                return CheckResult(await session.get(Payment, payment_id), False)
        log.info("payment %s credited", payment.id)
        if self.on_paid is not None:
            try:
                await self.on_paid(payment)
            except Exception:  # notification failure must not undo the credit
                log.exception("on_paid callback failed for payment %s", payment.id)
        return CheckResult(payment, True)

    async def _note_error(self, payment_id: int, error: str) -> None:
        async with self.sm() as session, session.begin():
            payment = await session.get(Payment, payment_id)
            payment.last_error = error[:512]
            payment.checked_at = func.now()

    async def demo_confirm(self, payment_id: int, user_id: int) -> CheckResult:
        """DEMO only: the fake provider marks its invoice paid, then the normal check runs."""
        from payments.demo import DemoProvider

        if not isinstance(self.provider, DemoProvider):
            raise ShopError("DEMO-оплата отключена")
        async with self.sm() as session:
            payment = await session.get(Payment, payment_id)
        if payment is None or payment.user_id != user_id or not payment.external_id:
            raise ShopError("Платёж не найден")
        self.provider.simulate_payment(payment.external_id, payment.amount)
        return await self.check(payment_id)

    async def poll_pending(self) -> int:
        """Re-checks open invoices; returns how many got credited."""
        since = datetime.now(timezone.utc) - self.ttl - timedelta(hours=1)
        async with self.sm() as session:
            ids = list(
                (
                    await session.execute(
                        select(Payment.id)
                        .where(
                            Payment.provider == self.provider.name,
                            Payment.status == PaymentStatus.PENDING,
                            Payment.created_at >= since,
                            Payment.external_id.is_not(None),
                        )
                        .order_by(Payment.id)
                        .limit(200)
                    )
                ).scalars()
            )
            # Old pending invoices that were never paid.
            await session.execute(
                Payment.__table__.update()
                .where(Payment.status == PaymentStatus.PENDING, Payment.created_at < since)
                .values(status=PaymentStatus.EXPIRED)
            )
            await session.commit()
        credited = 0
        for payment_id in ids:
            try:
                credited += (await self.check(payment_id)).credited
            except ShopError:
                continue
        return credited

    async def refund(self, payment_id: int, admin_id: int, reason: str) -> Payment:
        """Debits the credited amount back and asks the provider to refund, if it can."""
        async with self.sm() as session, session.begin():
            payment = await session.get(Payment, payment_id, with_for_update=True)
            if payment is None:
                raise ShopError("Платёж не найден")
            if payment.status != PaymentStatus.PAID:
                raise ShopError("Вернуть можно только оплаченный платёж")
            try:
                await change_balance(
                    session,
                    payment.user_id,
                    -payment.amount,
                    TxKind.TOPUP_REFUND,
                    payment_id=payment.id,
                    admin_id=admin_id,
                    comment=reason[:256],
                )
            except InsufficientFunds:
                raise ShopError("На балансе пользователя недостаточно средств для возврата") from None
            if self.provider.supports_refund and payment.provider == self.provider.name:
                try:
                    await self.provider.refund(payment.external_id or "", payment.amount)
                except ProviderError as exc:
                    raise ShopError(f"Провайдер отклонил возврат: {exc}") from None
            payment.status = PaymentStatus.REFUNDED
            payment.refunded_at = func.now()
            await log_action(session, admin_id, "payment_refund", payment.uid, reason)
            await session.flush()
            await session.refresh(payment)
            return payment
