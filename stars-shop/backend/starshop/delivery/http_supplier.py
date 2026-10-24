"""Adapter for an external Stars supplier speaking a small signed REST
contract (documented in docs/DELIVERY.md).

Request signing (both directions):
    X-Timestamp: unix seconds
    X-Signature: hex(HMAC_SHA256(SUPPLIER_API_SECRET, f"{timestamp}.{raw_body}"))
Requests also carry ``Authorization: Bearer SUPPLIER_API_KEY`` and an
``Idempotency-Key`` header; the supplier MUST de-duplicate on it.

This module does not talk to any particular vendor: put a thin bridge in
front of your real supplier that implements the contract.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import httpx

from ..config import Settings
from .base import DeliveryCallback, DeliveryError, DeliveryOutcome, DeliveryProvider, DeliveryRequest, RecipientCheck

_STATUS_MAP = {
    "completed": "succeeded",
    "succeeded": "succeeded",
    "processing": "pending",
    "accepted": "pending",
    "pending": "pending",
    "failed": "failed",
    "rejected": "failed",
}


def sign(secret: str, timestamp: str, body: bytes) -> str:
    return hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()


class HttpSupplierDeliveryProvider(DeliveryProvider):
    name = "http_supplier"
    title = "Поставщик Stars (HTTP API)"
    idempotent = True
    requires_username = True

    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self._base = settings.supplier_api_url.rstrip("/")
        self._key = settings.supplier_api_key.get_secret_value()
        self._secret = settings.supplier_api_secret.get_secret_value()
        self._timeout = settings.supplier_timeout_seconds
        self._callback_url = settings.public_base_url.rstrip("/") + "/api/v1/webhooks/delivery/http_supplier"
        self._transport = transport

    def is_configured(self) -> bool:
        return bool(self._base and self._key and self._secret)

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self._base, timeout=self._timeout, transport=self._transport)

    def _headers(self, body: bytes, idempotency_key: str | None = None) -> dict[str, str]:
        ts = str(int(time.time()))
        headers = {
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "X-Timestamp": ts,
            "X-Signature": sign(self._secret, ts, body),
        }
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return headers

    async def _request(self, method: str, path: str, payload: dict | None = None, idempotency_key: str | None = None) -> httpx.Response:
        if not self.is_configured():
            raise DeliveryError("Поставщик не настроен", retryable=False, definitely_not_executed=True)
        body = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else b""
        try:
            async with self._client() as client:
                return await client.request(method, path, content=body or None, headers=self._headers(body, idempotency_key))
        except httpx.ConnectError as exc:
            raise DeliveryError("Поставщик недоступен", retryable=True, definitely_not_executed=True) from exc
        except httpx.TimeoutException as exc:
            # The request may or may not have been executed — safe to retry
            # only because the supplier de-duplicates by Idempotency-Key.
            raise DeliveryError("Поставщик не ответил вовремя", retryable=True) from exc
        except httpx.HTTPError as exc:
            raise DeliveryError(f"Ошибка связи с поставщиком: {exc.__class__.__name__}", retryable=True) from exc

    @staticmethod
    def _outcome(data: dict) -> DeliveryOutcome:
        status = _STATUS_MAP.get(str(data.get("status", "")).lower())
        if status is None:
            raise DeliveryError(f"Неизвестный статус поставщика: {data.get('status')!r}", retryable=True)
        return DeliveryOutcome(
            status=status,  # type: ignore[arg-type]
            external_id=str(data.get("id")) if data.get("id") is not None else None,
            message=data.get("error") or data.get("message"),
            details={k: data[k] for k in ("id", "status", "tx_id", "completed_at") if k in data},
        )

    def _raise_for(self, response: httpx.Response) -> None:
        if response.status_code == 429 or response.status_code >= 500:
            raise DeliveryError(f"Поставщик вернул {response.status_code}", retryable=True)
        if response.status_code >= 400:
            try:
                detail = response.json().get("error")
            except ValueError:
                detail = None
            raise DeliveryError(
                detail or f"Поставщик отклонил запрос ({response.status_code})", retryable=False, definitely_not_executed=True
            )

    async def deliver(self, request: DeliveryRequest) -> DeliveryOutcome:
        payload = {
            "idempotency_key": request.idempotency_key,
            "reference": request.order_number,
            "stars": request.stars,
            "recipient": {"username": request.recipient_username, "telegram_id": request.recipient_telegram_id},
            "callback_url": self._callback_url,
        }
        response = await self._request("POST", "/v1/deliveries", payload, request.idempotency_key)
        self._raise_for(response)
        return self._outcome(response.json())

    async def check(self, external_id: str, request: DeliveryRequest) -> DeliveryOutcome:
        response = await self._request("GET", f"/v1/deliveries/{external_id}")
        self._raise_for(response)
        return self._outcome(response.json())

    async def check_recipient(self, username: str) -> RecipientCheck:
        response = await self._request("GET", f"/v1/recipients/{username}")
        if response.status_code == 404:
            return RecipientCheck(ok=False, reason="Пользователь с таким username не найден")
        if response.status_code in (405, 501):
            return RecipientCheck(ok=True)
        self._raise_for(response)
        data = response.json()
        found = bool(data.get("found", True))
        photo = data.get("photo_url")
        return RecipientCheck(
            ok=found,
            verified=found and data.get("found") is True,
            display_name=data.get("name"),
            photo_url=photo if isinstance(photo, str) and photo.startswith("https://") else None,
            reason=None if found else "Пользователь с таким username не найден",
        )

    def parse_callback(self, headers: dict[str, str], body: bytes) -> DeliveryCallback:
        ts = headers.get("x-timestamp", "")
        signature = headers.get("x-signature", "")
        if not ts.isdigit() or abs(time.time() - int(ts)) > 300:
            raise DeliveryError("Callback timestamp is invalid", retryable=False, code="signature_invalid")
        if not self._secret or not hmac.compare_digest(sign(self._secret, ts, body), signature):
            raise DeliveryError("Callback signature is invalid", retryable=False, code="signature_invalid")
        data = json.loads(body)
        outcome = self._outcome(data)
        if not outcome.external_id:
            raise DeliveryError("Callback has no delivery id", retryable=False)
        return DeliveryCallback(external_id=outcome.external_id, outcome=outcome)
