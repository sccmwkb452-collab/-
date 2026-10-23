from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select

from ...database.models import SupportTicket
from ...services import support
from ...shared.errors import Forbidden, ValidationFailed
from ..deps import RuntimeDep, SessionDep, UserDep, user_rate_limit
from ..schemas import MessageIn, TicketIn
from ..serializers import ticket as ticket_json

router = APIRouter(prefix="/support")


@router.get("/tickets")
async def list_tickets(user: UserDep, session: SessionDep) -> dict:
    rows = (
        await session.execute(
            select(SupportTicket).where(SupportTicket.user_id == user.id).order_by(SupportTicket.last_message_at.desc()).limit(30)
        )
    ).scalars()
    return {"items": [ticket_json(t) for t in rows]}


@router.post("/tickets", status_code=201, dependencies=[Depends(user_rate_limit("ticket_create", 5, 300))])
async def create_ticket(body: TicketIn, user: UserDep, session: SessionDep, runtime: RuntimeDep) -> dict:
    if user.is_blocked:
        raise Forbidden("Аккаунт ограничен", code="user_blocked")
    order_id = None
    if body.order_id:
        try:
            order_id = uuid.UUID(body.order_id)
        except ValueError as exc:
            raise ValidationFailed("Некорректный номер заказа", code="invalid_order_id") from exc
    t = await support.create_ticket(session, user, body.text, runtime, subject=body.subject, order_id=order_id)
    await session.commit()
    t = await support.get_user_ticket(session, user, t.id)
    return ticket_json(t, t.messages)


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: int, user: UserDep, session: SessionDep) -> dict:
    t = await support.get_user_ticket(session, user, ticket_id)
    return ticket_json(t, t.messages)


@router.post("/tickets/{ticket_id}/messages", dependencies=[Depends(user_rate_limit("ticket_message", 20, 300))])
async def add_message(ticket_id: int, body: MessageIn, user: UserDep, session: SessionDep) -> dict:
    t = await support.get_user_ticket(session, user, ticket_id)
    await support.add_user_message(session, t, body.text)
    await session.commit()
    session.expunge(t)
    t = await support.get_user_ticket(session, user, ticket_id)
    return ticket_json(t, t.messages)
