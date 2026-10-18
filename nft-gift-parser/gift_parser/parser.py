"""Загрузка и разбор страниц NFT-подарков вида https://t.me/nft/<Slug>-<номер>."""
import asyncio
import logging
import re
from collections.abc import AsyncIterator, Iterable

import aiohttp
from bs4 import BeautifulSoup

from gift_parser.models import Attribute, Gift

logger = logging.getLogger(__name__)

BASE_URL = "https://t.me/nft"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)

# Названия строк таблицы → поле модели (Telegram отдаёт страницу на языке
# из Accept-Language, поэтому поддерживаем и английский, и русский).
ROW_ALIASES = {
    "owner": "owner", "владелец": "owner",
    "model": "model", "модель": "model",
    "backdrop": "backdrop", "фон": "backdrop",
    "symbol": "symbol", "узор": "symbol", "символ": "symbol",
    "quantity": "quantity", "количество": "quantity",
}

_PERCENT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*%")
_QUANTITY_RE = re.compile(r"([\d\s  ,]+)\s*/\s*([\d\s  ,]+)")
_SLUG_URL_RE = re.compile(r"(?:https?://)?t\.me/nft/([A-Za-z0-9]+)-(\d+)", re.I)


def gift_url(slug: str, number: int) -> str:
    return f"{BASE_URL}/{slug}-{number}"


def parse_gift_ref(ref: str) -> tuple[str, int]:
    """'https://t.me/nft/PlushPepe-12' или 'PlushPepe-12' → ('PlushPepe', 12)."""
    ref = ref.strip()
    m = _SLUG_URL_RE.search(ref) or re.fullmatch(r"([A-Za-z0-9]+)-(\d+)", ref)
    if not m:
        raise ValueError(f"Не удалось разобрать ссылку на подарок: {ref!r}")
    return m.group(1), int(m.group(2))


def _to_int(raw: str) -> int | None:
    digits = re.sub(r"\D", "", raw)
    return int(digits) if digits else None


def _parse_attribute(td) -> Attribute:
    mark = td.find("mark")
    rarity = None
    if mark:
        m = _PERCENT_RE.search(mark.get_text())
        if m:
            rarity = float(m.group(1).replace(",", "."))
        mark.extract()
    return Attribute(name=td.get_text(" ", strip=True), rarity=rarity)


def _meta(soup: BeautifulSoup, prop: str) -> str | None:
    tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
    return tag["content"].strip() if tag and tag.get("content") else None


def parse_gift_html(html: str, slug: str, number: int) -> Gift | None:
    """Разбирает HTML страницы подарка. Возвращает None, если подарка нет."""
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_=re.compile("tgme_gift_table")) or soup.find("table")
    if table is None:
        return None

    gift = Gift(
        slug=slug,
        number=number,
        url=gift_url(slug, number),
        title=_meta(soup, "og:title"),
        image=_meta(soup, "og:image"),
    )

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
            setattr(gift, key, _parse_attribute(td))
        elif key == "quantity":
            m = _QUANTITY_RE.search(td.get_text(" ", strip=True))
            if m:
                gift.issued, gift.total = _to_int(m.group(1)), _to_int(m.group(2))
        else:
            gift.extra[label] = td.get_text(" ", strip=True)

    # Пустая таблица — значит, такого номера не существует.
    if not (gift.model or gift.backdrop or gift.symbol or gift.owner_name):
        return None
    return gift


class GiftParser:
    """Асинхронный загрузчик страниц с ограничением параллельности и повторами."""

    def __init__(
        self,
        concurrency: int = 5,
        delay: float = 0.2,
        retries: int = 3,
        timeout: float = 15.0,
        lang: str = "en",
        proxy: str | None = None,
    ) -> None:
        self._sem = asyncio.Semaphore(concurrency)
        self._delay = delay
        self._retries = retries
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._lang = lang
        self._proxy = proxy
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "GiftParser":
        self._session = aiohttp.ClientSession(
            timeout=self._timeout,
            headers={"User-Agent": USER_AGENT, "Accept-Language": self._lang},
            trust_env=True,
        )
        return self

    async def __aexit__(self, *exc) -> None:
        if self._session:
            await self._session.close()

    async def _fetch(self, url: str) -> str | None:
        assert self._session is not None, "используйте `async with GiftParser()`"
        for attempt in range(1, self._retries + 1):
            try:
                async with self._sem:
                    async with self._session.get(url, proxy=self._proxy) as resp:
                        if resp.status == 404:
                            return None
                        if resp.status == 429:
                            wait = float(resp.headers.get("Retry-After", 5 * attempt))
                            logger.warning("429 на %s, жду %.0f с", url, wait)
                            await asyncio.sleep(wait)
                            continue
                        resp.raise_for_status()
                        html = await resp.text()
                    await asyncio.sleep(self._delay)
                    return html
            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                logger.warning("Ошибка %s (попытка %d/%d): %s", url, attempt, self._retries, exc)
                await asyncio.sleep(2 ** attempt)
        logger.error("Не удалось загрузить %s", url)
        return None

    async def get_gift(self, slug: str, number: int) -> Gift | None:
        html = await self._fetch(gift_url(slug, number))
        return parse_gift_html(html, slug, number) if html else None

    async def get_many(self, refs: Iterable[tuple[str, int]]) -> AsyncIterator[Gift]:
        """Параллельно загружает подарки, отдаёт их по мере готовности."""
        tasks = [asyncio.create_task(self.get_gift(s, n)) for s, n in refs]
        try:
            for fut in asyncio.as_completed(tasks):
                gift = await fut
                if gift:
                    yield gift
        finally:
            for t in tasks:
                t.cancel()

    async def get_collection(
        self, slug: str, start: int = 1, end: int | None = None
    ) -> AsyncIterator[Gift]:
        """Парсит коллекцию. Если `end` не задан, берёт общее количество со страницы `start`."""
        first = await self.get_gift(slug, start)
        if first is None:
            logger.error("Подарок %s-%d не найден", slug, start)
            return
        yield first
        if end is None:
            end = first.total or first.issued or start
            logger.info("Коллекция %s: %d шт.", slug, end)
        async for gift in self.get_many((slug, n) for n in range(start + 1, end + 1)):
            yield gift
