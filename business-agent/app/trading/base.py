"""Интерфейс адаптеров торговых ботов.

Telegram-боты не могут общаться с другими ботами через Bot API, поэтому автоматизировать
сделку можно только если у торгового сервиса есть публичный API. Каждый адаптер честно
объявляет, какие операции поддерживает; всё остальное — REQUIRES_USER_ACTION для человека.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class Capability(StrEnum):
    CHECK = "check"  # проверка доступности
    CREATE_INVOICE = "create_invoice"  # мы продаём: счёт покупателю
    CREATE_DEAL = "create_deal"  # сделка/эскроу в торговом боте
    DEAL_STATUS = "deal_status"
    PAY = "pay"  # мы покупаем: перевод продавцу
    PAYMENT_STATUS = "payment_status"
    BALANCE = "balance"
    EXCHANGE_RATES = "exchange_rates"
    IDEMPOTENT_PAYMENTS = "idempotent_payments"  # повтор с тем же ключом не спишет дважды


class OpStatus(StrEnum):
    SUCCESS = "success"
    PENDING = "pending"
    FAILED = "failed"
    UNKNOWN = "unknown"  # таймаут/обрыв: результат неизвестен — только сверка
    NOT_FOUND = "not_found"
    NOT_SUPPORTED = "not_supported"
    REQUIRES_USER_ACTION = "requires_user_action"


@dataclass
class OpResult:
    status: OpStatus
    external_id: str | None = None
    url: str | None = None
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    instructions: str | None = None


@dataclass
class DealRequest:
    deal_id: int
    side: str  # buy | sell
    amount: Decimal
    currency: str
    description: str
    counterparty_telegram_id: int | None
    idempotency_key: str


@dataclass
class AvailabilityResult:
    ok: bool
    capabilities: list[Capability]
    currencies: list[str]
    error: str | None = None
    info: dict[str, Any] = field(default_factory=dict)


class TradeBotAdapter(ABC):
    key: str
    title: str
    # Официальные username ботов, которым соответствует адаптер (None — любой, выбранный пользователем).
    official_usernames: set[str] | None = None
    manual_only: bool = False

    @abstractmethod
    async def check(self) -> AvailabilityResult: ...

    @abstractmethod
    def static_capabilities(self) -> list[Capability]: ...

    async def create_invoice(self, req: DealRequest) -> OpResult:
        return OpResult(OpStatus.NOT_SUPPORTED, error=f"{self.title}: выставление счёта не поддерживается")

    async def create_deal(self, req: DealRequest) -> OpResult:
        return OpResult(OpStatus.NOT_SUPPORTED, error=f"{self.title}: создание сделки не поддерживается")

    async def deal_status(self, external_id: str) -> OpResult:
        return OpResult(OpStatus.NOT_SUPPORTED, error=f"{self.title}: статус сделки не поддерживается")

    async def pay(self, req: DealRequest, spend_id: str) -> OpResult:
        return OpResult(OpStatus.NOT_SUPPORTED, error=f"{self.title}: оплата через API не поддерживается")

    async def payment_status(self, spend_id: str, external_id: str | None) -> OpResult:
        return OpResult(OpStatus.NOT_SUPPORTED, error=f"{self.title}: статус оплаты не поддерживается")

    async def exchange_rates(self) -> dict[tuple[str, str], Decimal]:
        return {}

    async def close(self) -> None:
        return None
