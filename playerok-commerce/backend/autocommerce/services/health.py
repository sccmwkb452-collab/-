"""Health of the services: database, worker and bot heartbeats, queue."""

from __future__ import annotations

import os
import socket
from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import Heartbeat
from ..database.session import check_database, session_scope
from ..shared.timeutil import utcnow
from . import app_settings, jobs

STALE_AFTER = timedelta(minutes=3)
INSTANCE = f"{socket.gethostname()}:{os.getpid()}"


async def beat(service: str, details: dict[str, Any] | None = None, *, started_at=None) -> None:
    async with session_scope() as session:
        now = utcnow()
        stmt = insert(Heartbeat).values(
            service=service, instance=INSTANCE, started_at=started_at or now, last_seen_at=now, details=details or {}
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Heartbeat.service],
            set_={"instance": INSTANCE, "last_seen_at": now, "details": details or {}, "started_at": stmt.excluded.started_at},
        )
        await session.execute(stmt)


async def status(session: AsyncSession) -> dict[str, Any]:
    db_ok, db_msg = await check_database()
    out: dict[str, Any] = {"database": {"ok": db_ok, "message": db_msg}}
    if not db_ok:
        out["ok"] = False
        return out
    beats = {h.service: h for h in (await session.execute(select(Heartbeat))).scalars()}
    now = utcnow()
    for service in ("worker", "bot"):
        h = beats.get(service)
        out[service] = {
            "ok": bool(h and now - h.last_seen_at < STALE_AFTER),
            "last_seen_at": h.last_seen_at.isoformat() if h else None,
            "instance": h.instance if h else None,
            "details": h.details if h else {},
        }
    out["queue"] = await jobs.queue_stats(session)
    out["kill_switch"] = await app_settings.kill_switch(session)
    out["mode"] = "live" if await app_settings.is_live(session) else "test"
    out["ok"] = db_ok
    return out
