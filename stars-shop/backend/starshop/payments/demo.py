"""DEMO payment provider.

No money moves. The Mini App shows a clearly labelled DEMO checkout page;
its buttons call the backend, which produces an HMAC-signed provider event
and feeds it through exactly the same webhook pipeline as a real provider
(signature check, de-duplication, amount/currency check). Available only
while the shop runs in DEMO mode.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import uuid
from datetime import timedelta
from decimal import Decimal

from ..config import Settings
from ..database.models import Order, Payment, User
from ..shared.money import fmt
from ..shared.timeutil import utcnow
from .base import (
    PaymentContext,
    PaymentIntent,
    PaymentProvider,
    ProviderPaymentState,
    RefundResult,
    VerifiedWebhook,
    WebhookSignatureError,
)

SIGNATURE_HEADER = "x-demo-signature"


class DemoPaymentProvider(PaymentProvider):
    name = "demo"
    title = "DEMO-оплата"
    description = "Тестовая оплата без списания денег"
    is_demo = True
    supports_refunds = True
    currencies = frozenset({"RUB", "USD", "EUR", "KZT", "UAH", "BYN", "XTR"})

    def accepts(self, currency: str, shop_currency: str) -> bool:
        return currency in self.currencies or currency == shop_currency

    def __init__(self, settings: Settings):
        self._key = hmac.new(settings.secret_key.get_secret_value().encode(), b"demo-payments", hashlib.sha256).digest()
        self._webapp_url = settings.webapp_url.rstrip("/")

    def sign(self, body: bytes) -> str:
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()

    def build_event(self, payment: Payment, outcome: str) -> tuple[dict[str, str], bytes]:
        """Used by the DEMO checkout endpoint to emulate the provider."""
        body = json.dumps(
            {
                "event_id": f"demo_evt_{uuid.uuid4().hex}",
                "type": "payment.updated",
                "payment": {
                    "id": payment.provider_payment_id,
                    "reference": str(payment.id),
                    "status": "paid" if outcome == "success" else "failed",
                    "amount": fmt(payment.amount),
                    "currency": payment.currency,
                },
            },
            separators=(",", ":"),
        ).encode()
        return {SIGNATURE_HEADER: self.sign(body)}, body

    async def create_payment(self, payment: Payment, ctx: PaymentContext) -> PaymentIntent:
        return PaymentIntent(
            provider_payment_id=f"demo_{payment.id.hex[:20]}",
            pay_url=f"{self._webapp_url}/pay/demo/{payment.id}",
            pay_url_kind="internal",
            expires_at=utcnow() + timedelta(seconds=ctx.ttl_seconds),
        )

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> VerifiedWebhook:
        signature = headers.get(SIGNATURE_HEADER, "")
        if not signature or not hmac.compare_digest(self.sign(body), signature):
            raise WebhookSignatureError("bad demo signature")
        data = json.loads(body)
        p = data["payment"]
        state = ProviderPaymentState(
            provider_payment_id=p["id"],
            status=p["status"],
            amount=Decimal(p["amount"]),
            currency=p["currency"],
            reference=p.get("reference"),
            paid_amount=p["amount"],
            paid_asset=p["currency"],
        )
        return VerifiedWebhook(event_id=data["event_id"], event_type=data["type"], state=state, payload=data)

    async def fetch_state(self, payment: Payment) -> ProviderPaymentState:
        # The DEMO provider has no remote state: report what we already know.
        status = {"succeeded": "paid", "failed": "failed", "expired": "expired", "cancelled": "cancelled"}.get(payment.status, "pending")
        return ProviderPaymentState(
            provider_payment_id=payment.provider_payment_id or "",
            status=status,  # type: ignore[arg-type]
            amount=payment.amount,
            currency=payment.currency,
            reference=str(payment.id),
        )

    async def refund(self, payment: Payment, order: Order, user: User) -> RefundResult:
        return RefundResult(status="succeeded", reference=f"demo_refund_{payment.id.hex[:12]}")
