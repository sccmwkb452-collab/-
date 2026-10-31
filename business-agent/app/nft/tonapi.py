"""Floor Telegram-подарков по ончейн-листингам через TonAPI (https://tonapi.io) — работает без ключа.

Подарки, выведенные в блокчейн TON, — это NFT; TonAPI отдаёт их атрибуты (Model / Backdrop / Symbol) и
текущую продажу (маркетплейс и цену). Floor = самый дешёвый листинг с нужными атрибутами по тем же
правилам, что и для Getgems (символ не учитывается, фон — только премиальный).

Ограничения (честно): видны только ончейн-листинги (Getgems и другие TON-маркетплейсы), не внутренний
маркет Telegram; без ключа — 100 NFT за запрос и ~1 запрос в секунду, поэтому большие коллекции
сканируются не целиком (лимит max_items) — тогда это указывается в ответе. С ключом TONAPI_KEY — быстрее.
"""
from __future__ import annotations

import asyncio
import logging
import os
import ssl
import time
from decimal import Decimal, InvalidOperation
from typing import Any

import aiohttp

from app.nft.getgems import GiftQuote, _match, _norm

logger = logging.getLogger(__name__)

BASE_URL = "https://tonapi.io"
TON_TOKENS = {"ton", "gram"}  # тикер нативной валюты в ответах TonAPI


class TonapiError(Exception):
    pass


