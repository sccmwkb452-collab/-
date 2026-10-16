"""Repository for AuditLog — admin action trail."""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models.audit_log import AuditLog


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def log(
        self,
        admin_tg_id: int,
        action: str,
        details: str,
        target_id: int | None = None,
    ) -> AuditLog:
        entry = AuditLog(
            admin_telegram_id=admin_tg_id,
            action=action,
            details=details,
            target_id=target_id,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def get_recent(self, limit: int = 20) -> list[AuditLog]:
        result = await self._session.execute(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
