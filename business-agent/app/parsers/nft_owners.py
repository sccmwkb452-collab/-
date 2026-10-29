"""Публичные владельцы NFT-подарков (страницы t.me/nft) — потенциальные продавцы.

Берутся только владельцы с публичным профилем. Telegram ID на странице нет, поэтому
первое сообщение таким контактам отправляет человек (см. ограничения Business API).
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator
from typing import Any

from app.nft.pages import GIFT_LINK_RE, GiftPageClient
from app.parsers.base import Candidate, ParserAdapter, SearchCriteria

DEFAULT_SCAN = 200


def parse_collection(resource: str) -> str | None:
    resource = (resource or "").strip()
    m = GIFT_LINK_RE.search(resource)
    if m:
        return m.group(1)
    return resource if re.fullmatch(r"[A-Za-z0-9]{3,64}", resource) else None


class NftOwnersAdapter(ParserAdapter):
    key = "nft_owners"
    title = "Владельцы NFT-подарков (t.me/nft)"
    description = "Публичные страницы подарков: атрибуты, редкость, владелец"

    def __init__(self, config, client: GiftPageClient | None = None) -> None:
        super().__init__(config)
        self.client = client or GiftPageClient()
        self.slug = parse_collection(config.resource)

    async def validate(self) -> tuple[bool, str]:
        if not self.slug:
            return False, "Укажите коллекцию: slug (например PlushPepe) или ссылку t.me/nft/PlushPepe-1"
        try:
            page = await self.client.get(self.slug, 1)
        except ConnectionError as exc:
            return False, f"t.me недоступен: {exc}"
        if page is None:
            return False, f"Коллекция {self.slug} не найдена"
        return True, f"Коллекция {self.slug}: выпущено {page.issued or '?'} из {page.total or '?'}"

    async def search(self, criteria: SearchCriteria) -> AsyncIterator[dict[str, Any]]:
        if not self.slug:
            return
        rng = criteria.ranges.get("number", {})
        start = int(rng.get("min") or 1)
        end = int(rng.get("max") or start + min(criteria.max_results, DEFAULT_SCAN) - 1)
        end = min(end, start + criteria.max_results - 1)
        for number in range(start, end + 1):
            page = await self.client.get(self.slug, number)
            if page is not None:
                yield page.to_dict() | {"owner_username": page.owner_username}

    def normalize_result(self, raw: dict[str, Any]) -> Candidate | None:
        if not raw.get("owner_username"):
            return None  # владелец скрыт — связаться нельзя
        attrs: dict[str, Any] = {"gift": f"{raw['slug']}-{raw['number']}"}
        for key in ("model", "backdrop", "symbol"):
            if raw.get(key):
                attrs[key] = raw[key]["name"]
                if raw[key].get("rarity_percent") is not None:
                    attrs[f"{key}_rarity_percent"] = raw[key]["rarity_percent"]
        return Candidate(
            external_id=f"{raw['slug']}-{raw['number']}",
            username=raw["owner_username"],
            display_name=raw.get("owner_name"),
            role="seller",
            text=raw.get("title"),
            attributes=attrs,
            source_url=raw.get("url"),
        )

    async def disconnect(self) -> None:
        await self.client.close()
