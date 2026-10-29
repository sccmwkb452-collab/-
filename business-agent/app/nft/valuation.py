"""Оценка NFT / Telegram-подарков только по реальным данным.

Источники: атрибуты и редкость — со страницы t.me/nft (или из сообщения Telegram);
цены — только из таблицы MarketPrice (ввод владельца, импорт, будущие провайдеры).
Нет данных → нет оценки. Устаревшие данные помечаются временем обновления.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.state import normalize_currency, to_decimal
from app.db.models import ExchangeRate, MarketPrice, utcnow
from app.nft.pages import GiftPage

MIN_COMPS_FOR_CONFIDENCE = 3


@dataclass
class PricePoint:
    price: Decimal
    currency: str
    kind: str
    source: str
    observed_at: datetime
    model: str | None = None
    backdrop: str | None = None
    symbol: str | None = None


@dataclass
class Valuation:
    collection: str
    attributes: dict[str, dict]
    currency: str
    floor: PricePoint | None = None
    comps: list[PricePoint] = field(default_factory=list)
    listings: list[PricePoint] = field(default_factory=list)
    estimate: Decimal | None = None
    method: str = "нет данных"
    confidence: str = "none"
    newest_data_at: datetime | None = None
    warnings: list[str] = field(default_factory=list)

    def render(self) -> str:
        lines = [f"Коллекция: {self.collection}"]
        for key, a in self.attributes.items():
            rarity = f" (редкость {a['rarity_percent']}%)" if a.get("rarity_percent") is not None else ""
            lines.append(f"{key}: {a.get('name')}{rarity}")
        if self.floor:
            lines.append(f"Floor: {self.floor.price} {self.floor.currency} ({self.floor.source}, {self.floor.observed_at:%Y-%m-%d %H:%M} UTC)")
        else:
            lines.append("Floor: нет данных")
        if self.comps:
            lines.append(f"Сопоставимые продажи: {len(self.comps)}, медиана "
                         f"{statistics.median([c.price for c in self.comps])} {self.currency}")
        if self.listings:
            lines.append(f"Текущие листинги (не продажи): {len(self.listings)}, мин. {min(p.price for p in self.listings)} {self.currency}")
        if self.estimate is not None:
            lines.append(f"Оценка: {self.estimate} {self.currency} — {self.method}, уверенность: {self.confidence}")
        else:
            lines.append("Оценка: недостаточно рыночных данных")
        if self.newest_data_at:
            lines.append(f"Данные обновлены: {self.newest_data_at:%Y-%m-%d %H:%M} UTC")
        lines.extend(f"⚠️ {w}" for w in self.warnings)
        return "\n".join(lines)


async def _rate(session: AsyncSession, src: str, dst: str) -> Decimal | None:
    if src == dst:
        return Decimal(1)
    direct = await session.scalar(
        select(ExchangeRate).where(ExchangeRate.source_currency == src, ExchangeRate.target_currency == dst)
        .order_by(ExchangeRate.fetched_at.desc())
    )
    if direct:
        return direct.rate
    inverse = await session.scalar(
        select(ExchangeRate).where(ExchangeRate.source_currency == dst, ExchangeRate.target_currency == src)
        .order_by(ExchangeRate.fetched_at.desc())
    )
    return (Decimal(1) / inverse.rate) if inverse and inverse.rate else None


async def valuate(
    session: AsyncSession,
    owner_id: int,
    collection: str,
    attributes: dict[str, dict],
    *,
    currency: str = "TON",
    stale_after_hours: int = 24,
    lookback_days: int = 30,
) -> Valuation:
    val = Valuation(collection=collection, attributes=attributes, currency=currency)
    since = utcnow() - timedelta(days=lookback_days)
    rows = (await session.scalars(
        select(MarketPrice).where(
            MarketPrice.owner_id == owner_id, MarketPrice.collection.ilike(collection), MarketPrice.observed_at >= since
        ).order_by(MarketPrice.observed_at.desc())
    )).all()

    points: list[PricePoint] = []
    skipped_currencies: set[str] = set()
    for r in rows:
        rate = await _rate(session, r.currency, currency)
        if rate is None:
            skipped_currencies.add(r.currency)
            continue
        points.append(PricePoint((r.price * rate).quantize(Decimal("0.0001")), currency, r.kind, r.source,
                                 r.observed_at, r.model, r.backdrop, r.symbol))
    if skipped_currencies:
        val.warnings.append("Нет курса для пересчёта: " + ", ".join(sorted(skipped_currencies)) + " — эти цены не учтены.")

    floors = [p for p in points if p.kind == "floor"]
    val.floor = floors[0] if floors else None
    model = (attributes.get("model") or {}).get("name")
    backdrop = (attributes.get("backdrop") or {}).get("name")
    sales = [p for p in points if p.kind == "sale"]
    same_model = [p for p in sales if model and p.model and p.model.lower() == model.lower()]
    exact = [p for p in same_model if backdrop and p.backdrop and p.backdrop.lower() == backdrop.lower()]
    val.comps = exact or same_model
    val.listings = [p for p in points if p.kind == "listing" and (not model or (p.model or "").lower() == model.lower())]

    if len(exact) >= MIN_COMPS_FOR_CONFIDENCE:
        val.estimate, val.method, val.confidence = _median(exact), "медиана продаж с той же моделью и фоном", "medium"
    elif len(same_model) >= MIN_COMPS_FOR_CONFIDENCE:
        val.estimate, val.method, val.confidence = _median(same_model), "медиана продаж с той же моделью", "medium"
    elif val.comps:
        val.estimate, val.method, val.confidence = _median(val.comps), f"по {len(val.comps)} продаж(ам) — мало данных", "low"
    elif val.floor:
        val.estimate, val.method, val.confidence = val.floor.price, "floor коллекции (нижняя граница, атрибуты не учтены)", "low"

    dated = [p.observed_at for p in points]
    if dated:
        newest = max(dated)
        val.newest_data_at = newest
        if utcnow() - newest > timedelta(hours=stale_after_hours):
            val.warnings.append(f"Рыночные данные старше {stale_after_hours} ч — обновите их.")
    else:
        val.warnings.append("Рыночных данных по коллекции нет — оценка невозможна.")
    val.warnings.append("Редкость оценивается только по данным Telegram, внешний вид не учитывается.")
    return val


def _median(points: list[PricePoint]) -> Decimal:
    return Decimal(statistics.median([p.price for p in points])).quantize(Decimal("0.0001"))


def attributes_from_page(page: GiftPage) -> dict[str, dict]:
    out = {}
    for key in ("model", "backdrop", "symbol"):
        attr = getattr(page, key)
        if attr:
            out[key] = {"name": attr.name, "rarity_percent": attr.rarity_percent}
    return out


def compare_offer(price: Decimal, val: Valuation) -> str:
    if val.estimate is None or val.estimate == 0:
        return "Сравнить не с чем: нет оценки."
    diff = (price - val.estimate) / val.estimate * 100
    word = "выше" if diff > 0 else "ниже"
    return f"Предложение {price} {val.currency} на {abs(diff):.1f}% {word} оценки {val.estimate} ({val.confidence})."


_PRICE_LINE = re.compile(
    r"^\s*(?P<collection>[A-Za-z0-9]+)\s+(?P<kind>floor|sale|listing|флор|продажа|листинг)\s+"
    r"(?P<price>\d+(?:[.,]\d+)?)\s*(?P<currency>\S+)(?P<rest>.*)$",
    re.I,
)
_KIND_RU = {"флор": "floor", "продажа": "sale", "листинг": "listing"}


def parse_price_line(line: str) -> dict | None:
    """«PlushPepe sale 15.5 TON model=Pumpkin backdrop=Black source=Fragment» → поля MarketPrice."""
    m = _PRICE_LINE.match(line)
    if not m:
        return None
    currency = normalize_currency(m.group("currency"))
    price = to_decimal(m.group("price"))
    if not currency or price is None:
        return None
    extra = dict(re.findall(r"(model|backdrop|symbol|source)=(\"[^\"]+\"|\S+)", m.group("rest")))
    kind = m.group("kind").lower()
    return {
        "collection": m.group("collection"),
        "kind": _KIND_RU.get(kind, kind),
        "price": price,
        "currency": currency,
        "model": extra.get("model", "").strip('"') or None,
        "backdrop": extra.get("backdrop", "").strip('"') or None,
        "symbol": extra.get("symbol", "").strip('"') or None,
        "source": extra.get("source", "").strip('"') or "ввод владельца",
    }
