"""System errors shown in the admin panel (Admin → Ошибки).

Recording is best effort: it uses its own transaction, never raises and
scrubs secrets (bot token, signatures, initData) from the message and details.
"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete, select

from ..database.models import ErrorEvent
from ..database.session import session_scope
from ..shared.masking import scrub
from ..shared.timeutil import utcnow

log = logging.getLogger(__name__)
KEEP = 2000  # newest events kept


async def record(
    source: str, message: str, *, path: str | None = None, details: dict[str, Any] | None = None, user_id: int | None = None
) -> None:
    try:
        async with session_scope() as session:
            session.add(
                ErrorEvent(
                    source=source[:16],
                    message=str(scrub(message or "error"))[:1000],
                    path=(path or None) and path[:256],
                    details=scrub(details) if details else None,
                    user_id=user_id,
                    created_at=utcnow(),
                )
            )
            await session.flush()
            # Bounded table: drop the oldest beyond KEEP.
            cutoff = await session.scalar(select(ErrorEvent.id).order_by(ErrorEvent.id.desc()).offset(KEEP).limit(1))
            if cutoff is not None:
                await session.execute(delete(ErrorEvent).where(ErrorEvent.id <= cutoff))
    except Exception:
        log.warning("could not record an error event", exc_info=True)
