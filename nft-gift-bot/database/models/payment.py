"""TON blockchain payment record — one row per pending/confirmed payment attempt."""
import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class TonPaymentStatus(str, enum.Enum):
    PENDING = "pending"       # waiting for blockchain confirmation
    CONFIRMED = "confirmed"   # tx found and verified on-chain
    EXPIRED = "expired"       # payment window passed, tx not found
    FAILED = "failed"         # verification error (wrong amount / address)
    DUPLICATE = "duplicate"   # tx_hash already credited


class TonPayment(Base):
    __tablename__ = "ton_payments"

    __table_args__ = (
        UniqueConstraint("payment_comment", name="uq_ton_payments_comment"),
        UniqueConstraint("tx_hash", name="uq_ton_payments_tx_hash"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # "NFT" + 8 random digits, e.g. "NFT47291834"
    payment_comment: Mapped[str] = mapped_column(String(32), nullable=False)

    # Set once the tx is found on-chain
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_nanoton: Mapped[int | None] = mapped_column(Integer, nullable=True)

    status: Mapped[TonPaymentStatus] = mapped_column(
        Enum(TonPaymentStatus),
        default=TonPaymentStatus.PENDING,
        nullable=False,
        index=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    user: Mapped["User"] = relationship(foreign_keys=[user_id])  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"TonPayment(id={self.id}, user_id={self.user_id}, "
            f"comment={self.payment_comment!r}, status={self.status.value})"
        )
