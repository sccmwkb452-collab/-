"""Database schema.

Conventions:
* money is ``NUMERIC(14,2)`` (``MONEY``), per-star rates ``NUMERIC(14,4)``;
* all timestamps are ``timestamptz`` and written in UTC;
* enums are VARCHAR + CHECK (see ``str_enum``);
* relationships are ``lazy="raise"`` — anything needed must be loaded
  explicitly, which keeps async code free of hidden queries.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..shared.timeutil import utcnow
from .base import MONEY, RATE, Base, TimestampMixin, str_enum
from .enums import (
    ActorType,
    AdminRole,
    BotButtonAction,
    ButtonStyle,
    DeliveryStatus,
    NotificationStatus,
    OrderKind,
    OrderStatus,
    PaymentStatus,
    ProductKind,
    PromoKind,
    PromoUsageStatus,
    RecipientType,
    ReferralStatus,
    ShopMode,
    TicketStatus,
    WebhookStatus,
)

# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger, unique=True, nullable=False)
    username: Mapped[str | None] = mapped_column(sa.String(64))
    first_name: Mapped[str] = mapped_column(sa.String(128), default="", server_default="")
    last_name: Mapped[str | None] = mapped_column(sa.String(128))
    language_code: Mapped[str | None] = mapped_column(sa.String(16))
    photo_url: Mapped[str | None] = mapped_column(sa.Text)
    is_premium: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    bot_started: Mapped[bool] = mapped_column(default=False, server_default=sa.false())

    is_blocked: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    blocked_reason: Mapped[str | None] = mapped_column(sa.Text)
    blocked_at: Mapped[datetime | None]

    referral_code: Mapped[str] = mapped_column(sa.String(16), unique=True, nullable=False)
    referred_by_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    bonus_balance: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")

    first_seen_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    __table_args__ = (
        sa.CheckConstraint("bonus_balance >= 0", name="bonus_non_negative"),
        sa.CheckConstraint("referred_by_id IS NULL OR referred_by_id <> id", name="no_self_referral"),
        sa.Index("ix_users_username_lower", sa.text("lower(username)")),
        sa.Index("ix_users_created_at", "created_at"),
    )

    @property
    def display_name(self) -> str:
        full = " ".join(p for p in (self.first_name, self.last_name) if p)
        return full or (f"@{self.username}" if self.username else f"id{self.telegram_id}")


class UserActivityDay(Base):
    """One row per user per day the Mini App was opened. Used for the
    visitor -> buyer conversion on the dashboard."""

    __tablename__ = "user_activity_days"

    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    day: Mapped[date] = mapped_column(sa.Date, primary_key=True)

    __table_args__ = (sa.Index("ix_user_activity_days_day", "day"),)


class UserNote(Base):
    __tablename__ = "user_notes"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admin_users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(sa.Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())


# ---------------------------------------------------------------------------
# Catalog
# ---------------------------------------------------------------------------


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)
    kind: Mapped[ProductKind] = mapped_column(str_enum(ProductKind, "product_kind"), default=ProductKind.package)
    title: Mapped[str | None] = mapped_column(sa.String(64))
    badge: Mapped[str | None] = mapped_column(sa.String(32))
    # package
    stars_amount: Mapped[int | None] = mapped_column(sa.Integer)
    price: Mapped[Decimal | None] = mapped_column(MONEY)
    # custom amount
    price_per_star: Mapped[Decimal | None] = mapped_column(RATE)
    min_stars: Mapped[int | None] = mapped_column(sa.Integer)
    max_stars: Mapped[int | None] = mapped_column(sa.Integer)
    # economics (never exposed publicly)
    cost_per_star: Mapped[Decimal | None] = mapped_column(RATE)
    cost_source: Mapped[str | None] = mapped_column(sa.String(255))
    cost_updated_at: Mapped[datetime | None]

    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    is_popular: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    is_archived: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")

    __table_args__ = (
        sa.CheckConstraint(
            "(kind = 'package' AND stars_amount > 0 AND price >= 0) OR "
            "(kind = 'custom' AND price_per_star > 0 AND min_stars > 0 AND max_stars >= min_stars)",
            name="kind_fields",
        ),
        sa.CheckConstraint("cost_per_star IS NULL OR cost_per_star >= 0", name="cost_non_negative"),
        # At most one popular product.
        sa.Index("uq_products_single_popular", "is_popular", unique=True, postgresql_where=sa.text("is_popular AND NOT is_archived")),
        sa.Index("ix_products_listing", "is_archived", "is_active", "sort_order"),
    )


# ---------------------------------------------------------------------------
# Promo codes, referrals, bonuses
# ---------------------------------------------------------------------------


class PromoCode(TimestampMixin, Base):
    __tablename__ = "promo_codes"

    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(32), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(sa.String(255))
    kind: Mapped[PromoKind] = mapped_column(str_enum(PromoKind, "promo_kind"))
    value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    max_discount: Mapped[Decimal | None] = mapped_column(MONEY)
    min_order_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    starts_at: Mapped[datetime | None]
    expires_at: Mapped[datetime | None]
    max_uses: Mapped[int | None]
    per_user_limit: Mapped[int] = mapped_column(default=1, server_default="1")
    first_order_only: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())

    __table_args__ = (
        sa.CheckConstraint("value > 0", name="value_positive"),
        sa.CheckConstraint("kind <> 'percent' OR value <= 100", name="percent_le_100"),
        sa.CheckConstraint("max_uses IS NULL OR max_uses > 0", name="max_uses_positive"),
        sa.CheckConstraint("per_user_limit > 0", name="per_user_positive"),
        sa.CheckConstraint("code = upper(code)", name="code_upper"),
    )


class PromoCodeUsage(TimestampMixin, Base):
    __tablename__ = "promo_code_usages"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    promo_code_id: Mapped[int] = mapped_column(sa.ForeignKey("promo_codes.id", ondelete="CASCADE"))
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    order_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"), unique=True)
    status: Mapped[PromoUsageStatus] = mapped_column(str_enum(PromoUsageStatus, "promo_usage_status"))
    discount_amount: Mapped[Decimal] = mapped_column(MONEY)

    __table_args__ = (sa.Index("ix_promo_usage_code_user", "promo_code_id", "user_id"),)


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    referrer_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    referred_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    status: Mapped[ReferralStatus] = mapped_column(str_enum(ReferralStatus, "referral_status"), default=ReferralStatus.pending)
    reject_reason: Mapped[str | None] = mapped_column(sa.String(255))
    qualifying_order_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"))
    reward_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    rewarded_at: Mapped[datetime | None]

    __table_args__ = (sa.CheckConstraint("referrer_id <> referred_id", name="not_self"),)


class BonusTransaction(Base):
    """Append-only ledger for the bonus balance. ``dedup_key`` makes every
    credit/debit idempotent (e.g. ``spend:<order>``, ``ref:<referral>``)."""

    __tablename__ = "bonus_transactions"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    amount: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(32))
    order_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"))
    referral_id: Mapped[int | None] = mapped_column(sa.ForeignKey("referrals.id", ondelete="SET NULL"))
    dedup_key: Mapped[str] = mapped_column(sa.String(96), unique=True)
    comment: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    __table_args__ = (sa.CheckConstraint("amount <> 0", name="non_zero"),)


# ---------------------------------------------------------------------------
# Orders, payments, delivery
# ---------------------------------------------------------------------------


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    number: Mapped[str] = mapped_column(sa.String(16), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="RESTRICT"))
    product_id: Mapped[int | None] = mapped_column(sa.ForeignKey("products.id", ondelete="SET NULL"))
    product_kind: Mapped[ProductKind] = mapped_column(str_enum(ProductKind, "order_product_kind"))
    kind: Mapped[OrderKind] = mapped_column(str_enum(OrderKind, "order_kind"), default=OrderKind.regular, server_default="regular")
    stars_amount: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    recipient_type: Mapped[RecipientType] = mapped_column(str_enum(RecipientType, "recipient_type"))
    recipient_username: Mapped[str | None] = mapped_column(sa.String(64))
    recipient_telegram_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    recipient_name: Mapped[str | None] = mapped_column(sa.String(128))

    unit_price: Mapped[Decimal] = mapped_column(RATE)
    subtotal: Mapped[Decimal] = mapped_column(MONEY)
    discount_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    bonus_spent: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    fee_amount: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"), server_default="0")
    total: Mapped[Decimal] = mapped_column(MONEY)
    cost_amount: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(sa.String(3))

    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus, "order_status"), default=OrderStatus.created)
    mode: Mapped[ShopMode] = mapped_column(str_enum(ShopMode, "order_mode"))
    payment_provider: Mapped[str] = mapped_column(sa.String(32))
    delivery_provider: Mapped[str] = mapped_column(sa.String(32))
    promo_code_id: Mapped[int | None] = mapped_column(sa.ForeignKey("promo_codes.id", ondelete="SET NULL"))
    idempotency_key: Mapped[str] = mapped_column(sa.String(64))
    failure_reason: Mapped[str | None] = mapped_column(sa.Text)

    expires_at: Mapped[datetime | None]
    paid_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    cancelled_at: Mapped[datetime | None]
    refunded_at: Mapped[datetime | None]

    user: Mapped[User] = relationship(lazy="raise")
    payments: Mapped[list[Payment]] = relationship(back_populates="order", lazy="raise", order_by="Payment.created_at")
    events: Mapped[list[OrderEvent]] = relationship(back_populates="order", lazy="raise", order_by="OrderEvent.id")
    delivery_task: Mapped[DeliveryTask | None] = relationship(back_populates="order", lazy="raise", uselist=False)
    lucky: Mapped[LuckyDraw | None] = relationship(back_populates="order", lazy="raise", uselist=False)

    __table_args__ = (
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_orders_user_idempotency"),
        sa.CheckConstraint("stars_amount > 0", name="stars_positive"),
        sa.CheckConstraint(
            "subtotal >= 0 AND total >= 0 AND discount_amount >= 0 AND bonus_spent >= 0 AND fee_amount >= 0", name="amounts_non_negative"
        ),
        sa.CheckConstraint("total = subtotal - discount_amount - bonus_spent + fee_amount", name="total_formula"),
        sa.CheckConstraint(
            "recipient_type = 'self' OR recipient_username IS NOT NULL OR recipient_telegram_id IS NOT NULL", name="recipient_present"
        ),
        sa.Index("ix_orders_user_created", "user_id", "created_at"),
        sa.Index("ix_orders_status_created", "status", "created_at"),
        sa.Index("ix_orders_created_at", "created_at"),
        sa.Index("ix_orders_expires_open", "expires_at", postgresql_where=sa.text("status IN ('created', 'pending_payment')")),
    )


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    order_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(sa.String(48))
    from_status: Mapped[str | None] = mapped_column(sa.String(32))
    to_status: Mapped[str | None] = mapped_column(sa.String(32))
    message: Mapped[str | None] = mapped_column(sa.Text)
    actor_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "actor_type"))
    actor_id: Mapped[str | None] = mapped_column(sa.String(64))
    # Visible to the customer in the order timeline.
    is_public: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    data: Mapped[dict[str, Any] | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    order: Mapped[Order] = relationship(back_populates="events", lazy="raise")

    __table_args__ = (sa.Index("ix_order_events_order", "order_id", "id"),)


class Payment(TimestampMixin, Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("orders.id", ondelete="RESTRICT"), index=True)
    provider: Mapped[str] = mapped_column(sa.String(32))
    provider_payment_id: Mapped[str | None] = mapped_column(sa.String(128))
    idempotency_key: Mapped[str] = mapped_column(sa.String(96), unique=True)
    status: Mapped[PaymentStatus] = mapped_column(str_enum(PaymentStatus, "payment_status"), default=PaymentStatus.created)
    amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(sa.String(3))
    paid_amount: Mapped[str | None] = mapped_column(sa.String(40))
    paid_asset: Mapped[str | None] = mapped_column(sa.String(16))
    pay_url: Mapped[str | None] = mapped_column(sa.Text)
    pay_url_kind: Mapped[str | None] = mapped_column(sa.String(16))
    is_demo: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    # Captured after the order was already paid by another payment.
    is_duplicate: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    expires_at: Mapped[datetime | None]
    confirmed_at: Mapped[datetime | None]
    refunded_at: Mapped[datetime | None]
    refund_reference: Mapped[str | None] = mapped_column(sa.String(128))
    refund_reason: Mapped[str | None] = mapped_column(sa.Text)
    refund_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    refund_next_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    provider_data: Mapped[dict[str, Any] | None]

    order: Mapped[Order] = relationship(back_populates="payments", lazy="raise")

    __table_args__ = (
        sa.UniqueConstraint("provider", "provider_payment_id", name="uq_payments_provider_ref"),
        sa.CheckConstraint("amount >= 0", name="amount_non_negative"),
        # Only one captured payment can back an order. A duplicate capture
        # (customer paid twice) is moved to refund_pending, never 'succeeded'.
        sa.Index(
            "uq_payments_one_success_per_order",
            "order_id",
            unique=True,
            postgresql_where=sa.text("status = 'succeeded'"),
        ),
        sa.Index("ix_payments_refund_due", "refund_next_at", postgresql_where=sa.text("status = 'refund_pending'")),
        sa.Index("ix_payments_open", "status", "updated_at", postgresql_where=sa.text("status IN ('created', 'pending')")),
    )


class PaymentWebhookEvent(Base):
    __tablename__ = "payment_webhook_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    provider: Mapped[str] = mapped_column(sa.String(32))
    # Set only for events with a valid signature — unverified data must never
    # be able to "pre-claim" an event id and block the genuine delivery.
    event_id: Mapped[str | None] = mapped_column(sa.String(128))
    event_type: Mapped[str | None] = mapped_column(sa.String(64))
    signature_valid: Mapped[bool]
    status: Mapped[WebhookStatus] = mapped_column(str_enum(WebhookStatus, "webhook_status"))
    payment_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("payments.id", ondelete="SET NULL"), index=True)
    payload: Mapped[dict[str, Any] | None]
    remote_ip: Mapped[str | None] = mapped_column(sa.String(64))
    error: Mapped[str | None] = mapped_column(sa.Text)
    received_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    processed_at: Mapped[datetime | None]

    __table_args__ = (
        sa.UniqueConstraint("provider", "event_id", name="uq_webhook_provider_event"),
        sa.Index("ix_webhook_received", "received_at"),
    )


class DeliveryTask(TimestampMixin, Base):
    __tablename__ = "delivery_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    order_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("orders.id", ondelete="RESTRICT"), unique=True)
    provider: Mapped[str] = mapped_column(sa.String(32))
    status: Mapped[DeliveryStatus] = mapped_column(str_enum(DeliveryStatus, "delivery_status"), default=DeliveryStatus.queued)
    # Sent to the supplier with every request so retries never deliver twice.
    idempotency_key: Mapped[str] = mapped_column(sa.String(96), unique=True)
    external_id: Mapped[str | None] = mapped_column(sa.String(128))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(default=5, server_default="5")
    next_attempt_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    locked_at: Mapped[datetime | None]
    locked_by: Mapped[str | None] = mapped_column(sa.String(64))
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    result: Mapped[dict[str, Any] | None]
    completed_at: Mapped[datetime | None]

    order: Mapped[Order] = relationship(back_populates="delivery_task", lazy="raise")

    __table_args__ = (
        sa.Index("ix_delivery_due", "status", "next_attempt_at"),
        sa.UniqueConstraint("provider", "external_id", name="uq_delivery_provider_ref"),
    )


class LuckyDraw(Base):
    """Lucky Buy attempt of one order, provably fair by commit-reveal:
    ``server_seed_hash`` is shown when the order is created, the customer's
    ``client_seed`` is fixed when the first payment is created, and the draw
    runs once, in the transaction that confirms the payment. ``server_seed``
    is revealed only after the draw (see ``services/lucky.py``)."""

    __tablename__ = "lucky_draws"

    order_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True)
    # Chance in basis points: 2500 = 25 %.
    chance_bp: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    # Package price and cost at the time of the attempt.
    prize_value: Mapped[Decimal] = mapped_column(MONEY, nullable=False)
    prize_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    server_seed: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    server_seed_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    client_seed: Mapped[str | None] = mapped_column(sa.String(64))
    roll_bp: Mapped[int | None] = mapped_column(sa.Integer)
    won: Mapped[bool | None]
    drawn_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    order: Mapped[Order] = relationship(back_populates="lucky", lazy="raise")

    __table_args__ = (
        sa.CheckConstraint("chance_bp BETWEEN 1 AND 9999", name="chance_range"),
        sa.CheckConstraint("roll_bp IS NULL OR roll_bp BETWEEN 0 AND 9999", name="roll_range"),
        sa.CheckConstraint(
            "(drawn_at IS NULL AND won IS NULL AND roll_bp IS NULL) OR "
            "(drawn_at IS NOT NULL AND won IS NOT NULL AND roll_bp IS NOT NULL AND client_seed IS NOT NULL)",
            name="draw_complete",
        ),
    )


# ---------------------------------------------------------------------------
# Notifications (transactional outbox)
# ---------------------------------------------------------------------------


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    chat_id: Mapped[int] = mapped_column(sa.BigInteger)
    user_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    order_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(sa.String(48))
    text: Mapped[str] = mapped_column(sa.Text)
    reply_markup: Mapped[dict[str, Any] | None]
    dedup_key: Mapped[str] = mapped_column(sa.String(128), unique=True)
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus, "notification_status"), default=NotificationStatus.pending
    )
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    sent_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_notifications_due", "status", "next_attempt_at"),)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


class AdminUser(TimestampMixin, Base):
    __tablename__ = "admin_users"

    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(sa.BigInteger, unique=True)
    username: Mapped[str | None] = mapped_column(sa.String(64))
    display_name: Mapped[str | None] = mapped_column(sa.String(128))
    role: Mapped[AdminRole] = mapped_column(str_enum(AdminRole, "admin_role"), default=AdminRole.support)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    last_login_at: Mapped[datetime | None]


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    admin_id: Mapped[int] = mapped_column(sa.ForeignKey("admin_users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    user_agent: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    last_seen_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class AdminLoginToken(Base):
    """One-time login link issued by the bot (/admin). Only the hash is stored."""

    __tablename__ = "admin_login_tokens"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    admin_id: Mapped[int] = mapped_column(sa.ForeignKey("admin_users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())


class AdminAuditLog(Base):
    __tablename__ = "admin_audit_logs"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admin_users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(sa.String(64))
    entity_type: Mapped[str | None] = mapped_column(sa.String(32))
    entity_id: Mapped[str | None] = mapped_column(sa.String(64))
    summary: Mapped[str | None] = mapped_column(sa.Text)
    before: Mapped[dict[str, Any] | None]
    after: Mapped[dict[str, Any] | None]
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    user_agent: Mapped[str | None] = mapped_column(sa.String(255))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_audit_entity", "entity_type", "entity_id"),
        sa.Index("ix_audit_created", "created_at"),
    )


class AppSetting(Base):
    """Runtime-editable, non-secret settings and content (JSON per key)."""

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    value: Mapped[dict[str, Any]]
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now(), onupdate=utcnow)
    updated_by: Mapped[int | None] = mapped_column(sa.ForeignKey("admin_users.id", ondelete="SET NULL"))


# ---------------------------------------------------------------------------
# Support
# ---------------------------------------------------------------------------


class SupportTicket(TimestampMixin, Base):
    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    order_id: Mapped[uuid.UUID | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"))
    subject: Mapped[str] = mapped_column(sa.String(160))
    status: Mapped[TicketStatus] = mapped_column(str_enum(TicketStatus, "ticket_status"), default=TicketStatus.open)
    last_message_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    messages: Mapped[list[SupportMessage]] = relationship(lazy="raise", order_by="SupportMessage.id")

    __table_args__ = (sa.Index("ix_tickets_status", "status", "last_message_at"),)


class SupportMessage(Base):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    ticket_id: Mapped[int] = mapped_column(sa.ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True)
    author_type: Mapped[ActorType] = mapped_column(str_enum(ActorType, "message_author"))
    admin_id: Mapped[int | None] = mapped_column(sa.ForeignKey("admin_users.id", ondelete="SET NULL"))
    text: Mapped[str] = mapped_column(sa.Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())


# ---------------------------------------------------------------------------
# Bot
# ---------------------------------------------------------------------------


class BotButton(TimestampMixin, Base):
    """Extra buttons of the bot's main menu, managed in the admin panel."""

    __tablename__ = "bot_buttons"

    id: Mapped[int] = mapped_column(sa.Integer, sa.Identity(), primary_key=True)
    title: Mapped[str] = mapped_column(sa.String(48))
    emoji: Mapped[str | None] = mapped_column(sa.String(16))
    row: Mapped[int] = mapped_column(sa.SmallInteger, default=0, server_default="0")
    position: Mapped[int] = mapped_column(sa.SmallInteger, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    action: Mapped[BotButtonAction] = mapped_column(str_enum(BotButtonAction, "bot_button_action"))
    style: Mapped[ButtonStyle | None] = mapped_column(str_enum(ButtonStyle, "bot_button_style"), nullable=True)
    text: Mapped[str | None] = mapped_column(sa.Text)
    url: Mapped[str | None] = mapped_column(sa.String(512))
    section: Mapped[str | None] = mapped_column(sa.String(32))
    product_id: Mapped[int | None] = mapped_column(sa.ForeignKey("products.id", ondelete="SET NULL"))

    __table_args__ = (
        sa.CheckConstraint("row >= 0 AND row < 20 AND position >= 0 AND position < 20", name="placement_range"),
        sa.Index("ix_bot_buttons_order", "row", "position"),
    )


class BotState(Base):
    """Dialogue state of the bot (aiogram FSM), shared by every instance."""

    __tablename__ = "bot_states"

    key: Mapped[str] = mapped_column(sa.String(160), primary_key=True)
    state: Mapped[str | None] = mapped_column(sa.String(128))
    data: Mapped[dict[str, Any]] = mapped_column(default=dict, server_default=sa.text("'{}'::jsonb"))
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now(), onupdate=utcnow)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ErrorEvent(Base):
    """Errors of the API, the bot and the Mini App shown in the admin panel.
    Secrets are scrubbed before saving."""

    __tablename__ = "error_events"

    id: Mapped[int] = mapped_column(sa.BigInteger, sa.Identity(), primary_key=True)
    source: Mapped[str] = mapped_column(sa.String(16))  # api | bot | client | worker
    message: Mapped[str] = mapped_column(sa.String(1000))
    path: Mapped[str | None] = mapped_column(sa.String(256))
    details: Mapped[dict[str, Any] | None]
    user_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(default=utcnow, server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_error_events_created_at", "created_at"),)
