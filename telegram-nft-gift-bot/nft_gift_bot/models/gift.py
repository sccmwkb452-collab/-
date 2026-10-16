from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from nft_gift_bot.database.base import Base, TimestampMixin


class Gift(Base, TimestampMixin):
    """Cached snapshot of a gift owned by a connected account (refreshed from the API)."""

    __tablename__ = "gifts"
    __table_args__ = (UniqueConstraint("connected_account_id", "owned_gift_id", name="account_owned_gift"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    connected_account_id: Mapped[int] = mapped_column(
        ForeignKey("connected_accounts.id", ondelete="CASCADE"), index=True
    )
    owned_gift_id: Mapped[str] = mapped_column(String(255))
    title: Mapped[str] = mapped_column(String(255))
    is_unique: Mapped[bool] = mapped_column(default=False)
    can_be_transferred: Mapped[bool] = mapped_column(default=False)
    transfer_star_count: Mapped[int | None] = mapped_column(default=None)
    next_transfer_date: Mapped[datetime | None] = mapped_column(default=None)
    sticker_file_id: Mapped[str | None] = mapped_column(String(255), default=None)
    last_seen_at: Mapped[datetime]


class TransferStatus(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    PROCESSING = "processing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class GiftTransfer(Base, TimestampMixin):
    __tablename__ = "gift_transfers"
    __table_args__ = (Index("ix_gift_transfers_user_id_created_at", "user_id", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    connected_account_id: Mapped[int] = mapped_column(ForeignKey("connected_accounts.id", ondelete="CASCADE"))
    owned_gift_id: Mapped[str] = mapped_column(String(255))
    gift_title: Mapped[str] = mapped_column(String(255))
    recipient_chat_id: Mapped[int] = mapped_column(BigInteger)
    recipient_label: Mapped[str] = mapped_column(String(64))
    star_count: Mapped[int | None] = mapped_column(default=None)
    status: Mapped[str] = mapped_column(String(24), default=TransferStatus.PENDING_CONFIRMATION, index=True)
    confirm_expires_at: Mapped[datetime]
    executed_at: Mapped[datetime | None] = mapped_column(default=None)
    error_code: Mapped[str | None] = mapped_column(String(64), default=None)
    error_message: Mapped[str | None] = mapped_column(String(255), default=None)
