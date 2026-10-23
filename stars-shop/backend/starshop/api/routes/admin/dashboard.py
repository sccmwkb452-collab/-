from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Query

from ....config import get_settings
from ....payments.registry import KNOWN_PROVIDERS, get_payment_provider
from ....services import stats
from ...deps import ManagerAdmin, SessionDep

router = APIRouter(prefix="/dashboard")


@router.get("")
async def dashboard(
    ctx: ManagerAdmin,
    session: SessionDep,
    period: Annotated[str, Query(pattern="^(day|week|month|quarter)$")] = "week",
    include_demo: bool = False,
) -> dict:
    data = await stats.dashboard(session, period, include_demo)
    data["cash"] = await _balances()
    return data


@router.get("/series")
async def series(
    ctx: ManagerAdmin,
    session: SessionDep,
    granularity: Annotated[str, Query(pattern="^(day|week|month)$")] = "day",
    points: Annotated[int, Query(ge=2, le=90)] = 30,
    include_demo: bool = False,
) -> dict:
    return {"granularity": granularity, "items": await stats.sales_series(session, granularity, points, include_demo)}


async def _balances() -> list[dict]:
    """Cash balance as reported by providers (not computed from orders)."""
    result = []
    for name in get_settings().payment_providers:
        if name not in KNOWN_PROVIDERS:
            continue
        provider = get_payment_provider(name)
        if provider.is_demo or not provider.is_configured():
            continue
        try:
            balances = await asyncio.wait_for(provider.balances(), timeout=5)
        except Exception:
            result.append({"provider": name, "title": provider.title, "error": "Не удалось получить баланс"})
            continue
        if balances is not None:
            result.append({"provider": name, "title": provider.title, "balances": balances})
    return result
