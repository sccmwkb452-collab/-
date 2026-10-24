"""Admin → Ошибки: errors of the API, the bot and the Mini App, and orders that need attention."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import delete, func, select

from ....database.enums import DeliveryStatus, NotificationStatus, OrderStatus
from ....database.models import DeliveryTask, ErrorEvent, Notification, Order
from ....services import audit
from ...deps import ManagerAdmin, OwnerAdmin, SessionDep

router = APIRouter(prefix="/errors")


@router.get("")
async def list_errors(
    ctx: ManagerAdmin,
    session: SessionDep,
    source: Annotated[str | None, Query(max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(ErrorEvent)
    count = select(func.count()).select_from(ErrorEvent)
    if source:
        stmt = stmt.where(ErrorEvent.source == source)
        count = count.where(ErrorEvent.source == source)
    rows = (await session.execute(stmt.order_by(ErrorEvent.id.desc()).limit(limit).offset(offset))).scalars()
    problems = {
        "failed_orders": await session.scalar(select(func.count()).select_from(Order).where(Order.status == OrderStatus.failed)) or 0,
        "deliveries_need_attention": await session.scalar(
            select(func.count()).select_from(DeliveryTask).where(DeliveryTask.status == DeliveryStatus.needs_attention)
        )
        or 0,
        "failed_notifications": await session.scalar(
            select(func.count()).select_from(Notification).where(Notification.status == NotificationStatus.failed)
        )
        or 0,
    }
    return {
        "items": [
            {
                "id": e.id,
                "source": e.source,
                "message": e.message,
                "path": e.path,
                "details": e.details,
                "user_id": e.user_id,
                "created_at": e.created_at.isoformat(),
            }
            for e in rows
        ],
        "total": await session.scalar(count) or 0,
        "problems": problems,
    }


@router.delete("")
async def clear_errors(ctx: OwnerAdmin, session: SessionDep) -> dict:
    removed = (await session.execute(delete(ErrorEvent))).rowcount
    await audit.record(session, ctx.admin, "errors.clear", entity_type="error_events", summary=f"Удалено записей: {removed}", meta=ctx.meta)
    await session.commit()
    return {"ok": True, "removed": removed}
