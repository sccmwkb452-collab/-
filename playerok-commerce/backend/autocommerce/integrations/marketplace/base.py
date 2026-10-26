"""Marketplace integration interface.

Every operation the system wants from PlayerOK is a capability. The UI and
the automation read capabilities and show «Интеграция недоступна» with the
reason instead of pretending that something works.
"""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

CAPABILITY_LABELS: dict[str, str] = {
    "fetch_orders": "Получение заказов",
    "fetch_messages": "Получение сообщений покупателей",
    "send_messages": "Отправка сообщений покупателям",
    "publish_listings": "Публикация объявлений",
    "update_listings": "Изменение цены и описания объявлений",
    "raise_listings": "Поднятие объявлений",
    "confirm_deals": "Подтверждение сделок",
    "fetch_reviews": "Получение отзывов",
    "fetch_market": "Цены конкурентов",
    "presence": "Статус «в сети»",
}


@dataclass(frozen=True)
class MarketplaceCapabilities:
    fetch_orders: bool = False
    fetch_messages: bool = False
    send_messages: bool = False
    publish_listings: bool = False
    update_listings: bool = False
    raise_listings: bool = False
    confirm_deals: bool = False
    fetch_reviews: bool = False
    fetch_market: bool = False
    presence: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {name: getattr(self, name) for name in CAPABILITY_LABELS}


@dataclass
class ExternalOrder:
    external_id: str
    created_at: datetime
    product_ref: str
    quantity: int
    unit_price: Decimal
    buyer_name: str | None = None
    status: str = ""
    buyer_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ExternalMessage:
    external_id: str
    chat_id: str
    buyer_name: str | None
    text: str
    sent_at: datetime
    order_external_id: str | None = None


class MarketplaceUnavailable(Exception):
    def __init__(self, capability: str, reason: str):
        super().__init__(reason)
        self.capability = capability
        self.reason = reason


class MarketplaceAdapter(ABC):
    code: ClassVar[str]
    title: ClassVar[str]
    capabilities: ClassVar[MarketplaceCapabilities]
    unavailable_reason: ClassVar[str] = ""

    def reason(self, capability: str) -> str:
        return self.unavailable_reason

    def supports(self, capability: str) -> bool:
        return bool(getattr(self.capabilities, capability, False))

    def _unavailable(self, capability: str) -> MarketplaceUnavailable:
        return MarketplaceUnavailable(capability, self.reason(capability))

    async def fetch_orders(self, since: datetime | None) -> list[ExternalOrder]:
        raise self._unavailable("fetch_orders")

    async def fetch_messages(self, since: datetime | None) -> list[ExternalMessage]:
        raise self._unavailable("fetch_messages")

    async def send_message(self, chat_id: str, text: str) -> None:
        raise self._unavailable("send_messages")

    async def publish_listing(self, listing: dict[str, Any]) -> str:
        raise self._unavailable("publish_listings")

    async def update_listing(self, external_id: str, changes: dict[str, Any]) -> None:
        raise self._unavailable("update_listings")

    async def raise_listing(self, external_id: str) -> None:
        raise self._unavailable("raise_listings")

    async def confirm_deal(self, external_id: str) -> None:
        raise self._unavailable("confirm_deals")
