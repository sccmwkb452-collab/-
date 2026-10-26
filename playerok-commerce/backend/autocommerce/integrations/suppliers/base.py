"""Common interface for suppliers.

Rules every adapter follows:

* ``purchase`` is never retried inside the adapter. A timeout or an unclear
  answer returns ``UNKNOWN`` and the order goes to manual reconciliation —
  a second automatic attempt could buy the same goods twice.
* Read-only calls (catalogue, balance, status) may be retried.
* An adapter without a purchasing API raises ``PurchaseNotSupported`` and
  the order manager shows «Требуется ручная закупка».
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, ClassVar

from ...database.enums import SupplierOrderStatus


class PurchaseNotSupported(Exception):
    """The supplier has no permitted automated purchasing method."""


@dataclass(frozen=True)
class SupplierCapabilities:
    price_list: bool = False
    balance: bool = False
    purchase: bool = False
    order_status: bool = False
    returns_codes: bool = False
    reconcile_by_key: bool = False


@dataclass(frozen=True)
class CredentialField:
    name: str
    label: str
    secret: bool = True
    env: str | None = None
    help: str = ""


@dataclass
class CatalogItem:
    external_id: str
    name: str
    price: Decimal | None
    currency: str
    category: str = ""
    price_unit: int = 1
    min_quantity: int | None = None
    max_quantity: int | None = None
    region: str = ""
    available: bool = True
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectionCheck:
    ok: bool
    message: str
    balance: Decimal | None = None
    currency: str | None = None


@dataclass
class PurchaseRequest:
    idempotency_key: str
    external_product_id: str
    quantity: int
    expected_unit_cost: Decimal | None = None
    buyer_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PurchaseResult:
    status: SupplierOrderStatus
    external_id: str | None = None
    cost: Decimal | None = None
    currency: str | None = None
    codes: list[str] = field(default_factory=list)  # secrets: encrypted right after receipt, never logged
    message: str = ""
    raw: dict[str, Any] = field(default_factory=dict)  # scrubbed before storage


class SupplierAdapter(ABC):
    code: ClassVar[str]
    title: ClassVar[str]
    capabilities: ClassVar[SupplierCapabilities]
    credential_fields: ClassVar[tuple[CredentialField, ...]] = ()
    # Short honest description of what the integration can and cannot do.
    description: ClassVar[str] = ""

    def __init__(self, credentials: dict[str, str] | None = None, options: dict[str, Any] | None = None):
        self.credentials = credentials or {}
        self.options = options or {}

    def configured(self) -> bool:
        return all(self.credentials.get(f.name) for f in self.credential_fields)

    @abstractmethod
    async def check(self) -> ConnectionCheck: ...

    async def fetch_catalog(self) -> list[CatalogItem]:
        return []

    async def balance(self) -> tuple[Decimal, str] | None:
        return None

    async def purchase(self, request: PurchaseRequest) -> PurchaseResult:
        raise PurchaseNotSupported(f"{self.title}: автоматическая закупка не поддерживается")

    async def order_status(self, external_id: str) -> PurchaseResult:
        raise PurchaseNotSupported(f"{self.title}: статус заказа через API недоступен")

    async def find_by_key(self, idempotency_key: str) -> PurchaseResult | None:
        """Look up an order by our idempotency key (reconciliation of UNKNOWN orders)."""
        return None