class TonapiGiftSource:
    title = "TonAPI"

    def __init__(self, api_key: str = "", *, base_url: str = BASE_URL, premium_backdrops: list[str] | None = None,
                 cache_seconds: int = 900, max_items: int = 6000, timeout: float = 30,
                 min_interval: float | None = None) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.premium_backdrops = premium_backdrops if premium_backdrops is not None else ["Black", "Onyx Black"]
        self.cache_seconds = cache_seconds
        self.max_items = max_items
        self.min_interval = min_interval if min_interval is not None else (0.15 if api_key else 1.1)
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._session: aiohttp.ClientSession | None = None
        self._last_call = 0.0
        self._rate_lock = asyncio.Lock()
        self._scan_lock = asyncio.Lock()
        self._collections: dict[str, tuple[str, str]] = {}  # norm(запрос) → (название, адрес)
        self._scans: dict[str, tuple[float, list[dict[str, Any]], bool]] = {}

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
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        for attempt in range(3):
            async with self._rate_lock:  # лимит запросов TonAPI
                wait = self._last_call + self.min_interval - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                self._last_call = time.monotonic()
            try:
                async with self._get_session().get(f"{self.base_url}{path}", params=params, headers=headers) as resp:
                    if resp.status == 429:
                        await asyncio.sleep(2 * (attempt + 1))
                        continue
                    if resp.status == 404:
                        return None
                    payload = await resp.json(content_type=None)
                    if resp.status != 200:
                        raise TonapiError(f"TonAPI: HTTP {resp.status} {(payload or {}).get('error', '')}".strip())
                    return payload
            except (aiohttp.ClientError, TimeoutError, ValueError) as exc:
                if attempt == 2:
                    raise TonapiError(f"TonAPI недоступен: {exc or type(exc).__name__}") from exc
        raise TonapiError("TonAPI ограничил запросы, попробуйте позже")

    # ── данные ────────────────────────────────────────────────────────────

    async def gift_collections(self) -> list[str]:
        """Коллекции, которые уже находили (полного каталога у TonAPI нет — ищем по названию)."""
        return sorted({name for name, _ in self._collections.values()})

    async def resolve(self, collection: str) -> tuple[str, str] | None:
        key = _norm(collection)
        if key in self._collections:
            return self._collections[key]
        found: dict[str, str] = {}
        for query in dict.fromkeys([collection, collection.rstrip("s"), collection.rstrip("s") + "s"]):
            res = await self._get("/v2/accounts/search", name=query) or {}
            for acc in res.get("addresses") or []:
                if acc.get("trust") != "whitelist":
                    continue  # только проверенные TonAPI — поиск полон подделок
                info = await self._get(f"/v2/nfts/collections/{acc['address']}")
                name = ((info or {}).get("metadata") or {}).get("name")
                if name:
                    found[name] = acc["address"]
            if found:
                break
        name = _match(collection, list(found), cutoff=0.75)
        if name is None:
            return None
        self._collections[key] = (name, found[name])
        return self._collections[key]

    async def listings(self, address: str) -> tuple[list[dict[str, Any]], bool]:
        """Подарки коллекции на продаже за TON: [{model, backdrop, price}], и просканирована ли она целиком."""
        hit = self._scans.get(address)
        if hit and time.time() - hit[0] < self.cache_seconds:
            return hit[1], hit[2]
        async with self._scan_lock:
            hit = self._scans.get(address)
            if hit and time.time() - hit[0] < self.cache_seconds:
                return hit[1], hit[2]
            out: list[dict[str, Any]] = []
            complete = False
            offset = 0
            while offset < self.max_items:
                res = await self._get(f"/v2/nfts/collections/{address}/items", limit=100, offset=offset) or {}
                items = res.get("nft_items") or []
                for item in items:
                    price = _sale_price(item.get("sale"))
                    if price is None or price <= 0:  # аукционы и продажи без фиксированной цены
                        continue
                    attrs = {(a.get("trait_type") or "").lower(): a.get("value")
                             for a in ((item.get("metadata") or {}).get("attributes") or [])}
                    out.append({"model": attrs.get("model"), "backdrop": attrs.get("backdrop"), "price": price,
                                "market": ((item.get("sale") or {}).get("market") or {}).get("name")})
                if len(items) < 100:
                    complete = True
                    break
                offset += 100
            self._scans[address] = (time.time(), out, complete)
            return out, complete

    async def quote(self, collection: str, model: str | None = None, backdrop: str | None = None) -> GiftQuote:
        try:
            return await self._quote(collection, model, backdrop)
        except TonapiError as exc:
            return GiftQuote(collection, model, backdrop, error=str(exc), source=self.title)

    async def _quote(self, collection: str, model: str | None, backdrop: str | None) -> GiftQuote:
        resolved = await self.resolve(collection)
        if resolved is None:
            return GiftQuote(collection, model, backdrop, error="коллекция не найдена в TON", source=self.title)
        name, address = resolved
        listed, complete = await self.listings(address)
        partial = "" if complete else f", просмотрены первые {self.max_items} NFT коллекции"
        model_name = _match(model, sorted({x["model"] for x in listed if x["model"]}))
        backdrop_name = _match(backdrop, sorted({x["backdrop"] for x in listed if x["backdrop"]})) or backdrop
        premium = bool(backdrop) and _norm(backdrop_name) in {_norm(b) for b in self.premium_backdrops}
        if model and model_name is None:
            return GiftQuote(name, model, backdrop, error=f"нет листингов модели «{model}»{partial}", source=self.title)

        pool = listed
        if model_name:
            pool = [x for x in pool if _norm(x["model"]) == _norm(model_name)]
        if premium:
            pool = [x for x in pool if _norm(x["backdrop"]) == _norm(backdrop_name)]
            basis = "модель + премиальный фон" if model_name else "премиальный фон"
        elif model_name:
            basis = "floor модели, фон и символ не учитываются"
        else:
            basis = "floor коллекции, модель не названа"
        if not pool:
            return GiftQuote(name, model_name or model, backdrop_name, error=f"нет листингов{partial}", source=self.title)
        best = min(pool, key=lambda x: x["price"])
        return GiftQuote(name, model_name, backdrop_name if premium else backdrop, best["price"],
                         basis=f"{basis}, листинг {best['market'] or 'TON'}{partial}", source=self.title)

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None


def _sale_price(sale: dict[str, Any] | None) -> Decimal | None:
    price = (sale or {}).get("price") or {}
    if price.get("currency_type") != "native" and (price.get("token_name") or "").lower() not in TON_TOKENS:
        return None
    try:
        return Decimal(str(price["value"])) / (Decimal(10) ** int(price.get("decimals", 9)))
    except (KeyError, InvalidOperation, ValueError):
        return None
