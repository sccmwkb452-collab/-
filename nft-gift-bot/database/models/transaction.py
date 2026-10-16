import enum

from sqlalchemy import Enum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class TransactionType(str, enum.Enum):
    SUBSCRIPTION_PURCHASE = "subscription_purchase"
    SUBSCRIPTION_RENEWAL = "subscription_renewal"
    GIFT_PURCHASE = "gift_purchase"
    GIFT_TRANSFER = "gift_transfer"
    REFUND = "refund"


class TransactionStatus(str, enum.Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentProvider(str, enum.Enum):
    TELEGRAM_STARS = "telegram_stars"
    CRYPTO_BOT = "crypto_bot"
    INTERNAL = "internal"


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    type: Mapped[TransactionType] = mapped_column(Enum(TransactionType), nullable=False)
    status: Mapped[TransactionStatus] = mapped_column(
        Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False, index=True
    )
    provider: Mapped[PaymentProvider] = mapped_column(
        Enum(PaymentProvider), nullable=False
    )

    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False)

    # Внешние идентификаторы провайдера платежей
    provider_payment_id: Mapped[str | None] = mapped_column(String(256), unique=True, index=True)
    provider_charge_id: Mapped[str | None] = mapped_column(String(256))

    description: Mapped[str | None] = mapped_column(Text)

    # Ссылки на связанные сущности
    subscription_id: Mapped[int | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="SET NULL")
    )
    gift_id: Mapped[int | None] = mapped_column(
        ForeignKey("gifts.id", ondelete="SET NULL")
    )

    # Relationships
    user: Mapped["User | None"] = relationship(back_populates="transactions")  # noqa: F821

    def __repr__(self) -> str:
        return (
            f"Transaction(id={self.id}, type={self.type.value}, "
            f"status={self.status.value}, amount={self.amount} {self.currency})"
        )
