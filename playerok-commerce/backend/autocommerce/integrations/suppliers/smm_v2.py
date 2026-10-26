"""SMM panel API v2 (the de-facto standard contract of SMM panels).

Used for VexBoost: ``https://vexboost.ru/api/v2`` answers in this format
(checked 25.10.2026 without a key: ``{"error":"user_inactive"}``). The full
documentation is in the VexBoost account after login.

Contract: POST form ``key`` + ``action``:

* ``services`` → ``[{service, name, type, category, rate, min, max, refill, cancel}]``
  (``rate`` is the price per 1000)
* ``add`` (``service``, ``link``, ``quantity``) → ``{"order": 123}``
* ``status`` (``order``) → ``{charge, start_count, status, remains, currency}``
* ``balance`` → ``{balance, currency}``
* any error → ``{"error": "..."}``

The API has no idempotency key, so a lost answer to ``add`` makes the order
UNKNOWN: the operator checks the panel's order history before anything else.
"""

from __future__ import annotations

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

STATUS_MAP = {
    "pending": SupplierOrderStatus.PENDING,
    "in progress": SupplierOrderStatus.PENDING,
    "processing": SupplierOrderStatus.PENDING,
    "completed": SupplierOrderStatus.SUCCEEDED,
    "partial": SupplierOrderStatus.SUCCEEDED,
    "canceled": SupplierOrderStatus.CANCELLED,
    "cancelled": SupplierOrderStatus.CANCELLED,
    "refunded": SupplierOrderStatus.CANCELLED,
    "fail": SupplierOrderStatus.FAILED,
    "failed": SupplierOrderStatus.FAILED,
}


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value).replace(",", "."))
    except InvalidOperation:
        return None


class SmmV2Adapter(SupplierAdapter):
    code = "smm_v2"
    title = "SMM-панель (API v2)"
    capabilities = SupplierCapabilities(price_list=True, balance=True, purchase=True, order_status=True)
    credential_fields = (
        CredentialField("api_key", "API-ключ", env="VEXBOOST_API_KEY", help="Личный кабинет VexBoost → API"),
        CredentialField("api_url", "Адрес API", secret=False, help="По умолчанию https://vexboost.ru/api/v2"),
    )
    description = "Каталог услуг и цены, баланс, создание заказа и проверка статуса через стандартный SMM API v2."

    def configured(self) -> bool:
        return bool(self.credentials.get("api_key"))

    @property
    def url(self) -> str:
        return self.credentials.get("api_url") or self.options.get("api_url") or "https://vexboost.ru/api/v2"

    async def _call(self, action: str, *, mutating: bool = False, **params: Any) -> Any:
        data = {"key": self.credentials.get("api_key", ""), "action": action, **{k: str(v) for k, v in params.items()}}
        try:
            async with client() as c:
                response = await c.post(self.url, data=data)
        except Exception as exc:  # noqa: BLE001
            raise classify(exc, mutating=mutating) from exc
        check_status(response, mutating=mutating)
        try:
            payload = response.json()
        except ValueError as exc:
            raise IntegrationError("ответ не JSON", uncertain=mutating) from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise IntegrationError(f"панель ответила: {payload['error']}")
        return payload

    async def check(self) -> ConnectionCheck:
        if not self.configured():
            return ConnectionCheck(False, "Не задан API-ключ")
        try:
            bal = await self.balance()
        except IntegrationError as exc:
            return ConnectionCheck(False, str(exc))
        assert bal is not None
        return ConnectionCheck(True, "Подключено", bal[0], bal[1])

    async def balance(self) -> tuple[Decimal, str] | None:
        payload = await with_retries(lambda: self._call("balance"))
        amount = _dec(payload.get("balance") if isinstance(payload, dict) else None)
        if amount is None:
            raise IntegrationError("панель не вернула баланс")
        return amount, str(payload.get("currency") or "RUB").upper()

    async def fetch_catalog(self) -> list[CatalogItem]:
        payload = await with_retries(lambda: self._call("services"))
        if not isinstance(payload, list):
            raise IntegrationError("список услуг в неожиданном формате")
        currency = str(self.options.get("currency") or "RUB")
        items: list[CatalogItem] = []
        for row in payload:
            if not isinstance(row, dict) or row.get("service") is None:
                continue
            items.append(
                CatalogItem(
                    external_id=str(row["service"]),
                    name=str(row.get("name") or f"Услуга {row['service']}")[:300],
                    price=_dec(row.get("rate")),
                    currency=currency,
                    category=str(row.get("category") or "")[:120],
                    price_unit=1000,
                    min_quantity=int(row["min"]) if str(row.get("min", "")).isdigit() else None,
                    max_quantity=int(row["max"]) if str(row.get("max", "")).isdigit() else None,
                    raw={k: row.get(k) for k in ("type", "refill", "cancel", "dripfeed")},
                )
            )
        return items

    async def purchase(self, request: PurchaseRequest) -> PurchaseResult:
        link = str(request.buyer_data.get("link") or "").strip()
        if not link.startswith(("http://", "https://", "@", "t.me/")):
            return PurchaseResult(SupplierOrderStatus.FAILED, message="Нет ссылки для выполнения услуги (нужна ссылка от покупателя)")
        try:
            payload = await self._call("add", mutating=True, service=request.external_product_id, link=link, quantity=request.quantity)
        except IntegrationError as exc:
            if exc.uncertain:
                return PurchaseResult(SupplierOrderStatus.UNKNOWN, message=f"Ответ не получен ({exc}). Проверьте историю заказов в панели.")
            return PurchaseResult(SupplierOrderStatus.FAILED, message=str(exc))
        order_id = payload.get("order") if isinstance(payload, dict) else None
        if not order_id:
            return PurchaseResult(SupplierOrderStatus.UNKNOWN, message="Панель не вернула номер заказа", raw={"answer": payload})
        return PurchaseResult(SupplierOrderStatus.PENDING, external_id=str(order_id), message="Заказ принят панелью")

    async def order_status(self, external_id: str) -> PurchaseResult:
        payload = await with_retries(lambda: self._call("status", order=external_id))
        status_text = str(payload.get("status") or "").strip().lower()
        status = STATUS_MAP.get(status_text, SupplierOrderStatus.PENDING)
        return PurchaseResult(
            status,
            external_id=external_id,
            cost=_dec(payload.get("charge")),
            currency=str(payload.get("currency") or "RUB").upper(),
            message=f"Статус панели: {payload.get('status')}, осталось: {payload.get('remains')}",
            raw={k: payload.get(k) for k in ("status", "remains", "start_count", "charge")},
        )
