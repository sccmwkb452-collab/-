"""YooKassa provider: https://yookassa.ru/developers/api

Webhooks are not trusted as is: each notification is re-checked with
GET /v3/payments/{id}, as YooKassa recommends.
"""

from __future__ import annotations

import json
from decimal import Decimal
from typing import Any, Mapping

import aiohttp

from payments.base import Invoice, InvoiceRequest, PaymentProvider, ProviderError, ProviderStatus

API = "https://api.yookassa.ru/v3"


class YooKassaProvider(PaymentProvider):
    name = "yookassa"
    title = "ЮKassa"
    supports_refund = True

    def __init__(self, shop_id: str, secret_key: str, return_url: str) -> None:
        if not shop_id or not secret_key:
            raise ValueError("YOOKASSA_SHOP_ID / YOOKASSA_SECRET_KEY are empty")
        self._auth = aiohttp.BasicAuth(shop_id, secret_key)
        self._return_url = return_url
        self._session: aiohttp.ClientSession | None = None

    def _http(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=20), auth=self._auth)
        return self._session

    async def _request(self, method: str, path: str, *, body: dict | None = None, idem: str | None = None) -> Any:
        headers = {"Idempotence-Key": idem} if idem else {}
        try:
            async with self._http().request(method, f"{API}{path}", json=body, headers=headers) as response:
                data = await response.json(content_type=None)
                status = response.status
        except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
            raise ProviderError(f"YooKassa {path}: {type(exc).__name__}") from None
        if status >= 400:
            raise ProviderError(f"YooKassa {path}: HTTP {status} {data.get('code', '')}".strip())
        return data

    async def create_invoice(self, request: InvoiceRequest) -> Invoice:
        data = await self._request(
            "POST",
            "/payments",
            idem=request.uid,
            body={
                "amount": {"value": f"{request.amount / 100:.2f}", "currency": "RUB"},
                "capture": True,
                "confirmation": {"type": "redirect", "return_url": self._return_url},
                "description": request.description[:128],
                "metadata": {"uid": request.uid},
            },
        )
        url = (data.get("confirmation") or {}).get("confirmation_url")
        return Invoice(external_id=data["id"], pay_url=url)

    async def fetch_status(self, external_id: str) -> ProviderStatus:
        data = await self._request("GET", f"/payments/{external_id}")
        state = {"succeeded": "paid", "pending": "pending", "waiting_for_capture": "pending", "canceled": "failed"}
        amount = data.get("amount") or {}
        kopecks = int((Decimal(amount["value"]) * 100).to_integral_value()) if "value" in amount else None
        return ProviderStatus(state.get(data.get("status"), "failed"), kopecks, amount.get("currency"))

    async def parse_webhook(self, body: bytes, headers: Mapping[str, str]) -> str | None:
        try:
            data = json.loads(body)
            if data.get("event") not in {"payment.succeeded", "payment.canceled"}:
                return None
            return str(data["object"]["id"])
        except (ValueError, KeyError, TypeError):
            raise ProviderError("YooKassa webhook: malformed body") from None

    async def refund(self, external_id: str, amount: int) -> None:
        await self._request(
            "POST",
            "/refunds",
            idem=f"refund-{external_id}",
            body={"payment_id": external_id, "amount": {"value": f"{amount / 100:.2f}", "currency": "RUB"}},
        )

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
