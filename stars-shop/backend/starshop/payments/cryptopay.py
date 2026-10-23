"""Crypto Pay API (@CryptoBot) — https://help.crypt.bot/crypto-pay-api

* Invoices are issued in the shop currency (``currency_type=fiat``); the
  customer pays with any of ``CRYPTOPAY_ACCEPTED_ASSETS`` inside Telegram.
* Webhooks are authenticated with ``crypto-pay-api-signature`` =
  hex(HMAC_SHA256(key=SHA256(api_token), msg=raw_body)). After the signature
  check the invoice is re-read with ``getInvoices`` (server-to-server) before
  it is trusted, unless CRYPTOPAY_VERIFY_VIA_API=false.
* Crypto Pay has no invoice refund; refunds are made with ``transfer`` to the
  customer's @CryptoBot wallet with a unique ``spend_id`` (idempotent).

Testnet (https://testnet-pay.crypt.bot) is the default. Switch
CRYPTOPAY_NETWORK=mainnet only after an end-to-end test on testnet.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

import httpx

from ..config import Settings
from ..database.models import Order, Payment, User
from ..shared.money import fmt
from ..shared.timeutil import utcnow
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

SIGNATURE_HEADER = "crypto-pay-api-signature"
_STATUS = {"active": "pending", "paid": "paid", "expired": "expired"}


class CryptoPayProvider(PaymentProvider):
    name = "cryptopay"
    title = "Криптовалюта через @CryptoBot"
    description = "USDT, TON, BTC и другие активы — оплата внутри Telegram"
    supports_refunds = True

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._token = settings.cryptopay_api_token.get_secret_value()
        self._base = settings.cryptopay_api_base
        self._assets = settings.cryptopay_accepted_assets
        self._verify_via_api = settings.cryptopay_verify_via_api
        self._bot_username = settings.bot_username
        self._app_short_name = settings.webapp_short_name
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self._token)

    # --- low level ------------------------------------------------------------

    async def _call(self, method: str, params: dict[str, Any]) -> Any:
        if not self._token:
            raise PaymentProviderError("Crypto Pay не настроен", retryable=False)
        try:
            async with httpx.AsyncClient(base_url=self._base, timeout=15, transport=self._transport) as client:
                response = await client.post(f"/{method}", json=params, headers={"Crypto-Pay-API-Token": self._token})
        except httpx.ConnectError as exc:
            raise PaymentProviderError(retryable=True, definitely_not_executed=True) from exc
        except httpx.HTTPError as exc:
            raise PaymentProviderError(retryable=True) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise PaymentProviderError(f"Crypto Pay: некорректный ответ ({response.status_code})", retryable=True) from exc
        if not data.get("ok"):
            error = data.get("error") or {}
            name = error.get("name") if isinstance(error, dict) else str(error)
            raise PaymentProviderError(
                f"Crypto Pay: {name or 'ошибка'}",
                retryable=response.status_code >= 500,
                definitely_not_executed=response.status_code < 500,
                details={"provider_error": name},
            )
        return data["result"]

    def _return_url(self, order: Order) -> str | None:
        if not self._bot_username:
            return None
        if self._app_short_name:
            return f"https://t.me/{self._bot_username}/{self._app_short_name}?startapp=order_{order.number}"
        return f"https://t.me/{self._bot_username}?start=order_{order.number}"

    @staticmethod
    def _state(invoice: dict[str, Any]) -> ProviderPaymentState:
        currency_type = invoice.get("currency_type")
        currency = invoice.get("fiat") if currency_type == "fiat" else invoice.get("asset")
        return ProviderPaymentState(
            provider_payment_id=str(invoice["invoice_id"]),
            status=_STATUS.get(invoice.get("status", ""), "pending"),  # type: ignore[arg-type]
            amount=Decimal(str(invoice["amount"])) if invoice.get("amount") is not None else None,
            currency=currency,
            reference=invoice.get("payload"),
            paid_amount=invoice.get("paid_amount"),
            paid_asset=invoice.get("paid_asset"),
            data={
                k: invoice.get(k)
                for k in ("invoice_id", "status", "paid_at", "paid_asset", "paid_amount", "paid_fiat_rate", "fee_asset", "fee_amount")
            },
        )

    # --- interface ------------------------------------------------------------

    async def create_payment(self, payment: Payment, ctx: PaymentContext) -> PaymentIntent:
        params: dict[str, Any] = {
            "currency_type": "fiat",
            "fiat": payment.currency,
            "accepted_assets": self._assets,
            "amount": fmt(payment.amount),
            "description": ctx.description[:1024],
            "payload": str(payment.id),
            "allow_comments": False,
            "allow_anonymous": False,
            "expires_in": max(60, min(ctx.ttl_seconds, 2_678_400)),
        }
        if (url := self._return_url(ctx.order)) is not None:
            params["paid_btn_name"] = "callback"
            params["paid_btn_url"] = url
        invoice = await self._call("createInvoice", params)
        pay_url = invoice.get("mini_app_invoice_url") or invoice.get("bot_invoice_url") or invoice.get("pay_url")
        if not pay_url:
            raise PaymentProviderError("Crypto Pay не вернул ссылку на оплату", retryable=False)
        expires: datetime | None = None
        if invoice.get("expiration_date"):
            try:
                expires = datetime.fromisoformat(str(invoice["expiration_date"]).replace("Z", "+00:00"))
            except ValueError:
                expires = None
        return PaymentIntent(
            provider_payment_id=str(invoice["invoice_id"]),
            pay_url=pay_url,
            pay_url_kind="telegram" if pay_url.startswith("https://t.me/") else "external",
            expires_at=expires or utcnow() + timedelta(seconds=params["expires_in"]),
            data={"hash": invoice.get("hash")},
        )

    def _expected_signature(self, body: bytes) -> str:
        secret = hashlib.sha256(self._token.encode()).digest()
        return hmac.new(secret, body, hashlib.sha256).hexdigest()

    async def parse_webhook(self, headers: dict[str, str], body: bytes) -> VerifiedWebhook:
        signature = headers.get(SIGNATURE_HEADER, "")
        if not self._token or not signature or not hmac.compare_digest(self._expected_signature(body), signature):
            raise WebhookSignatureError("bad crypto pay signature")
        data = json.loads(body)
        event_type = str(data.get("update_type", ""))
        invoice = data.get("payload") or {}
        state = None
        if event_type == "invoice_paid" and isinstance(invoice, dict) and invoice.get("invoice_id") is not None:
            state = self._state(invoice)
            if self._verify_via_api:
                state = await self._fetch_by_id(state.provider_payment_id)
        return VerifiedWebhook(event_id=str(data.get("update_id")), event_type=event_type, state=state, payload=data)

    async def _fetch_by_id(self, invoice_id: str) -> ProviderPaymentState:
        result = await self._call("getInvoices", {"invoice_ids": invoice_id})
        items = result.get("items", []) if isinstance(result, dict) else result
        for invoice in items or []:
            if str(invoice.get("invoice_id")) == str(invoice_id):
                return self._state(invoice)
        raise PaymentProviderError("Crypto Pay: счёт не найден", retryable=True)

    async def fetch_state(self, payment: Payment) -> ProviderPaymentState:
        if not payment.provider_payment_id:
            raise PaymentProviderError("Платёж не был создан у провайдера", retryable=False)
        return await self._fetch_by_id(payment.provider_payment_id)

    async def cancel(self, payment: Payment) -> None:
        if payment.provider_payment_id:
            try:
                await self._call("deleteInvoice", {"invoice_id": int(payment.provider_payment_id)})
            except (PaymentProviderError, ValueError):
                pass

    async def refund(self, payment: Payment, order: Order, user: User) -> RefundResult:
        if not payment.paid_asset or not payment.paid_amount:
            raise PaymentProviderError("Нет данных об оплаченном активе — оформите возврат вручную", retryable=False)
        spend_id = f"refund-{payment.id.hex}"
        result = await self._call(
            "transfer",
            {
                "user_id": user.telegram_id,
                "asset": payment.paid_asset,
                "amount": payment.paid_amount,
                "spend_id": spend_id,
                "comment": f"Возврат по заказу #{order.number}",
            },
        )
        return RefundResult(status="succeeded", reference=str(result.get("transfer_id") or spend_id), data={"transfer": result})

    async def balances(self) -> list[dict[str, str]] | None:
        result = await self._call("getBalance", {})
        return [
            {"currency": b.get("currency_code"), "available": b.get("available"), "onhold": b.get("onhold")}
            for b in result
            if Decimal(str(b.get("available") or 0)) > 0 or Decimal(str(b.get("onhold") or 0)) > 0
        ]
