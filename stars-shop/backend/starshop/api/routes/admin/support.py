from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ....database.enums import TicketStatus
from ....database.models import SupportTicket, User
from ....services import audit, support
from ....shared.errors import NotFound
from ...deps import SessionDep, SupportAdmin
from ...schemas import ReplyIn
from ...serializers import ticket as ticket_json
from ...serializers import user_admin

router = APIRouter(prefix="/tickets")


@router.get("")
async def list_tickets(
    ctx: SupportAdmin,
    session: SessionDep,
    status: Annotated[str | None, Query(pattern="^(open|answered|closed)$")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> dict:
    stmt = select(SupportTicket, User).join(User, User.id == SupportTicket.user_id)
    if status:
        stmt = stmt.where(SupportTicket.status == status)
    total = await session.scalar(select(func.count()).select_from(stmt.subquery()))
    rows = (await session.execute(stmt.order_by(SupportTicket.last_message_at.desc()).limit(limit).offset(offset))).all()
    return {
        "items": [
            {
                **ticket_json(t, admin=True),
                "user": {"id": u.id, "telegram_id": u.telegram_id, "username": u.username, "display_name": u.display_name},
            }
            for t, u in rows
        ],
        "total": total or 0,
    }


async def _ticket(session, ticket_id: int) -> SupportTicket:
    t = (
        await session.execute(select(SupportTicket).where(SupportTicket.id == ticket_id).options(selectinload(SupportTicket.messages)))
    ).scalar_one_or_none()
    if t is None:
        raise NotFound("Обращение не найдено", code="ticket_not_found")
    return t


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: int, ctx: SupportAdmin, session: SessionDep) -> dict:
    t = await _ticket(session, ticket_id)
    user = await session.get(User, t.user_id)
    return {**ticket_json(t, t.messages, admin=True), "user": user_admin(user) if user else None}


@router.post("/{ticket_id}/reply")
async def reply(ticket_id: int, body: ReplyIn, ctx: SupportAdmin, session: SessionDep) -> dict:
    t = await _ticket(session, ticket_id)
    await support.admin_reply(session, t, ctx.admin, body.text)
    await audit.record(session, ctx.admin, "ticket.reply", entity_type="ticket", entity_id=t.id, meta=ctx.meta)
    await session.commit()
    session.expunge(t)
    return await get_ticket(ticket_id, ctx, session)


@router.post("/{ticket_id}/close")
async def close(ticket_id: int, ctx: SupportAdmin, session: SessionDep) -> dict:
    t = await _ticket(session, ticket_id)
    t.status = TicketStatus.closed
    await audit.record(session, ctx.admin, "ticket.close", entity_type="ticket", entity_id=t.id, meta=ctx.meta)
    await session.commit()
    session.expunge(t)
    return await get_ticket(ticket_id, ctx, session)
