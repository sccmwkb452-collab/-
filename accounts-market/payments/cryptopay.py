"""Crypto Pay (@CryptoBot) provider: https://help.crypt.bot/crypto-pay-api

Invoices are issued in RUB (fiat) and paid in crypto inside Telegram.
Webhook signature: HMAC-SHA256(body, key=SHA256(api_token)).
"""

from __future__ import annotations

import hashlib
import hmac
import json
from decimal import Decimal
from typing import Any, Mapping

import aiohttp

from payments.base import Invoice, InvoiceRequest, PaymentProvider, ProviderError, ProviderStatus

MAINNET = "https://pay.crypt.bot/api"
TESTNET = "https://testnet-pay.crypt.bot/api"


def _to_kopecks(value: str | None) -> int | None:
    if value is None:
        return None
    return int((Decimal(str(value)) * 100).to_integral_value())


class CryptoPayProvider(PaymentProvider):
    name = "cryptopay"
    title = "Crypto Bot"

    def __init__(self, token: str, *, testnet: bool = False, assets: str = "USDT,TON,BTC") -> None:
        if not token:
            raise ValueError("CRYPTOPAY_TOKEN is empty")
        self._token = token
        self._base = TESTNET if testnet else MAINNET
        self._assets = assets
        self._session: aiohttp.ClientSession | None = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20))
        return self._session

    async def _call(self, method: str, params: dict[str, Any]) -> Any:
        try:
            async with self._http().post(
                f"{self._base}/{method}", json=params, headers={"Crypto-Pay-API-Token": self._token}
            ) as response:
                data = await response.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise ProviderError(f"Crypto Pay {method}: {type(exc).__name__}") from None
        if not data.get("ok"):
            error = data.get("error") or {}
            raise ProviderError(f"Crypto Pay {method}: {error.get('name') or error.get('code') or 'error'}")
        return data["result"]

    async def create_invoice(self, request: InvoiceRequest) -> Invoice:
        result = await self._call(
            "createInvoice",
            {
                "currency_type": "fiat",
                "fiat": "RUB",
                "amount": f"{request.amount / 100:.2f}",
                "accepted_assets": self._assets,
                "description": request.description[:1024],
                "payload": request.uid,
                "expires_in": request.ttl_seconds,
                "allow_comments": False,
                "allow_anonymous": True,
            },
        )
        url = result.get("bot_invoice_url") or result.get("mini_app_invoice_url") or result.get("pay_url")
        return Invoice(external_id=str(result["invoice_id"]), pay_url=url)

    async def fetch_status(self, external_id: str) -> ProviderStatus:
        result = await self._call("getInvoices", {"invoice_ids": external_id})
        items = result.get("items", []) if isinstance(result, dict) else result
        if not items:
            raise ProviderError("Crypto Pay: счёт не найден")
        return self._status(items[0])

    @staticmethod
    def _status(invoice: Mapping[str, Any]) -> ProviderStatus:
        state = {"paid": "paid", "active": "pending", "expired": "expired"}.get(invoice.get("status"), "failed")
        currency = invoice.get("fiat") if invoice.get("currency_type") == "fiat" else invoice.get("asset")
        return ProviderStatus(state, _to_kopecks(invoice.get("amount")), currency)

    def verify_signature(self, body: bytes, signature: str) -> bool:
        secret = hashlib.sha256(self._token.encode()).digest()
        expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    async def parse_webhook(self, body: bytes, headers: Mapping[str, str]) -> str | None:
        signature = headers.get("crypto-pay-api-signature") or headers.get("Crypto-Pay-API-Signature") or ""
        if not self.verify_signature(body, signature):
            raise ProviderError("Crypto Pay webhook: bad signature")
        data = json.loads(body)
        if data.get("update_type") != "invoice_paid":
            return None
        return str(data["payload"]["invoice_id"])

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
