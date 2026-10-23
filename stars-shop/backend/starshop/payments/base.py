"""Payment provider interface.

The server never trusts the client about a payment: an order becomes paid
only after a provider event with a valid signature (or a server-side status
query to the provider) reports the exact amount and currency of the payment.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from ..database.models import Order, Payment, User
from ..shared.errors import ProviderError


class PaymentProviderError(ProviderError):
    code = "payment_provider_error"
    message = "Платёжный провайдер временно недоступен. Попробуйте ещё раз"


class WebhookSignatureError(Exception):
    """The webhook is not authentic. Never process it."""


@dataclass(slots=True)
class PaymentIntent:
    provider_payment_id: str
    pay_url: str
    # telegram: t.me link (open with openTelegramLink); external: browser page;
    # internal: a page of this Mini App (DEMO only)
    pay_url_kind: Literal["telegram", "external", "internal"]
    expires_at: datetime | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ProviderPaymentState:
    provider_payment_id: str
    status: Literal["pending", "paid", "expired", "failed", "cancelled"]
    amount: Decimal | None
    currency: str | None
    # Reference we passed to the provider (our Payment.id); checked on receipt.
    reference: str | None = None
    paid_amount: str | None = None
    paid_asset: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class VerifiedWebhook:
    event_id: str
    event_type: str
    state: ProviderPaymentState | None
    payload: dict[str, Any]


@dataclass(slots=True)
class RefundResult:
    status: Literal["succeeded", "pending"]
    reference: str | None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class PaymentContext:
    order: Order
    user: User
    description: str
    return_url: str
    ttl_seconds: int


class PaymentProvider(ABC):
    name: str = ""
    title: str = ""
    description: str = ""
    is_demo: bool = False
    supports_refunds: bool = False

    def is_configured(self) -> bool:
        return True

    @abstractmethod
    async def create_payment(self, payment: Payment, ctx: PaymentContext) -> PaymentIntent: ...

    @abstractmethod
    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> VerifiedWebhook:
        """Verify authenticity (raise ``WebhookSignatureError``) and parse."""

    @abstractmethod
    async def fetch_state(self, payment: Payment) -> ProviderPaymentState: ...

    async def refund(self, payment: Payment, order: Order, user: User) -> RefundResult:
        raise PaymentProviderError("Провайдер не поддерживает автоматический возврат", retryable=False)

    async def cancel(self, payment: Payment) -> None:  # noqa: B027 - optional hook
        """Best-effort invalidation of an unpaid invoice."""

    async def balances(self) -> list[dict[str, str]] | None:
        """Merchant balance at the provider, if the API exposes it."""
        return None
