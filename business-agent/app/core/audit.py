"""Журнал действий. Никогда не пишет секреты: все детали проходят через redact()."""
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.redaction import redact, redact_text
from app.db.models import AuditLog

logger = logging.getLogger("audit")


async def audit(
    session: AsyncSession,
    action: str,
    result: str = "ok",
    *,
    owner_id: int | None = None,
    actor: str = "agent",
    conversation_id: int | None = None,
    parser: str | None = None,
    trade_bot: str | None = None,
    error: str | None = None,
    **details: Any,
) -> AuditLog:
    entry = AuditLog(
        owner_id=owner_id,
        actor=actor,
        action=action,
        result=result,
        conversation_id=conversation_id,
        parser=parser,
        trade_bot=trade_bot,
        error=redact_text(error[:2000]) if error else None,
        details=redact(details),
    )
    session.add(entry)
    await session.flush()
    log = logger.warning if result in ("error", "blocked", "unknown") else logger.info
    log("%s %s owner=%s conv=%s %s", action, result, owner_id, conversation_id, error or "")
    return entry
