"""Telegram Stars (currency ``XTR``) — https://core.telegram.org/bots/payments-stars

* An invoice link is created with ``createInvoiceLink`` (no provider token,
  amount in whole Stars); the payload is our ``Payment.id``.
* Telegram asks the bot to confirm the purchase (``pre_checkout_query``) and
  then sends ``successful_payment`` to the bot. The bot handler turns it into
  an event signed with a key derived from SECRET_KEY and feeds it to the same
  pipeline as provider webhooks (de-duplication by
  ``telegram_payment_charge_id``, amount and currency check).
* ``getStarTransactions`` lets the server find a payment whose update was
  lost; refunds use ``refundStarPayment``.

Used for Lucky Buy: digital goods inside Telegram are paid in Stars.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any

import httpx

from ..config import Settings
from ..database.models import Order, Payment, User
from .base import (
    PaymentContext,
    PaymentIntent,
    PaymentProvider,
    PaymentProviderError,
    ProviderPaymentState,
    RefundResult,
    VerifiedWebhook,
    WebhookSignatureError,
)

SIGNATURE_HEADER = "x-starshop-signature"
CURRENCY = "XTR"


class TelegramStarsProvider(PaymentProvider):
    name = "telegram_stars"
    title = "Telegram Stars"
    description = "Оплата звёздами прямо в Telegram"
    supports_refunds = True
    currencies = frozenset({CURRENCY})

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._token = settings.bot_token.get_secret_value()
        self._base = settings.telegram_api_base.rstrip("/")
        self._key = hmac.new(settings.secret_key.get_secret_value().encode(), b"telegram-stars-payments", hashlib.sha256).digest()
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self._token)

    async def _call(self, method: str, params: dict[str, Any]) -> Any:
        if not self._token:
            raise PaymentProviderError("Бот не настроен: нет BOT_TOKEN", retryable=False)
        try:
            async with httpx.AsyncClient(timeout=15, transport=self._transport) as client:
                response = await client.post(f"{self._base}/bot{self._token}/{method}", json=params)
        except httpx.HTTPError as exc:
            raise PaymentProviderError(f"Telegram недоступен: {exc.__class__.__name__}") from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise PaymentProviderError(f"Telegram вернул {response.status_code}") from exc
        if not data.get("ok"):
            raise PaymentProviderError(f"Telegram: {data.get('description', response.status_code)}", retryable=response.status_code >= 500)
        return data["result"]

    # --- events from the bot ---------------------------------------------------

    def sign(self, body: bytes) -> str:
        return hmac.new(self._key, body, hashlib.sha256).hexdigest()

    def build_event(self, *, charge_id: str, payload: str, total_amount: int, currency: str, payer_id: int) -> tuple[dict[str, str], bytes]:
        """Called by the bot for a ``successful_payment`` update."""
        body = json.dumps(
            {
                "event_id": charge_id,
                "payload": payload,
                "total_amount": total_amount,
                "currency": currency,
                "payer_id": payer_id,
            },
            separators=(",", ":"),
        ).encode()
        return {SIGNATURE_HEADER: self.sign(body)}, body

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> VerifiedWebhook:
        signature = headers.get(SIGNATURE_HEADER, "")
        if not signature or not hmac.compare_digest(self.sign(body), signature):
            raise WebhookSignatureError("bad signature")
        data = json.loads(body)
        state = ProviderPaymentState(
            provider_payment_id="",
            status="paid",
            amount=Decimal(int(data["total_amount"])),
            currency=str(data["currency"]),
            reference=str(data["payload"]),
            data={"telegram_payment_charge_id": data["event_id"], "payer_id": data["payer_id"]},
        )
        return VerifiedWebhook(event_id=str(data["event_id"]), event_type="successful_payment", state=state, payload=data)

    # --- provider API ------------------------------------------------------------

    async def create_payment(self, payment: Payment, ctx: PaymentContext) -> PaymentIntent:
        amount = int(payment.amount)
        if payment.currency != CURRENCY or amount != payment.amount or amount < 1:
            raise PaymentProviderError("Telegram Stars принимает только целое число звёзд", retryable=False)
        link = await self._call(
            "createInvoiceLink",
            {
                "title": f"Заказ #{ctx.order.number}"[:32],
                "description": ctx.description[:255],
                "payload": str(payment.id),
                "currency": CURRENCY,
                "prices": [{"label": f"{ctx.order.stars_amount} Stars"[:32], "amount": amount}],
            },
        )
        return PaymentIntent(provider_payment_id=f"xtr_{payment.id.hex}", pay_url=str(link), pay_url_kind="invoice")

    async def fetch_state(self, payment: Payment) -> ProviderPaymentState:
        """Looks for the payment among the bot's recent Star transactions."""
        reference = str(payment.id)
        for offset in range(0, 500, 100):
            result = await self._call("getStarTransactions", {"offset": offset, "limit": 100})
            transactions = result.get("transactions", [])
            for tx in transactions:
                source = tx.get("source") or {}
                if source.get("type") == "user" and source.get("invoice_payload") == reference:
                    return ProviderPaymentState(
                        provider_payment_id=payment.provider_payment_id or "",
                        status="paid",
                        amount=Decimal(int(tx["amount"])),
                        currency=CURRENCY,
                        reference=reference,
                        data={"telegram_payment_charge_id": tx["id"], "payer_id": (source.get("user") or {}).get("id")},
                    )
            if len(transactions) < 100:
                break
        return ProviderPaymentState(provider_payment_id=payment.provider_payment_id or "", status="pending", amount=None, currency=None)

    async def refund(self, payment: Payment, order: Order, user: User) -> RefundResult:
        confirmation = (payment.provider_data or {}).get("confirmation") or {}
        charge_id = confirmation.get("telegram_payment_charge_id")
        payer_id = confirmation.get("payer_id") or user.telegram_id
        if not charge_id:
            raise PaymentProviderError("Нет идентификатора платежа Telegram для возврата", retryable=False)
        try:
            await self._call("refundStarPayment", {"user_id": int(payer_id), "telegram_payment_charge_id": charge_id})
        except PaymentProviderError as exc:
            if "ALREADY_REFUNDED" not in exc.message.upper():  # a retry after a lost answer
                raise
        return RefundResult(status="succeeded", reference=charge_id)
