from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from ....database.models import AdminAuditLog, PaymentWebhookEvent
from ...deps import ManagerAdmin, SessionDep
from ...serializers import audit_admin

router = APIRouter()


@router.get("/audit")
async def audit_log(
    ctx: ManagerAdmin,
    session: SessionDep,
    entity_type: Annotated[str | None, Query(max_length=32)] = None,
    entity_id: Annotated[str | None, Query(max_length=64)] = None,
    admin_id: int | None = None,
    action: Annotated[str | None, Query(max_length=64)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(AdminAuditLog)
    if entity_type:
        stmt = stmt.where(AdminAuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AdminAuditLog.entity_id == entity_id)
    if admin_id:
        stmt = stmt.where(AdminAuditLog.admin_id == admin_id)
    if action:
        stmt = stmt.where(AdminAuditLog.action.startswith(action))
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await session.execute(stmt.order_by(AdminAuditLog.id.desc()).limit(limit).offset(offset))).scalars()
    return {"items": [audit_admin(r) for r in rows], "total": total or 0}


@router.get("/webhook-events")
async def webhook_events(
    ctx: ManagerAdmin,
    session: SessionDep,
    status: Annotated[str | None, Query(pattern="^(received|processed|ignored|rejected|failed)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict:
    stmt = select(PaymentWebhookEvent).order_by(PaymentWebhookEvent.id.desc()).limit(limit)
    if status:
        stmt = stmt.where(PaymentWebhookEvent.status == status)
    rows = (await session.execute(stmt)).scalars()
    return {
        "items": [
            {
                "id": e.id,
                "provider": e.provider,
                "event_id": e.event_id,
                "type": e.event_type,
                "signature_valid": e.signature_valid,
                "status": e.status,
                "payment_id": str(e.payment_id) if e.payment_id else None,
                "remote_ip": e.remote_ip,
                "error": e.error,
                "received_at": e.received_at.isoformat(),
                "processed_at": e.processed_at.isoformat() if e.processed_at else None,
            }
            for e in rows
        ]
    }
