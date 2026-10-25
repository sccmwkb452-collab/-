"""Database schema. All money amounts are stored as integer kopecks."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

NAMING = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    pass


Base.metadata.naming_convention = NAMING


def _now() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("balance >= 0", name="balance_non_negative"),
        CheckConstraint("referrer_id IS NULL OR referrer_id <> id", name="no_self_referral"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    username: Mapped[str | None] = mapped_column(String(64))
    full_name: Mapped[str] = mapped_column(String(256), default="", server_default="")
    balance: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    ref_code: Mapped[str] = mapped_column(String(16), unique=True)
    referrer_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    ban_reason: Mapped[str | None] = mapped_column(String(256))
    bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = _now()
    last_seen_at: Mapped[datetime] = _now()


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(64))
    emoji: Mapped[str] = mapped_column(String(16), default="📦", server_default="📦")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    sort_order: Mapped[int] = mapped_column(Integer, default=100, server_default="100")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = _now()


class Product(Base):
    __tablename__ = "products"
    __table_args__ = (CheckConstraint("price > 0", name="price_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_id: Mapped[int] = mapped_column(
        ForeignKey("categories.id", ondelete="RESTRICT"), index=True
    )
    title: Mapped[str] = mapped_column(String(128))
    short_description: Mapped[str] = mapped_column(String(256), default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    region: Mapped[str | None] = mapped_column(String(64))
    # One characteristic per line, "Name: value"
    specs: Mapped[str] = mapped_column(Text, default="", server_default="")
    price: Mapped[int] = mapped_column(BigInteger)
    photo_file_id: Mapped[str | None] = mapped_column(String(256))
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = _now()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    category: Mapped[Category] = relationship(lazy="joined")


class ItemStatus:
    AVAILABLE = "available"
    SOLD = "sold"
    REVOKED = "revoked"  # sold, then refunded: never goes back on sale
    WITHDRAWN = "withdrawn"  # removed from sale by an admin


class ProductItem(Base):
    """One deliverable unit of a product (a key, credentials of a transferable account, ...)."""

    __tablename__ = "product_items"
    __table_args__ = (Index("ix_product_items_product_status", "product_id", "status"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=ItemStatus.AVAILABLE, server_default="available")
    created_at: Mapped[datetime] = _now()
    sold_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # never expose content in logs / tracebacks
        return f"<ProductItem id={self.id} product={self.product_id} status={self.status}>"


class OrderStatus:
    COMPLETED = "completed"
    REFUNDED = "refunded"


class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (CheckConstraint("price > 0", name="price_positive"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    item_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("product_items.id"), unique=True)
    product_title: Mapped[str] = mapped_column(String(128))
    price: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=OrderStatus.COMPLETED)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True)
    created_at: Mapped[datetime] = _now()
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_reason: Mapped[str | None] = mapped_column(String(256))
    refunded_by: Mapped[int | None] = mapped_column(BigInteger)

    item: Mapped[ProductItem] = relationship(lazy="joined")

    @property
    def number(self) -> str:
        return format_order_number(self.id)


def format_order_number(order_id: int) -> str:
    return f"AM-{order_id:06d}"


class TxKind:
    TOPUP = "topup"
    PURCHASE = "purchase"
    REFUND = "refund"
    REFERRAL = "referral"
    ADMIN = "admin_adjust"
    TOPUP_REFUND = "topup_refund"


class Transaction(Base):
    """Balance ledger. Partial unique indexes make every credit/debit happen at most once."""

    __tablename__ = "transactions"
    __table_args__ = (
        Index("uq_tx_topup_payment", "payment_id", unique=True, postgresql_where=text("kind = 'topup'")),
        Index(
            "uq_tx_topup_refund_payment",
            "payment_id",
            unique=True,
            postgresql_where=text("kind = 'topup_refund'"),
        ),
        Index("uq_tx_purchase_order", "order_id", unique=True, postgresql_where=text("kind = 'purchase'")),
        Index("uq_tx_refund_order", "order_id", unique=True, postgresql_where=text("kind = 'refund'")),
        Index("uq_tx_referral_order", "order_id", unique=True, postgresql_where=text("kind = 'referral'")),
        Index("ix_transactions_user_created", "user_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"))
    amount: Mapped[int] = mapped_column(BigInteger)
    balance_after: Mapped[int] = mapped_column(BigInteger)
    kind: Mapped[str] = mapped_column(String(24))
    order_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("orders.id"))
    payment_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("payments.id"))
    admin_id: Mapped[int | None] = mapped_column(BigInteger)
    comment: Mapped[str | None] = mapped_column(String(256))
    created_at: Mapped[datetime] = _now()


class PaymentStatus:
    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    FAILED = "failed"
    REFUNDED = "refunded"


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("provider", "external_id", name="uq_payments_provider_external"),
        CheckConstraint("amount > 0", name="amount_positive"),
        Index("ix_payments_status_created", "status", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    uid: Mapped[str] = mapped_column(String(32), unique=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), index=True)
    provider: Mapped[str] = mapped_column(String(16))
    amount: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=PaymentStatus.PENDING)
    external_id: Mapped[str | None] = mapped_column(String(128))
    pay_url: Mapped[str | None] = mapped_column(Text)
    last_error: Mapped[str | None] = mapped_column(String(512))
    created_at: Mapped[datetime] = _now()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refunded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger, index=True)
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(64), default="")
    details: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = _now()


class BroadcastStatus:
    RUNNING = "running"
    DONE = "done"
    CANCELLED = "cancelled"


class Broadcast(Base):
    __tablename__ = "broadcasts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    source_chat_id: Mapped[int] = mapped_column(BigInteger)
    source_message_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16), default=BroadcastStatus.RUNNING)
    total: Mapped[int] = mapped_column(Integer, default=0)
    sent: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    blocked: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = _now()
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
