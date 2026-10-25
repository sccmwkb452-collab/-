from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog


async def log_action(session: AsyncSession, admin_id: int, action: str, target: str = "", details: str = "") -> None:
    session.add(AuditLog(admin_id=admin_id, action=action, target=target, details=details[:2000]))
