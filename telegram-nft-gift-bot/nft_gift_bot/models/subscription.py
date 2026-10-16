from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from nft_gift_bot.database.base import Base, TimestampMixin


class SubscriptionStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Subscription(Base, TimestampMixin):
    """One row per user; renewals extend ``expires_at``. History lives in payments."""

    __tablename__ = "subscriptions"
    __table_args__ = (Index("ix_subscriptions_status_expires_at", "status", "expires_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    status: Mapped[str] = mapped_column(String(16), default=SubscriptionStatus.ACTIVE)
    starts_at: Mapped[datetime]
    expires_at: Mapped[datetime]
    expiry_notified_at: Mapped[datetime | None] = mapped_column(default=None)
