"""Reloadly Gift Cards API (official reseller API with a sandbox).

* token: POST https://auth.reloadly.com/oauth/token
  ``{client_id, client_secret, grant_type: client_credentials, audience}``,
  audience ``https://giftcards-sandbox.reloadly.com`` or ``https://giftcards.reloadly.com``
* catalogue: GET /products?page=&size= (paged ``content``/``totalPages``)
* balance: GET /accounts/balance
* order: POST /orders ``{productId, countryCode, quantity, unitPrice, customIdentifier, senderName, recipientEmail}``
* codes: GET /orders/transactions/{transactionId}/cards
* reconciliation: GET /reports/transactions?customIdentifier=…

An order spends wallet funds and cannot be reversed; ``customIdentifier``
carries our idempotency key so an unclear answer can be reconciled instead
of being retried.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from ...database.enums import SupplierOrderStatus
from ..http import IntegrationError, check_status, classify, client, with_retries
from .base import (
    CatalogItem,
    ConnectionCheck,
    CredentialField,
    PurchaseRequest,
    PurchaseResult,
    SupplierAdapter,
    SupplierCapabilities,
)

AUTH_URL = "https://auth.reloadly.com/oauth/token"
ACCEPT = "application/com.reloadly.giftcards-v1+json"
STATUS_MAP = {
    "SUCCESSFUL": SupplierOrderStatus.SUCCEEDED,
    "PENDING": SupplierOrderStatus.PENDING,
    "PROCESSING": SupplierOrderStatus.PENDING,
    "REFUNDED": SupplierOrderStatus.CANCELLED,
    "FAILED": SupplierOrderStatus.FAILED,
}

_token_cache: dict[str, tuple[str, float]] = {}


def _json(body: dict[str, Any]) -> bytes:
    """JSON with Decimal values written as exact numbers (no float rounding)."""

    def default(value: Any) -> Any:
        if isinstance(value, Decimal):
            return f"__dec__{value}"
        raise TypeError(type(value).__name__)

    text = json.dumps(body, default=default)
    for token in [v for v in body.values() if isinstance(v, Decimal)]:
        text = text.replace(f'"__dec__{token}"', str(token))
    return text.encode()


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


class ReloadlyAdapter(SupplierAdapter):
    code = "reloadly"
    title = "Reloadly Gift Cards"
    capabilities = SupplierCapabilities(
        price_list=True, balance=True, purchase=True, order_status=True, returns_codes=True, reconcile_by_key=True
    )
    credential_fields = (
        CredentialField("client_id", "Client ID", env="RELOADLY_CLIENT_ID"),
        CredentialField("client_secret", "Client Secret", env="RELOADLY_CLIENT_SECRET"),
    )
    description = (
        "Каталог подарочных карт по странам, цены с учётом скидки и сбора, баланс, заказ, получение кодов, сверка по идентификатору."
    )

    @property
    def sandbox(self) -> bool:
        return bool(self.options.get("sandbox", True))

    @property
    def base_url(self) -> str:
        return "https://giftcards-sandbox.reloadly.com" if self.sandbox else "https://giftcards.reloadly.com"

    async def _token(self) -> str:
        cache_key = f"{self.credentials.get('client_id')}:{self.sandbox}"
        cached = _token_cache.get(cache_key)
        if cached and cached[1] > time.monotonic() + 60:
            return cached[0]
        body = {
            "client_id": self.credentials.get("client_id", ""),
            "client_secret": self.credentials.get("client_secret", ""),
            "grant_type": "client_credentials",
            "audience": self.base_url,
        }
        try:
            async with client() as c:
                response = await c.post(AUTH_URL, json=body)
        except Exception as exc:  # noqa: BLE001
            raise classify(exc) from exc
        if response.status_code in (400, 401, 403):
            raise IntegrationError(
                "Reloadly отклонил ключи (проверьте client_id/client_secret и режим песочницы)", status=response.status_code
            )
        check_status(response)
        data = response.json()
        token = data.get("access_token")
        if not token:
            raise IntegrationError("Reloadly не выдал токен")
        _token_cache[cache_key] = (token, time.monotonic() + float(data.get("expires_in") or 3600))
        return token

    async def _request(
        self, method: str, path: str, *, mutating: bool = False, headers_extra: dict[str, str] | None = None, **kwargs: Any
    ) -> Any:
        token = await self._token()
        headers = {"Authorization": f"Bearer {token}", "Accept": ACCEPT, **(headers_extra or {})}
        try:
            async with client(self.base_url, headers=headers) as c:
                response = await c.request(method, path, **kwargs)
        except Exception as exc:  # noqa: BLE001
            raise classify(exc, mutating=mutating) from exc
        check_status(response, mutating=mutating)
        return response.json()

    async def check(self) -> ConnectionCheck:
        if not self.configured():
            return ConnectionCheck(False, "Не заданы client_id и client_secret")
        try:
            bal = await self.balance()
        except IntegrationError as exc:
            return ConnectionCheck(False, str(exc))
        assert bal is not None
        mode = "песочница" if self.sandbox else "боевой режим"
        return ConnectionCheck(True, f"Подключено ({mode})", bal[0], bal[1])

    async def balance(self) -> tuple[Decimal, str] | None:
        data = await with_retries(lambda: self._request("GET", "/accounts/balance"))
        amount = _dec(data.get("balance"))
        if amount is None:
            raise IntegrationError("Reloadly не вернул баланс")
        return amount, str(data.get("currencyCode") or "USD")

    async def fetch_catalog(self) -> list[CatalogItem]:
        items: list[CatalogItem] = []
        page, pages = 1, 1
        while page <= pages and page <= 50:
            data = await with_retries(lambda p=page: self._request("GET", "/products", params={"page": p, "size": 200}))
            pages = int(data.get("totalPages") or 1)
            for product in data.get("content") or []:
                items.extend(self._expand(product))
            page += 1
        return items

    @staticmethod
    def _expand(product: dict[str, Any]) -> list[CatalogItem]:
        """One catalogue item per fixed denomination. Cost in the sender (wallet)
        currency = sender denomination − discount + sender fee."""
        pid = product.get("productId")
        if pid is None:
            return []
        name = str(product.get("productName") or f"Product {pid}")
        country = (product.get("country") or {}).get("isoName") or ""
        brand = (product.get("brand") or {}).get("brandName") or ""
        category = (product.get("category") or {}).get("name") or brand
        discount = _dec(product.get("discountPercentage")) or Decimal(0)
        fee = _dec(product.get("senderFee")) or Decimal(0)
        sender_currency = str(product.get("senderCurrencyCode") or "USD")
        recipient_currency = str(product.get("recipientCurrencyCode") or "")
        out: list[CatalogItem] = []
        if str(product.get("denominationType")).upper() == "FIXED":
            recipient = product.get("fixedRecipientDenominations") or []
            sender = product.get("fixedSenderDenominations") or []
            for face, cost in zip(recipient, sender, strict=False):
                cost_d = _dec(cost)
                price = None if cost_d is None else cost_d * (Decimal(100) - discount) / Decimal(100) + fee
                out.append(
                    CatalogItem(
                        external_id=f"{pid}:{face}",
                        name=f"{name} — {face} {recipient_currency}".strip(),
                        price=price,
                        currency=sender_currency,
                        category=category,
                        region=country,
                        raw={
                            "productId": pid,
                            "countryCode": country,
                            "unitPrice": str(face),
                            "recipientCurrency": recipient_currency,
                            "brand": brand,
                            "discountPercentage": str(discount),
                            "senderFee": str(fee),
                        },
                    )
                )
        return out

    async def purchase(self, request: PurchaseRequest) -> PurchaseResult:
        product_id, _, unit_price = request.external_product_id.partition(":")
        country = str(request.buyer_data.get("country_code") or self.options.get("country_code") or "")
        body = {
            "productId": int(product_id),
            "countryCode": country,
            "quantity": request.quantity,
            "unitPrice": Decimal(unit_price) if unit_price else None,
            "customIdentifier": request.idempotency_key,
            "senderName": str(self.options.get("sender_name") or "Shop"),
        }
        if self.options.get("recipient_email"):
            body["recipientEmail"] = self.options["recipient_email"]
        try:
            data = await self._request(
                "POST", "/orders", mutating=True, content=_json(body), headers_extra={"Content-Type": "application/json"}
            )
        except IntegrationError as exc:
            if exc.uncertain:
                return PurchaseResult(
                    SupplierOrderStatus.UNKNOWN, message=f"Ответ не получен ({exc}). Будет выполнена сверка по идентификатору."
                )
            return PurchaseResult(SupplierOrderStatus.FAILED, message=str(exc))
        return await self._result_from_transaction(data)

    async def _result_from_transaction(self, data: dict[str, Any]) -> PurchaseResult:
        tx_id = data.get("transactionId")
        status = STATUS_MAP.get(str(data.get("status") or "").upper(), SupplierOrderStatus.UNKNOWN)
        result = PurchaseResult(
            status,
            external_id=None if tx_id is None else str(tx_id),
            cost=_dec(data.get("amount")),
            currency=str(data.get("currencyCode") or "USD"),
            message=f"Reloadly: {data.get('status')}",
            raw={k: data.get(k) for k in ("transactionId", "status", "amount", "discount", "fee", "currencyCode")},
        )
        if status is SupplierOrderStatus.SUCCEEDED and tx_id is not None:
            cards = await with_retries(lambda: self._request("GET", f"/orders/transactions/{tx_id}/cards"))
            for card in cards or []:
                parts = [str(card.get("cardNumber") or "").strip(), str(card.get("pinCode") or "").strip()]
                code = " / PIN ".join(p for p in parts if p) if parts[1] else parts[0]
                if code:
                    result.codes.append(code)
            if not result.codes:
                result.status = SupplierOrderStatus.UNKNOWN
                result.message = "Заказ успешен, но коды не получены — проверьте транзакцию в кабинете Reloadly"
        return result

    async def order_status(self, external_id: str) -> PurchaseResult:
        data = await with_retries(lambda: self._request("GET", f"/reports/transactions/{external_id}"))
        return await self._result_from_transaction(data.get("transaction") or data)

    async def find_by_key(self, idempotency_key: str) -> PurchaseResult | None:
        data = await with_retries(
            lambda: self._request("GET", "/reports/transactions", params={"customIdentifier": idempotency_key, "size": 5})
        )
        for tx in data.get("content") or []:
            if tx.get("customIdentifier") == idempotency_key:
                return await self._result_from_transaction(tx)
        return None
