"""Fragment (fragment.com): public price monitoring for Telegram Stars and Premium.

The pages ``/stars/buy`` and ``/premium/gift`` are public (no login) and list
packages with prices in USD and TON. They are read with a plain GET, no
cookies, at most once per ``FRAGMENT_MIN_INTERVAL_MINUTES``.

Purchasing on Fragment requires connecting a TON wallet (TON Connect) and a
Telegram account in a browser; there is no public purchasing API, so the
adapter never buys anything: orders get «Требуется ручная закупка».
"""

from __future__ import annotations

import html
import re
from decimal import Decimal, InvalidOperation

from ...config import get_settings
from ..http import IntegrationError, check_status, classify, client, with_retries
from .base import CatalogItem, ConnectionCheck, SupplierAdapter, SupplierCapabilities

_STARS_ITEM = re.compile(
    r'name="stars"\s+value="(?P<qty>\d+)".*?icon-usd">(?P<usd>[\d.,\s]+)</div>\s*'
    r'<div class="tm-radio-desc[^"]*icon-ton">(?P<ton>.*?)</div>',
    re.S,
)
_PREMIUM_ITEM = re.compile(
    r'name="months"\s+value="(?P<months>\d+)".*?icon-ton">(?P<ton>.*?)</div>\s*'
    r'<div class="tm-radio-desc">(?P<usd>.*?)</div>',
    re.S,
)


def _number(fragment_html: str) -> Decimal | None:
    text = html.unescape(re.sub(r"<[^>]+>", "", fragment_html))
    text = text.replace("$", "").replace(",", "").replace(" ", "").strip()
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_stars(page: str) -> list[CatalogItem]:
    items: list[CatalogItem] = []
    for m in _STARS_ITEM.finditer(page):
        qty = int(m.group("qty"))
        usd = _number(m.group("usd"))
        ton = _number(m.group("ton"))
        if usd is None:
            continue
        items.append(
            CatalogItem(
                external_id=f"stars:{qty}",
                name=f"Telegram Stars — {qty:,} ⭐".replace(",", " "),
                price=usd,
                currency="USD",
                category="Telegram Stars",
                raw={"quantity": qty, "price_ton": None if ton is None else str(ton), "page": "/stars/buy"},
            )
        )
    return items


def parse_premium(page: str) -> list[CatalogItem]:
    items: list[CatalogItem] = []
    for m in _PREMIUM_ITEM.finditer(page):
        months = int(m.group("months"))
        usd = _number(m.group("usd"))
        ton = _number(m.group("ton"))
        if usd is None:
            continue
        items.append(
            CatalogItem(
                external_id=f"premium:{months}",
                name=f"Telegram Premium — {months} мес. (подарок)",
                price=usd,
                currency="USD",
                category="Telegram Premium",
                raw={"months": months, "price_ton": None if ton is None else str(ton), "page": "/premium/gift"},
            )
        )
    return items


class FragmentAdapter(SupplierAdapter):
    code = "fragment"
    title = "Fragment (мониторинг цен)"
    capabilities = SupplierCapabilities(price_list=True)
    description = (
        "Цены пакетов Stars и Premium с публичных страниц fragment.com (USD и TON). "
        "Покупка — только вручную через TON Connect: публичного API покупки нет."
    )

    def configured(self) -> bool:
        return True  # public pages, no credentials

    async def _page(self, path: str) -> str:
        base = get_settings().fragment_base_url

        async def call() -> str:
            try:
                async with client(base) as c:
                    response = await c.get(path)
            except Exception as exc:  # noqa: BLE001
                raise classify(exc) from exc
            check_status(response)
            return response.text

        return await with_retries(call)

    async def check(self) -> ConnectionCheck:
        try:
            items = parse_stars(await self._page("/stars/buy"))
        except IntegrationError as exc:
            return ConnectionCheck(False, f"Страница Fragment недоступна: {exc}")
        if not items:
            return ConnectionCheck(False, "Страница Fragment открылась, но цены не распознаны — изменилась вёрстка")
        return ConnectionCheck(True, f"Цены читаются: {len(items)} пакетов Stars. Закупка — вручную")

    async def fetch_catalog(self) -> list[CatalogItem]:
        stars = parse_stars(await self._page("/stars/buy"))
        premium = parse_premium(await self._page("/premium/gift"))
        if not stars and not premium:
            raise IntegrationError("цены на страницах Fragment не распознаны — изменилась вёрстка")
        return stars + premium
