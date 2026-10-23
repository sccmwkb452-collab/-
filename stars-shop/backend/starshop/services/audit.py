from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ..database.models import AdminAuditLog, AdminUser
from ..shared.masking import scrub


@dataclass(slots=True)
class RequestMeta:
    ip: str | None = None
    user_agent: str | None = None


async def record(
    session: AsyncSession,
    admin: AdminUser | None,
    action: str,
    *,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    summary: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    meta: RequestMeta | None = None,
) -> AdminAuditLog:
    log = AdminAuditLog(
        admin_id=admin.id if admin else None,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        summary=summary,
        before=scrub(before) if before else None,
        after=scrub(after) if after else None,
        ip=meta.ip if meta else None,
        user_agent=(meta.user_agent or "")[:255] if meta else None,
    )
    session.add(log)
    return log
