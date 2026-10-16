from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from nft_gift_bot.database.base import Base, TimestampMixin


class PaymentStatus(StrEnum):
    PENDING = "pending"  # ожидает оплаты
    PAID = "paid"  # оплачено
    EXPIRED = "expired"  # истёк срок
    CANCELLED = "cancelled"  # отменено
    FAILED = "failed"  # ошибка


class PaymentKind(StrEnum):
    SUBSCRIPTION = "subscription"


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount_nano > 0", name="amount_positive"),
        Index("ix_payments_status_expires_at", "status", "expires_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(16), default=PaymentKind.SUBSCRIPTION)
    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.PENDING)
    amount_nano: Mapped[int] = mapped_column(BigInteger)
    # Days of subscription bought; snapshot so later price/term changes don't affect this invoice.
    subscription_days: Mapped[int]
    # Unique invoice identifier the payer puts into the TON transfer comment.
    memo: Mapped[str] = mapped_column(String(32), unique=True)
    # A blockchain transaction can confirm at most one invoice.
    ton_tx_hash: Mapped[str | None] = mapped_column(String(128), unique=True, default=None)
    ton_sender: Mapped[str | None] = mapped_column(String(128), default=None)
    expires_at: Mapped[datetime]
    paid_at: Mapped[datetime | None] = mapped_column(default=None)
    error_message: Mapped[str | None] = mapped_column(String(255), default=None)
