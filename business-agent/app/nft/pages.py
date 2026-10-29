"""Публичные страницы NFT-подарков Telegram: https://t.me/nft/<Slug>-<номер>.

Даёт реальные атрибуты (модель, фон, символ и их редкость) и публичного владельца.
Цен на этих страницах нет — рыночные данные берутся только из MarketPrice.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, dataclass, field

import aiohttp
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

BASE_URL = "https://t.me/nft"
USER_AGENT = "Mozilla/5.0 (compatible; BusinessAgent/1.0)"
ROW_ALIASES = {
    "owner": "owner", "владелец": "owner",
    "model": "model", "модель": "model",
    "backdrop": "backdrop", "фон": "backdrop",
    "symbol": "symbol", "узор": "symbol", "символ": "symbol",
    "quantity": "quantity", "количество": "quantity",
}
_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_QUANTITY_RE = re.compile(r"([\d\s  ,]+)\s*/\s*([\d\s  ,]+)")
GIFT_LINK_RE = re.compile(r"(?:https?://)?t\.me/nft/([A-Za-z0-9]+)-(\d+)", re.I)


@dataclass
class GiftAttribute:
    name: str
    rarity_percent: float | None = None


@dataclass
class GiftPage:
    slug: str
    number: int
    url: str
    title: str | None = None
    owner_name: str | None = None
    owner_link: str | None = None
    model: GiftAttribute | None = None
    backdrop: GiftAttribute | None = None
    symbol: GiftAttribute | None = None
    issued: int | None = None
    total: int | None = None
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def owner_username(self) -> str | None:
        if self.owner_link:
            m = re.match(r"https?://t\.me/([A-Za-z0-9_]{4,32})/?$", self.owner_link)
            if m:
                return m.group(1).lower()
        return None

    def to_dict(self) -> dict:
        return asdict(self)


def find_gift_links(text: str) -> list[tuple[str, int]]:
    return [(m.group(1), int(m.group(2))) for m in GIFT_LINK_RE.finditer(text or "")]


def _attr(td) -> GiftAttribute:
    mark = td.find("mark")
    rarity = None
    if mark:
        m = _PERCENT_RE.search(mark.get_text())
        if m:
            rarity = float(m.group(1).replace(",", "."))
        mark.extract()
    return GiftAttribute(td.get_text(" ", strip=True), rarity)


def _digits(raw: str) -> int | None:
    d = re.sub(r"\D", "", raw)
    return int(d) if d else None


def parse_gift_html(html: str, slug: str, number: int) -> GiftPage | None:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile("tgme_gift_table")) or soup.find("table")
    if table is None:
        return None
    og = soup.find("meta", attrs={"property": "og:title"})
    gift = GiftPage(slug, number, f"{BASE_URL}/{slug}-{number}", title=og["content"].strip() if og and og.get("content") else None)
    for tr in table.find_all("tr"):
        th, td = tr.find("th"), tr.find("td")
        if not th or not td:
            continue
        label = th.get_text(" ", strip=True)
        key = ROW_ALIASES.get(label.lower())
        if key == "owner":
            link = td.find("a")
            gift.owner_name = td.get_text(" ", strip=True) or None
            gift.owner_link = link["href"] if link and link.get("href") else None
        elif key in ("model", "backdrop", "symbol"):
            setattr(gift, key, _attr(td))
        elif key == "quantity":
            m = _QUANTITY_RE.search(td.get_text(" ", strip=True))
            if m:
                gift.issued, gift.total = _digits(m.group(1)), _digits(m.group(2))
        else:
            gift.extra[label] = td.get_text(" ", strip=True)
    if not (gift.model or gift.backdrop or gift.symbol or gift.owner_name):
        return None
    return gift


class GiftPageClient:
    def __init__(self, *, delay: float = 0.5, retries: int = 3, timeout: float = 15, lang: str = "en",
                 session: aiohttp.ClientSession | None = None, base_url: str = BASE_URL) -> None:
        self.delay = delay
        self.retries = retries
        self.lang = lang
        self.base_url = base_url
        self._session = session
        self._own = session is None
        self._timeout = aiohttp.ClientTimeout(total=timeout)

    async def _get(self, url: str) -> str | None:
        if self._session is None:
            self._session = aiohttp.ClientSession(
                timeout=self._timeout, headers={"User-Agent": USER_AGENT, "Accept-Language": self.lang}, trust_env=True
            )
        for attempt in range(1, self.retries + 1):
            try:
                async with self._session.get(url) as resp:
                    if resp.status == 404:
                        return None
                    if resp.status == 429:
                        await asyncio.sleep(float(resp.headers.get("Retry-After", 5 * attempt)))
                        continue
                    resp.raise_for_status()
                    html = await resp.text()
                await asyncio.sleep(self.delay)
                return html
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning("t.me/nft %s попытка %d: %s", url, attempt, exc)
                await asyncio.sleep(2**attempt)
        raise ConnectionError(f"не удалось загрузить {url}")

    async def get(self, slug: str, number: int) -> GiftPage | None:
        html = await self._get(f"{self.base_url}/{slug}-{number}")
        return parse_gift_html(html, slug, number) if html else None

    async def close(self) -> None:
        if self._own and self._session is not None:
            await self._session.close()
            self._session = None
