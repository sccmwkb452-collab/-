"""Payment provider interface.

A provider creates an invoice (payment link) and answers, from its own API,
whether that invoice is paid. Nothing the user does in the chat can mark a
payment as paid: only `fetch_status` of the provider can.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Mapping

ProviderState = Literal["pending", "paid", "expired", "failed"]


class ProviderError(Exception):
    """Provider API failure. The message must not contain secrets."""


@dataclass(frozen=True)
class Invoice:
    external_id: str
    pay_url: str | None


@dataclass(frozen=True)
class ProviderStatus:
    state: ProviderState
    amount: int | None = None  # kopecks, as reported by the provider
    currency: str | None = None


@dataclass(frozen=True)
class InvoiceRequest:
    uid: str
    amount: int  # kopecks
    description: str
    ttl_seconds: int


class PaymentProvider(ABC):
    name: str
    title: str
    is_demo: bool = False
    supports_refund: bool = False

    @abstractmethod
    async def create_invoice(self, request: InvoiceRequest) -> Invoice: ...

    @abstractmethod
    async def fetch_status(self, external_id: str) -> ProviderStatus: ...

    async def parse_webhook(self, body: bytes, headers: Mapping[str, str]) -> str | None:
        """Validates a webhook and returns the external invoice id to re-check.

        The id is always re-checked through `fetch_status`, so a forged
        notification cannot credit anything.
        """
        return None

    async def refund(self, external_id: str, amount: int) -> None:
        raise ProviderError("Провайдер не поддерживает возвраты через API")

    async def close(self) -> None:
        return None
