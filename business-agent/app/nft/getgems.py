"""Floor Telegram-подарков с Getgems через официальный Public API.

Документация: https://api.getgems.io/public-api/docs, ключ — https://getgems.io/public-api
(заголовок Authorization; лимит 400 запросов / 5 мин с IP). Внутренний GraphQL сайта не используется.

Как считается floor (правила владельца):
- символ не учитывается;
- фон учитывается только премиальный (по умолчанию Black и Onyx Black): тогда floor — самый дешёвый
  листинг с той же моделью и тем же фоном;
- иначе floor — минимальная цена модели (minPrice атрибута Model), без модели — floor коллекции.
Цены — только из ответов API; нет листингов — нет цены.
"""
from __future__ import annotations

import asyncio
import difflib
import logging
import os
import re
import ssl
import time
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

BASE_URL = "https://api.getgems.io/public-api"
NANO = Decimal(10) ** 9


class GetgemsError(Exception):
    pass


@dataclass
class GiftQuote:
    collection: str
    model: str | None = None
    backdrop: str | None = None
    floor: Decimal | None = None
    currency: str = "TON"
    basis: str = ""
    source: str = "Getgems"
    fetched_at: float = field(default_factory=time.time)
    error: str | None = None

    def render(self, markup_min: Decimal, markup_max: Decimal) -> str:
        what = " / ".join(x for x in (self.collection, self.model and f"модель {self.model}",
                                      self.backdrop and f"фон {self.backdrop}") if x)
        if self.floor is None:
            return f"- {what}: floor ({self.source}) не найден ({self.error or 'нет листингов'}) — цену не называть"
        a = (self.floor * (1 + markup_min / 100)).quantize(Decimal("0.01"))
        b = (self.floor * (1 + markup_max / 100)).quantize(Decimal("0.01"))
        when = time.strftime("%Y-%m-%d %H:%M", time.gmtime(self.fetched_at))
        return (f"- {what}: floor {fmt(self.floor)} {self.currency} ({self.source}, {self.basis}, {when} UTC)"
                f" → предложение {fmt(a)}–{fmt(b)} {self.currency}")


def fmt(value: Decimal) -> str:
    """100 вместо 1E+2."""
    return format(value.normalize(), "f")


def _norm(value: str | None) -> str:
    value = re.sub(r"\s*\([^)]*%\)\s*$", "", value or "")  # «Pumpkin (1.2%)» → «Pumpkin»
    return re.sub(r"[^a-z0-9а-яё]+", "", value.lower())


def _match(name: str | None, options: list[str], cutoff: float = 0.8) -> str | None:
    if not name or not options:
        return None
    by_norm = {_norm(o): o for o in options}
    key = _norm(name)
    if key in by_norm:
        return by_norm[key]
    close = difflib.get_close_matches(key, list(by_norm), n=1, cutoff=cutoff)
    return by_norm[close[0]] if close else None


def _nano_to_ton(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value)) / NANO if value not in (None, "") else None
    except InvalidOperation:
        return None


def _sale_price(item: dict[str, Any]) -> Decimal | None:
    sale = item.get("sale") or {}
    if sale.get("type") != "FixPriceSale" or (sale.get("currency") or "TON") != "TON":
        return None
    return _nano_to_ton(sale.get("fullPrice"))


def _attr(item: dict[str, Any], trait: str) -> str | None:
    for a in item.get("attributes") or []:
        if (a.get("traitType") or a.get("trait_type") or "").lower() == trait:
            return a.get("value")
    return None


