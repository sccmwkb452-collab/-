from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from nft_gift_bot.models import SupportTicket
from nft_gift_bot.repositories import SupportTicketRepository

MAX_MESSAGE_LENGTH = 2000
MAX_OPEN_TICKETS = 3


class SupportError(ValueError):
    pass


class SupportService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = SupportTicketRepository(session)

    async def create_ticket(self, user_id: int, message: str) -> SupportTicket:
        text = message.strip()
        if not text:
            raise SupportError("empty")
        if len(text) > MAX_MESSAGE_LENGTH:
            raise SupportError("too_long")
        if await self._repo.count_open_for_user(user_id) >= MAX_OPEN_TICKETS:
            raise SupportError("too_many_open")
        return await self._repo.create(user_id, text)
