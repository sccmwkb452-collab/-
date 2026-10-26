"""Exchange rates (RUB per unit) from the Bank of Russia."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import SyncStatus
from ..database.models import FxRate, SyncRun
from ..integrations.fx import cbr
from ..integrations.http import IntegrationError
from . import sync

STALE_AFTER = timedelta(days=4)  # weekends and holidays: the CBR publishes no new rate


async def sync_cbr(session: AsyncSession) -> SyncRun:
    run = await sync.start(session, "fx:cbr", "rates")
    try:
        data = await cbr.fetch()
    except IntegrationError as exc:
        return sync.finish(run, SyncStatus.FAILED, errors=1, message=f"ЦБ РФ недоступен: {exc}")
    saved = 0
    for rate in data.rates.values():
        stmt = (
            insert(FxRate)
            .values(base=rate.code, quote="RUB", rate=rate.rate.quantize(Decimal("0.000001")), source="cbr", rate_date=data.date)
            .on_conflict_do_nothing(constraint="uq_fx_rates_point")
        )
        saved += (await session.execute(stmt)).rowcount or 0
    return sync.finish(
        run,
        SyncStatus.SUCCEEDED,
        received=len(data.rates),
        saved=saved,
        message=f"Курсы ЦБ РФ на {data.date:%d.%m.%Y}",
        details={"date": data.date.isoformat(), "usd": str(data.rates["USD"].rate) if "USD" in data.rates else None},
    )


async def latest_rate(session: AsyncSession, currency: str) -> tuple[Decimal, datetime | None] | None:
    currency = currency.upper()
    if currency == "RUB":
        return Decimal(1), None
    row = (
        await session.execute(
            select(FxRate)
            .where(FxRate.base == currency, FxRate.quote == "RUB")
            .order_by(FxRate.rate_date.desc(), FxRate.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return row.rate, row.rate_date


async def to_rub(session: AsyncSession, amount: Decimal, currency: str) -> Decimal | None:
    found = await latest_rate(session, currency)
    if found is None:
        return None
    return (amount * found[0]).quantize(Decimal("0.01"))


async def rates_overview(session: AsyncSession, codes: tuple[str, ...] = ("USD", "EUR", "CNY", "KZT", "TRY")) -> list[dict]:
    out = []
    for code in codes:
        found = await latest_rate(session, code)
        if found:
            out.append({"currency": code, "rate": str(found[0]), "date": found[1].isoformat() if found[1] else None})
    return out