class GetgemsClient:
    def __init__(self, api_key: str, *, base_url: str = BASE_URL, premium_backdrops: list[str] | None = None,
                 cache_seconds: int = 600, max_pages: int = 10, timeout: float = 20) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.premium_backdrops = premium_backdrops if premium_backdrops is not None else ["Black", "Onyx Black"]
        self.cache_seconds = cache_seconds
        self.max_pages = max_pages
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._cache: dict[Any, tuple[float, Any]] = {}
        self._lock = asyncio.Lock()

    # ── HTTP ──────────────────────────────────────────────────────────────

    def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            cafile = os.environ.get("SSL_CERT_FILE")
            connector = None
            if cafile and os.path.exists(cafile):
                connector = aiohttp.TCPConnector(ssl=ssl.create_default_context(cafile=cafile))
            self._session = aiohttp.ClientSession(timeout=self._timeout, trust_env=True, connector=connector)
        return self._session

    async def _get(self, path: str, **params: Any) -> Any:
        clean = {k: v for k, v in params.items() if v is not None}
        try:
            async with self._get_session().get(f"{self.base_url}{path}", params=clean,
                                               headers={"Authorization": self.api_key, "accept": "application/json"}) as resp:
                if resp.status in (401, 403):
                    raise GetgemsError("ключ Getgems отклонён или не оплачен")
                if resp.status == 429 or "json" not in (resp.content_type or ""):
                    raise GetgemsError(f"Getgems ограничил запросы (HTTP {resp.status})")
                payload = await resp.json()
        except (aiohttp.ClientError, TimeoutError) as exc:
            raise GetgemsError(f"Getgems недоступен: {exc or type(exc).__name__}") from exc
        if not isinstance(payload, dict) or not payload.get("success"):
            raise GetgemsError(f"Getgems вернул ошибку: HTTP {resp.status}")
        return payload.get("response")

    async def _cached(self, key: Any, factory, ttl: int | None = None):
        hit = self._cache.get(key)
        if hit and time.time() - hit[0] < (ttl or self.cache_seconds):
            return hit[1]
        value = await factory()
        self._cache[key] = (time.time(), value)
        return value

    # ── данные ────────────────────────────────────────────────────────────

    async def gift_collections(self) -> dict[str, str]:
        """Название коллекции → адрес."""
        async def load():
            out: dict[str, str] = {}
            cursor = None
            for _ in range(20):
                res = await self._get("/v1/gifts/collections", limit=100, after=cursor) or {}
                for c in res.get("items") or []:
                    if c.get("name") and c.get("address"):
                        out[c["name"]] = c["address"]
                cursor = res.get("cursor")
                if not cursor:
                    break
            return out
        return await self._cached("collections", load, ttl=6 * 3600)

    async def attributes(self, address: str) -> dict[str, dict[str, Decimal | None]]:
        """traitType (lower) → {значение: минимальная цена в TON}."""
        async def load():
            res = await self._get(f"/v1/collection/attributes/{address}") or {}
            out: dict[str, dict[str, Decimal | None]] = {}
            for a in res.get("attributes") or []:
                values = {}
                for v in a.get("values") or []:
                    price = _nano_to_ton(v.get("minPriceNano"))
                    if price is None and v.get("minPrice") not in (None, ""):
                        try:
                            price = Decimal(str(v["minPrice"]))
                        except InvalidOperation:
                            price = None
                    values[v.get("value")] = price
                out[(a.get("traitType") or "").lower()] = values
            return out
        return await self._cached(("attrs", address), load)

    async def min_listing(self, address: str, model: str | None, backdrop: str) -> Decimal | None:
        """Самый дешёвый листинг (фиксированная цена в TON) с заданной моделью и фоном."""
        async def load():
            best: Decimal | None = None
            for path in (f"/v1/nfts/on-sale/{address}", f"/v1/nfts/offchain/on-sale/{address}"):
                cursor = None
                for _ in range(self.max_pages):
                    try:
                        res = await self._get(path, limit=100, after=cursor) or {}
                    except GetgemsError:
                        if path.startswith("/v1/nfts/offchain"):
                            break
                        raise
                    for item in res.get("items") or []:
                        if _norm(_attr(item, "backdrop")) != _norm(backdrop):
                            continue
                        if model and _norm(_attr(item, "model")) != _norm(model):
                            continue
                        price = _sale_price(item)
                        if price is not None and (best is None or price < best):
                            best = price
                    cursor = res.get("cursor")
                    if not cursor:
                        break
            return best
        return await self._cached(("listing", address, _norm(model), _norm(backdrop)), load)

    async def quote(self, collection: str, model: str | None = None, backdrop: str | None = None) -> GiftQuote:
        try:
            async with self._lock:  # не превышать лимит Getgems параллельными сканами
                return await self._quote(collection, model, backdrop)
        except GetgemsError as exc:
            return GiftQuote(collection, model, backdrop, error=str(exc))

    async def _quote(self, collection: str, model: str | None, backdrop: str | None) -> GiftQuote:
        collections = await self.gift_collections()
        name = _match(collection, list(collections))
        if name is None:
            return GiftQuote(collection, model, backdrop, error="коллекция не найдена на Getgems")
        address = collections[name]
        attrs = await self.attributes(address)
        models = attrs.get("model", {})
        backdrops = attrs.get("backdrop", {})
        model_name = _match(model, [m for m in models if m])
        backdrop_name = _match(backdrop, [b for b in backdrops if b])
        if model and model_name is None:
            return GiftQuote(name, model, backdrop, error=f"модель «{model}» не найдена в коллекции")
        premium = backdrop_name is not None and _norm(backdrop_name) in {_norm(b) for b in self.premium_backdrops}

        if premium:
            price = await self.min_listing(address, model_name, backdrop_name)
            basis = "модель + премиальный фон" if model_name else "премиальный фон"
            return GiftQuote(name, model_name, backdrop_name, price, basis=basis,
                             error=None if price is not None else "нет листингов с такой моделью и фоном")
        if model_name:
            price = models.get(model_name)
            return GiftQuote(name, model_name, backdrop_name, price, basis="floor модели, фон и символ не учитываются",
                             error=None if price is not None else "нет листингов этой модели")
        prices = [p for p in models.values() if p is not None]
        price = min(prices) if prices else None
        return GiftQuote(name, None, backdrop_name, price, basis="floor коллекции, модель не названа",
                         error=None if price is not None else "нет листингов")

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
