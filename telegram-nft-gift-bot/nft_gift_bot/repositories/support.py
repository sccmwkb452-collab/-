from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import SupportTicket, TicketStatus


class SupportTicketRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get(self, ticket_id: int) -> SupportTicket | None:
        return await self.session.get(SupportTicket, ticket_id)

    async def create(self, user_id: int, message: str) -> SupportTicket:
        ticket = SupportTicket(user_id=user_id, message=message)
        self.session.add(ticket)
        await self.session.flush()
        return ticket

    async def list_open(self, limit: int = 20) -> list[SupportTicket]:
        result = await self.session.scalars(
            select(SupportTicket)
            .where(SupportTicket.status == TicketStatus.OPEN)
            .order_by(SupportTicket.id)
            .limit(limit)
        )
        return list(result)

    async def count_open_for_user(self, user_id: int) -> int:
        result = await self.session.scalars(
            select(SupportTicket.id).where(
                SupportTicket.user_id == user_id, SupportTicket.status == TicketStatus.OPEN
            )
        )
        return len(list(result))
