import enum
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class SubscriptionPlan(str, enum.Enum):
    BASIC = "basic"
    PREMIUM = "premium"


class SubscriptionStatus(str, enum.Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    CANCELLED = "cancelled"
    PENDING = "pending"


class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    plan: Mapped[SubscriptionPlan] = mapped_column(
        Enum(SubscriptionPlan), nullable=False
    )
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.PENDING, nullable=False, index=True
    )

    price_paid: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="XTR", nullable=False)  # XTR = Telegram Stars

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="subscriptions")  # noqa: F821

    @property
    def is_active(self) -> bool:
        from datetime import timezone
        if self.status != SubscriptionStatus.ACTIVE:
            return False
        if self.expires_at is None:
            return True
        return datetime.now(tz=timezone.utc) < self.expires_at

    def __repr__(self) -> str:
        return (
            f"Subscription(id={self.id}, user_id={self.user_id}, "
            f"plan={self.plan.value}, status={self.status.value})"
        )
