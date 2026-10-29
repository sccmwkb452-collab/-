"""Структурированное состояние диалога/сделки (хранится в Conversation.state)."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class Stage(StrEnum):
    NEW = "new"
    GREETING = "greeting"
    DISCOVERY = "discovery"
    NEGOTIATION = "negotiation"
    AGREED = "agreed"
    DEAL_PENDING = "deal_pending"
    DEAL_CREATED = "deal_created"
    CLOSED = "closed"
    DECLINED = "declined"


class DealState(BaseModel):
    conversation_stage: Stage = Stage.NEW
    counterparty_role: str | None = None  # seller | buyer
    product_type: str | None = None
    item_description: str | None = None
    item_attributes: dict[str, str] = Field(default_factory=dict)
    quantity: int | None = None
    seller_price: str | None = None
    buyer_target_price: str | None = None
    agreed_price: str | None = None
    currency: str | None = None
    payment_method: str | None = None
    trade_bot: str | None = None  # только из настроек владельца, никогда из переписки
    deal_status: str = "not_created"
    deal_id: int | None = None
    objections: list[str] = Field(default_factory=list)
    agreements: list[str] = Field(default_factory=list)
    suspicious_links: list[str] = Field(default_factory=list)
    last_action: str | None = None
    requires_human_review: bool = False
    human_review_reason: str | None = None
    interest_level: str | None = None

    @classmethod
    def load(cls, raw: dict[str, Any] | None) -> "DealState":
        return cls.model_validate(raw or {})

    def dump(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def price_decimal(self) -> Decimal | None:
        return to_decimal(self.agreed_price)


def to_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    cleaned = str(value).replace(" ", "").replace(" ", "").replace(",", ".")
    try:
        result = Decimal(cleaned)
    except InvalidOperation:
        return None
    if not result.is_finite() or result < 0:
        return None
    return result


# Нормализация валют: синонимы из разговорной речи → код.
CURRENCY_ALIASES: dict[str, str] = {
    "ton": "TON", "тон": "TON", "тонн": "TON", "тонов": "TON", "тонах": "TON",
    "usdt": "USDT", "юсдт": "USDT", "тезер": "USDT", "tether": "USDT",
    "usdc": "USDC", "btc": "BTC", "биткоин": "BTC", "eth": "ETH", "эфир": "ETH",
    "ltc": "LTC", "bnb": "BNB", "trx": "TRX",
    "stars": "XTR", "star": "XTR", "звезд": "XTR", "звёзд": "XTR", "звезды": "XTR", "звёзды": "XTR", "xtr": "XTR", "⭐": "XTR",
    "rub": "RUB", "руб": "RUB", "рублей": "RUB", "₽": "RUB",
    "usd": "USD", "$": "USD", "долларов": "USD", "eur": "EUR", "€": "EUR",
}


def normalize_currency(value: str | None) -> str | None:
    if not value:
        return None
    key = value.strip().lower()
    if key in CURRENCY_ALIASES:
        return CURRENCY_ALIASES[key]
    upper = value.strip().upper()
    return upper if upper.isalpha() and 2 <= len(upper) <= 6 else None
