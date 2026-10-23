from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..database.enums import ActorType, TicketStatus
from ..database.models import AdminUser, Order, SupportMessage, SupportTicket, User
from ..notifications import service as notify
from ..notifications import templates
from ..shared.errors import Conflict, NotFound, ValidationFailed
from ..shared.timeutil import utcnow
from .app_settings import RuntimeSettings

MAX_OPEN_TICKETS = 3
MAX_TEXT = 4000


def _clean(text: str) -> str:
    text = (text or "").strip()
    if not text:
        raise ValidationFailed("Сообщение не может быть пустым", code="empty_message")
    if len(text) > MAX_TEXT:
        raise ValidationFailed(f"Сообщение длиннее {MAX_TEXT} символов", code="message_too_long")
    return text


async def create_ticket(
    session: AsyncSession, user: User, text: str, runtime: RuntimeSettings, *, subject: str | None = None, order_id: uuid.UUID | None = None
) -> SupportTicket:
    text = _clean(text)
    if order_id is not None:
        owned = await session.scalar(select(Order.id).where(Order.id == order_id, Order.user_id == user.id))
        if owned is None:
            raise NotFound("Заказ не найден", code="order_not_found")
    open_count = await session.scalar(
        select(func.count()).select_from(SupportTicket).where(SupportTicket.user_id == user.id, SupportTicket.status != TicketStatus.closed)
    )
    if (open_count or 0) >= MAX_OPEN_TICKETS:
        raise Conflict("У вас уже есть открытые обращения — продолжите переписку в них", code="too_many_tickets")
    ticket = SupportTicket(user_id=user.id, order_id=order_id, subject=(subject or text.splitlines()[0])[:160], status=TicketStatus.open)
    session.add(ticket)
    await session.flush()
    session.add(SupportMessage(ticket_id=ticket.id, author_type=ActorType.user, text=text))
    if runtime.notifications.admin_new_ticket:
        await notify.notify_admins(
            session, "admin_new_ticket", templates.admin_new_ticket(ticket.id, ticket.subject, user.username), f"ticket:{ticket.id}"
        )
    return ticket


async def latest_open_ticket(session: AsyncSession, user: User) -> SupportTicket | None:
    return (
        await session.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == user.id, SupportTicket.status != TicketStatus.closed)
            .order_by(SupportTicket.last_message_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def get_user_ticket(session: AsyncSession, user: User, ticket_id: int) -> SupportTicket:
    ticket = (
        await session.execute(
            select(SupportTicket)
            .where(SupportTicket.id == ticket_id, SupportTicket.user_id == user.id)
            .options(selectinload(SupportTicket.messages))
        )
    ).scalar_one_or_none()
    if ticket is None:
        raise NotFound("Обращение не найдено", code="ticket_not_found")
    return ticket


async def add_user_message(session: AsyncSession, ticket: SupportTicket, text: str) -> SupportMessage:
    if ticket.status == TicketStatus.closed:
        raise Conflict("Обращение закрыто. Создайте новое", code="ticket_closed")
    message = SupportMessage(ticket_id=ticket.id, author_type=ActorType.user, text=_clean(text))
    session.add(message)
    ticket.status = TicketStatus.open
    ticket.last_message_at = utcnow()
    return message


async def admin_reply(session: AsyncSession, ticket: SupportTicket, admin: AdminUser, text: str) -> SupportMessage:
    text = _clean(text)
    message = SupportMessage(ticket_id=ticket.id, author_type=ActorType.admin, admin_id=admin.id, text=text)
    session.add(message)
    await session.flush()
    ticket.status = TicketStatus.answered
    ticket.last_message_at = utcnow()
    user = await session.get(User, ticket.user_id)
    if user is not None:
        await notify.enqueue(
            session,
            chat_id=user.telegram_id,
            kind="support_reply",
            message=templates.support_reply(ticket.id, text),
            dedup_key=f"support_reply:{message.id}",
            user_id=user.id,
        )
    return message
