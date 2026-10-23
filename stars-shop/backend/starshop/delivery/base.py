"""Delivery provider interface.

A delivery provider is whatever actually credits Telegram Stars to the
recipient. The shop never fakes this step: the DEMO provider is clearly
labelled and only runs for DEMO orders; real deliveries go through the
manual (operator + Fragment) provider or an HTTP supplier adapter.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

from ..shared.errors import ProviderError


class DeliveryError(ProviderError):
    code = "delivery_error"
    message = "Не удалось выполнить доставку"


@dataclass(slots=True)
class DeliveryRequest:
    idempotency_key: str
    order_id: uuid.UUID
    order_number: str
    stars: int
    recipient_username: str | None
    recipient_telegram_id: int | None
    is_demo: bool


@dataclass(slots=True)
class DeliveryOutcome:
    status: Literal["succeeded", "pending", "needs_attention", "failed"]
    external_id: str | None = None
    message: str | None = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RecipientCheck:
    ok: bool
    display_name: str | None = None
    reason: str | None = None


@dataclass(slots=True)
class DeliveryCallback:
    external_id: str
    outcome: DeliveryOutcome


class DeliveryProvider(ABC):
    name: str = ""
    title: str = ""
    is_demo: bool = False
    # Supplier de-duplicates requests by idempotency key, so a retry after an
    # ambiguous failure (timeout) cannot deliver twice.
    idempotent: bool = False
    supports_gift_to_others: bool = True
    requires_username: bool = True
    min_stars: int = 50
    max_stars: int = 1_000_000

    def is_configured(self) -> bool:
        return True

    @abstractmethod
    async def deliver(self, request: DeliveryRequest) -> DeliveryOutcome: ...

    async def check(self, external_id: str, request: DeliveryRequest) -> DeliveryOutcome:
        return DeliveryOutcome(status="pending", external_id=external_id)

    async def check_recipient(self, username: str) -> RecipientCheck:
        return RecipientCheck(ok=True)

    def parse_callback(self, headers: dict[str, str], body: bytes) -> DeliveryCallback:
        raise DeliveryError("Provider does not accept callbacks", retryable=False)
