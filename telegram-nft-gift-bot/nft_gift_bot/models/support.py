from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from nft_gift_bot.database.base import Base, TimestampMixin


class TicketStatus(StrEnum):
    OPEN = "open"
    ANSWERED = "answered"
    CLOSED = "closed"


class SupportTicket(Base, TimestampMixin):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(16), default=TicketStatus.OPEN, index=True)
    message: Mapped[str] = mapped_column(Text)
    admin_reply: Mapped[str | None] = mapped_column(Text, default=None)
    answered_by: Mapped[int | None] = mapped_column(BigInteger, default=None)
    answered_at: Mapped[datetime | None] = mapped_column(default=None)
