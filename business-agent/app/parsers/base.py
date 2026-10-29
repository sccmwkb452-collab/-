"""Унифицированный интерфейс парсеров (ParserAdapter)."""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.db.models import ParserConfig


@dataclass
class SearchCriteria:
    target_role: str = "any"  # seller | buyer | any
    keywords: list[str] = field(default_factory=list)
    filters: dict[str, Any] = field(default_factory=dict)  # атрибут → подстрока
    geo: str | None = None
    ranges: dict[str, dict[str, str]] = field(default_factory=dict)  # поле → {"min": .., "max": ..}
    max_results: int = 200

    @classmethod
    def from_config(cls, cfg: ParserConfig) -> "SearchCriteria":
        return cls(
            target_role=cfg.target_role or "any",
            keywords=[str(k) for k in cfg.keywords or []],
            filters=dict(cfg.filters or {}),
            geo=cfg.geo,
            ranges=dict(cfg.ranges or {}),
            max_results=int((cfg.stop_rules or {}).get("max_results", 200)),
        )


@dataclass
class Candidate:
    """Нормализованный результат. Только данные из источника."""

    external_id: str
    telegram_user_id: int | None = None
    username: str | None = None
    display_name: str | None = None
    role: str | None = None
    text: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)
    price: Decimal | None = None
    currency: str | None = None
    geo: str | None = None
    source_url: str | None = None

    @property
    def reachable(self) -> bool:
        return bool(self.telegram_user_id or self.username)

    def profile(self) -> dict[str, Any]:
        data = {
            "name": self.display_name, "role": self.role, "text": self.text, "attributes": self.attributes,
            "price": str(self.price) if self.price is not None else None, "currency": self.currency,
            "geo": self.geo, "source_url": self.source_url,
        }
        return {k: v for k, v in data.items() if v not in (None, "", {}, [])}


class ParserError(Exception):
    pass


class ParserAdapter(ABC):
    key: str
    title: str
    description: str

    def __init__(self, config: ParserConfig) -> None:
        self.config = config

    async def connect(self) -> None:
        return None

    @abstractmethod
    async def validate(self) -> tuple[bool, str]:
        """Проверка, что источник доступен и настроен. (ok, сообщение для пользователя)."""

    @abstractmethod
    def search(self, criteria: SearchCriteria) -> AsyncIterator[dict[str, Any]]:
        """Сырые записи источника."""

    async def fetch_profile(self, external_id: str) -> dict[str, Any] | None:
        return None

    async def fetch_available_context(self, candidate: Candidate) -> dict[str, Any]:
        return candidate.profile()

    @abstractmethod
    def normalize_result(self, raw: dict[str, Any]) -> Candidate | None: ...

    async def disconnect(self) -> None:
        return None
