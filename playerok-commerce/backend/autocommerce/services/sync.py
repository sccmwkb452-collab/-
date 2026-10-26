"""Synchronisation runs: every data load records what was received, saved,
how many errors happened and where the data came from."""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.enums import SyncStatus
from ..database.models import SyncRun
from ..shared.masking import scrub_text
from ..shared.timeutil import utcnow


async def start(session: AsyncSession, source: str, kind: str) -> SyncRun:
    run = SyncRun(source=source, kind=kind, status=SyncStatus.RUNNING, started_at=utcnow())
    session.add(run)
    await session.flush()
    return run


def finish(
    run: SyncRun,
    status: SyncStatus,
    *,
    received: int = 0,
    saved: int = 0,
    errors: int = 0,
    message: str = "",
    details: dict[str, Any] | None = None,
) -> SyncRun:
    run.status = status
    run.records_received = received
    run.records_saved = saved
    run.errors_count = errors
    run.message = scrub_text(message)[:2000]
    run.details = details or {}
    run.finished_at = utcnow()
    return run


async def latest_by_source(session: AsyncSession) -> list[SyncRun]:
    sub = select(SyncRun.source, func.max(SyncRun.id).label("id")).group_by(SyncRun.source).subquery()
    rows = await session.execute(select(SyncRun).join(sub, SyncRun.id == sub.c.id).order_by(SyncRun.source))
    return list(rows.scalars())
