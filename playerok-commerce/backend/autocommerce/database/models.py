"""Database schema.

Normalised tables for users and access, catalogue, suppliers, pricing,
listings, orders, inventory, messages, automation, notifications and audit.
All money columns are NUMERIC(14,2); exchange rates NUMERIC(18,6); percents
NUMERIC(9,4). Secrets and digital codes are stored encrypted (shared/crypto).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import MONEY, PERCENT, RATE, Base, TimestampMixin, str_enum
from .enums import (
    CodeStatus,
    ComplianceStatus,
    Confidence,
    DeliveryType,
    JobStatus,
    ListingStatus,
    LogResult,
    MessageDirection,
    MessageStatus,
    NotificationStatus,
    OrderStatus,
    ProductStatus,
    PurchaseMode,
    RoleCode,
    Sentiment,
    Severity,
    SupplierOrderStatus,
    SupplierStatus,
    SyncStatus,
    TransactionKind,
)

# ---------------------------------------------------------------------------
# Users and access
# ---------------------------------------------------------------------------


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[RoleCode] = mapped_column(str_enum(RoleCode, "role_code"), unique=True)
    name: Mapped[str] = mapped_column(sa.String(64))
    permissions: Mapped[list[Any]] = mapped_column(default=list)


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(254), unique=True)
    display_name: Mapped[str] = mapped_column(sa.String(120))
    password_hash: Mapped[str] = mapped_column(sa.String(255))
    role_id: Mapped[int] = mapped_column(sa.ForeignKey("roles.id", ondelete="RESTRICT"), index=True)
    telegram_id: Mapped[int | None] = mapped_column(sa.BigInteger, unique=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default=sa.true())
    totp_secret_enc: Mapped[str | None] = mapped_column(sa.Text)
    totp_enabled: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    failed_logins: Mapped[int] = mapped_column(default=0, server_default="0")
    locked_until: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]
    password_changed_at: Mapped[datetime | None]
    notification_prefs: Mapped[dict[str, Any]] = mapped_column(default=dict)

    role: Mapped[Role] = relationship(lazy="joined")


class WebSession(Base):
    __tablename__ = "web_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    user_agent: Mapped[str | None] = mapped_column(sa.String(300))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    last_seen_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]


class OneTimeToken(Base):
    """Telegram linking codes and similar single-use secrets (only the hash is stored)."""

    __tablename__ = "one_time_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    purpose: Mapped[str] = mapped_column(sa.String(32))
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)
    user_id: Mapped[int | None] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(sa.String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSONB)
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), onupdate=sa.func.now())
    updated_by: Mapped[str | None] = mapped_column(sa.String(120))


class AutoSetting(Base):
    """One row per item of the «Автонастройки» menu."""

    __tablename__ = "auto_settings"

    code: Mapped[str] = mapped_column(sa.String(48), primary_key=True)
    enabled: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    config: Mapped[dict[str, Any]] = mapped_column(default=dict)
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), onupdate=sa.func.now())
    updated_by: Mapped[str | None] = mapped_column(sa.String(120))
    last_run_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(sa.Text)


class IntegrationCredential(TimestampMixin, Base):
    __tablename__ = "integration_credentials"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(sa.String(48), unique=True)
    fields_enc: Mapped[str] = mapped_column(sa.Text)
    preview: Mapped[dict[str, Any]] = mapped_column(default=dict)  # masked values only
    rotated_at: Mapped[datetime | None]
    updated_by: Mapped[str | None] = mapped_column(sa.String(120))


# ---------------------------------------------------------------------------
# Catalogue
# ---------------------------------------------------------------------------


class ProductCategory(TimestampMixin, Base):
    __tablename__ = "product_categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(64), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    group: Mapped[str] = mapped_column(sa.String(48), index=True)  # telegram, promotion, steam, giftcards, games, roblox, subscriptions
    parent_id: Mapped[int | None] = mapped_column(sa.ForeignKey("product_categories.id", ondelete="SET NULL"))
    marketplace_commission_pct: Mapped[Decimal] = mapped_column(PERCENT, default=Decimal("20"))
    commission_source: Mapped[str] = mapped_column(sa.String(255), default="")
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        str_enum(ComplianceStatus, "compliance_status"), default=ComplianceStatus.NEEDS_REVIEW
    )
    compliance_note: Mapped[str] = mapped_column(sa.Text, default="")
    dispute_risk_pct: Mapped[Decimal] = mapped_column(PERCENT, default=Decimal("5"))
    auto_delivery_possible: Mapped[bool] = mapped_column(default=False)
    listing_template: Mapped[str] = mapped_column(sa.String(48), default="default")
    image_template: Mapped[str | None] = mapped_column(sa.String(64))
    sort: Mapped[int] = mapped_column(default=100)


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(sa.String(64), unique=True)
    name: Mapped[str] = mapped_column(sa.String(200))
    category_id: Mapped[int] = mapped_column(sa.ForeignKey("product_categories.id", ondelete="RESTRICT"), index=True)
    description: Mapped[str] = mapped_column(sa.Text, default="")
    region: Mapped[str] = mapped_column(sa.String(64), default="")
    face_value: Mapped[Decimal | None] = mapped_column(MONEY)
    face_currency: Mapped[str | None] = mapped_column(sa.String(8))
    delivery_type: Mapped[DeliveryType] = mapped_column(str_enum(DeliveryType, "delivery_type"), default=DeliveryType.MANUAL)
    delivery_time: Mapped[str] = mapped_column(sa.String(120), default="до 30 минут")
    activation_notes: Mapped[str] = mapped_column(sa.Text, default="")
    buyer_instructions: Mapped[str] = mapped_column(sa.Text, default="")
    required_buyer_data: Mapped[str] = mapped_column(sa.String(255), default="")  # e.g. "ссылка на пост", "username"
    status: Mapped[ProductStatus] = mapped_column(str_enum(ProductStatus, "product_status"), default=ProductStatus.DRAFT, index=True)
    compliance_override: Mapped[ComplianceStatus | None] = mapped_column(str_enum(ComplianceStatus, "product_compliance"))
    preferred_supplier_product_id: Mapped[int | None] = mapped_column(sa.ForeignKey("supplier_products.id", ondelete="SET NULL"))
    # units ordered from the supplier per one unit sold (e.g. 1000 for «1000 подписчиков»)
    supplier_quantity: Mapped[int] = mapped_column(default=1, server_default="1")
    manual_unit_cost: Mapped[Decimal | None] = mapped_column(MONEY)  # cost entered by hand (RUB)
    manual_cost_updated_at: Mapped[datetime | None]
    current_price: Mapped[Decimal | None] = mapped_column(MONEY)
    min_price: Mapped[Decimal | None] = mapped_column(MONEY)
    recommended_price: Mapped[Decimal | None] = mapped_column(MONEY)
    full_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    expected_profit: Mapped[Decimal | None] = mapped_column(MONEY)
    expected_margin_pct: Mapped[Decimal | None] = mapped_column(PERCENT)
    pricing_status: Mapped[str] = mapped_column(sa.String(32), default="not_calculated")
    pricing_notes: Mapped[list[Any]] = mapped_column(default=list)
    priced_at: Mapped[datetime | None]
    price_version: Mapped[int] = mapped_column(default=1, server_default="1")
    auto_purchase_allowed: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    image_template: Mapped[str | None] = mapped_column(sa.String(64))  # overrides the category's template

    category: Mapped[ProductCategory] = relationship(lazy="joined")

    __mapper_args__ = {"version_id_col": price_version}


class Inventory(Base):
    """Stock counters. For CODE products they mirror digital_codes; for SERVICE
    products ``unlimited`` is set when the supplier performs the service."""

    __tablename__ = "inventory"

    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    quantity_available: Mapped[int] = mapped_column(default=0, server_default="0")
    quantity_reserved: Mapped[int] = mapped_column(default=0, server_default="0")
    unlimited: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    low_stock_threshold: Mapped[int] = mapped_column(default=3, server_default="3")
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), onupdate=sa.func.now())

    __table_args__ = (
        sa.CheckConstraint("quantity_available >= 0", name="available_non_negative"),
        sa.CheckConstraint("quantity_reserved >= 0", name="reserved_non_negative"),
    )


# ---------------------------------------------------------------------------
# Suppliers and prices
# ---------------------------------------------------------------------------


class Supplier(TimestampMixin, Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(48), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    website: Mapped[str] = mapped_column(sa.String(255), default="")
    adapter: Mapped[str] = mapped_column(sa.String(32))  # smm_v2, reloadly, fragment, manual, none
    categories: Mapped[list[Any]] = mapped_column(default=list)
    integration_method: Mapped[str] = mapped_column(sa.String(255), default="")
    status: Mapped[SupplierStatus] = mapped_column(str_enum(SupplierStatus, "supplier_status"), default=SupplierStatus.NOT_CONFIGURED)
    status_reason: Mapped[str] = mapped_column(sa.Text, default="")
    purchase_mode: Mapped[PurchaseMode] = mapped_column(str_enum(PurchaseMode, "purchase_mode"), default=PurchaseMode.MONITOR)
    currency: Mapped[str] = mapped_column(sa.String(8), default="RUB")
    balance: Mapped[Decimal | None] = mapped_column(MONEY)
    balance_currency: Mapped[str | None] = mapped_column(sa.String(8))
    balance_checked_at: Mapped[datetime | None]
    max_single_purchase: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    daily_limit: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    max_operations_per_day: Mapped[int] = mapped_column(default=50)
    fee_pct: Mapped[Decimal] = mapped_column(PERCENT, default=Decimal("0"))
    fee_fixed: Mapped[Decimal] = mapped_column(MONEY, default=Decimal("0"))
    refund_policy: Mapped[str] = mapped_column(sa.Text, default="")
    policy_note: Mapped[str] = mapped_column(sa.Text, default="")
    verification: Mapped[dict[str, Any]] = mapped_column(default=dict)  # {checked_at, sources: [...], facts: [...]}
    last_check_at: Mapped[datetime | None]
    last_sync_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    success_count: Mapped[int] = mapped_column(default=0, server_default="0")
    error_count: Mapped[int] = mapped_column(default=0, server_default="0")


class SupplierProduct(TimestampMixin, Base):
    __tablename__ = "supplier_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(sa.ForeignKey("suppliers.id", ondelete="CASCADE"), index=True)
    external_id: Mapped[str] = mapped_column(sa.String(120))
    name: Mapped[str] = mapped_column(sa.String(300))
    category: Mapped[str] = mapped_column(sa.String(120), default="")
    price: Mapped[Decimal | None] = mapped_column(RATE)  # supplier currency, per unit (or per 1000 for SMM)
    price_unit: Mapped[int] = mapped_column(default=1)  # quantity the price refers to (1000 for SMM rates)
    currency: Mapped[str] = mapped_column(sa.String(8), default="RUB")
    min_quantity: Mapped[int | None]
    max_quantity: Mapped[int | None]
    region: Mapped[str] = mapped_column(sa.String(64), default="")
    available: Mapped[bool] = mapped_column(default=True)
    compliance_status: Mapped[ComplianceStatus] = mapped_column(
        str_enum(ComplianceStatus, "supplier_product_compliance"), default=ComplianceStatus.NEEDS_REVIEW
    )
    raw: Mapped[dict[str, Any]] = mapped_column(default=dict)
    last_seen_at: Mapped[datetime | None]
    price_changed_at: Mapped[datetime | None]

    supplier: Mapped[Supplier] = relationship(lazy="joined")

    __table_args__ = (sa.UniqueConstraint("supplier_id", "external_id", name="uq_supplier_products_external"),)


class SupplierPriceHistory(Base):
    __tablename__ = "supplier_price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_product_id: Mapped[int] = mapped_column(sa.ForeignKey("supplier_products.id", ondelete="CASCADE"))
    price: Mapped[Decimal] = mapped_column(RATE)
    currency: Mapped[str] = mapped_column(sa.String(8))
    price_rub: Mapped[Decimal | None] = mapped_column(MONEY)
    captured_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())

    __table_args__ = (sa.Index("ix_supplier_price_history_product_time", "supplier_product_id", "captured_at"),)


class FxRate(Base):
    __tablename__ = "fx_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    base: Mapped[str] = mapped_column(sa.String(8))
    quote: Mapped[str] = mapped_column(sa.String(8), default="RUB")
    rate: Mapped[Decimal] = mapped_column(RATE)
    source: Mapped[str] = mapped_column(sa.String(32))
    rate_date: Mapped[datetime]
    fetched_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())

    __table_args__ = (sa.UniqueConstraint("base", "quote", "source", "rate_date", name="uq_fx_rates_point"),)


class MarketPriceSnapshot(Base):
    """Competitor prices observed on PlayerOK (entered by the operator or by an adapter)."""

    __tablename__ = "market_price_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"))
    source: Mapped[str] = mapped_column(sa.String(32), default="manual")
    competitor_min: Mapped[Decimal | None] = mapped_column(MONEY)
    competitor_median: Mapped[Decimal | None] = mapped_column(MONEY)
    competitor_max: Mapped[Decimal | None] = mapped_column(MONEY)
    offers_count: Mapped[int | None]
    note: Mapped[str] = mapped_column(sa.Text, default="")
    observed_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    recorded_by: Mapped[str | None] = mapped_column(sa.String(120))

    __table_args__ = (sa.Index("ix_market_snapshots_product_time", "product_id", "observed_at"),)


class PriceRule(TimestampMixin, Base):
    """Profitability guards. Resolution: product rule > category rule > global rule."""

    __tablename__ = "price_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(sa.String(16))  # global | category | product
    category_id: Mapped[int | None] = mapped_column(sa.ForeignKey("product_categories.id", ondelete="CASCADE"), unique=True)
    product_id: Mapped[int | None] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), unique=True)
    enabled: Mapped[bool] = mapped_column(default=True)
    values: Mapped[dict[str, Any]] = mapped_column(default=dict)  # only overridden fields, Decimal as strings

    __table_args__ = (
        sa.CheckConstraint("scope in ('global','category','product')", name="scope_valid"),
        sa.Index("uq_price_rules_global", "scope", unique=True, postgresql_where=sa.text("scope = 'global'")),
    )


class ResearchScore(Base):
    __tablename__ = "research_scores"

    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), primary_key=True)
    total_score: Mapped[Decimal] = mapped_column(PERCENT)
    confidence: Mapped[Confidence] = mapped_column(str_enum(Confidence, "confidence"))
    factors: Mapped[dict[str, Any]] = mapped_column(default=dict)
    excluded_reason: Mapped[str | None] = mapped_column(sa.Text)
    computed_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


# ---------------------------------------------------------------------------
# Listings
# ---------------------------------------------------------------------------


class Listing(TimestampMixin, Base):
    __tablename__ = "listings"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    marketplace: Mapped[str] = mapped_column(sa.String(32), default="playerok")
    external_id: Mapped[str | None] = mapped_column(sa.String(120))
    external_url: Mapped[str | None] = mapped_column(sa.String(500))
    marketplace_category: Mapped[str] = mapped_column(sa.String(200), default="")
    title: Mapped[str] = mapped_column(sa.String(200))
    description: Mapped[str] = mapped_column(sa.Text)
    price: Mapped[Decimal] = mapped_column(MONEY)
    quantity: Mapped[int] = mapped_column(default=1)
    status: Mapped[ListingStatus] = mapped_column(str_enum(ListingStatus, "listing_status"), default=ListingStatus.DRAFT, index=True)
    status_reason: Mapped[str] = mapped_column(sa.Text, default="")
    template_code: Mapped[str] = mapped_column(sa.String(48), default="default")
    version: Mapped[int] = mapped_column(default=1, server_default="1")
    preview_confirmed_at: Mapped[datetime | None]
    published_at: Mapped[datetime | None]
    last_bumped_at: Mapped[datetime | None]
    relist_on_complete: Mapped[bool] = mapped_column(default=False)
    auto_created: Mapped[bool] = mapped_column(default=False)

    product: Mapped[Product] = relationship(lazy="joined")

    __table_args__ = (
        sa.Index("uq_listings_external", "marketplace", "external_id", unique=True, postgresql_where=sa.text("external_id IS NOT NULL")),
        # one live listing per product and marketplace: protection from double publication
        sa.Index(
            "uq_listings_active_product",
            "marketplace",
            "product_id",
            unique=True,
            postgresql_where=sa.text("status IN ('ready','published','paused')"),
        ),
    )


class ListingRevision(Base):
    __tablename__ = "listing_revisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(sa.ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    version: Mapped[int]
    action: Mapped[str] = mapped_column(sa.String(48))
    snapshot: Mapped[dict[str, Any]] = mapped_column(default=dict)
    actor: Mapped[str | None] = mapped_column(sa.String(120))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


class ImageTemplate(TimestampMixin, Base):
    __tablename__ = "image_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(sa.String(64), unique=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    kind: Mapped[str] = mapped_column(sa.String(16))  # demo | user
    category_groups: Mapped[list[Any]] = mapped_column(default=list)
    base_path: Mapped[str] = mapped_column(sa.String(500))  # relative to assets/templates
    width: Mapped[int]
    height: Mapped[int]
    spec: Mapped[dict[str, Any]] = mapped_column(default=dict)
    active: Mapped[bool] = mapped_column(default=True)


class ListingImage(Base):
    __tablename__ = "listing_images"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int | None] = mapped_column(sa.ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="CASCADE"), index=True)
    listing_version: Mapped[int | None]
    template_code: Mapped[str] = mapped_column(sa.String(64))
    path: Mapped[str] = mapped_column(sa.String(500))  # relative to storage_dir
    width: Mapped[int]
    height: Mapped[int]
    sha256: Mapped[str] = mapped_column(sa.String(64))
    is_preview: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------


ORDER_NUMBER_SEQ = sa.Sequence("order_number_seq", metadata=Base.metadata)


class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(
        sa.String(24), unique=True, server_default=sa.text("'PO-' || lpad(nextval('order_number_seq')::text, 6, '0')")
    )
    marketplace: Mapped[str] = mapped_column(sa.String(32), default="playerok")
    external_id: Mapped[str] = mapped_column(sa.String(120))
    source: Mapped[str] = mapped_column(sa.String(16), default="manual")  # manual | import | adapter
    buyer_name: Mapped[str | None] = mapped_column(sa.String(120))
    buyer_data: Mapped[dict[str, Any]] = mapped_column(default=dict)  # only what fulfilment needs (link, username)
    status: Mapped[OrderStatus] = mapped_column(str_enum(OrderStatus, "order_status"), default=OrderStatus.NEW, index=True)
    status_reason: Mapped[str] = mapped_column(sa.Text, default="")
    needs_attention: Mapped[bool] = mapped_column(default=False, index=True)
    automation_paused: Mapped[bool] = mapped_column(default=False)
    review_passed: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    total_amount: Mapped[Decimal] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(sa.String(8), default="RUB")
    marketplace_fee: Mapped[Decimal | None] = mapped_column(MONEY)
    cost_total: Mapped[Decimal | None] = mapped_column(MONEY)
    net_profit: Mapped[Decimal | None] = mapped_column(MONEY)
    is_test: Mapped[bool] = mapped_column(default=False)
    placed_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)
    delivered_at: Mapped[datetime | None]
    buyer_confirmed_at: Mapped[datetime | None]
    completed_at: Mapped[datetime | None]
    review_received_at: Mapped[datetime | None]
    reminders_sent: Mapped[dict[str, Any]] = mapped_column(default=dict)
    notes: Mapped[str] = mapped_column(sa.Text, default="")
    version: Mapped[int] = mapped_column(default=1, server_default="1")

    items: Mapped[list[OrderItem]] = relationship(back_populates="order", lazy="selectin", order_by="OrderItem.id")

    __table_args__ = (sa.UniqueConstraint("marketplace", "external_id", name="uq_orders_marketplace_external"),)
    __mapper_args__ = {"version_id_col": version}


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    listing_id: Mapped[int | None] = mapped_column(sa.ForeignKey("listings.id", ondelete="SET NULL"))
    quantity: Mapped[int] = mapped_column(default=1)
    unit_price: Mapped[Decimal] = mapped_column(MONEY)
    unit_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    fulfilled_quantity: Mapped[int] = mapped_column(default=0, server_default="0")

    order: Mapped[Order] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(lazy="joined")

    __table_args__ = (sa.CheckConstraint("quantity > 0", name="quantity_positive"),)


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(sa.ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(sa.String(32))
    to_status: Mapped[str | None] = mapped_column(sa.String(32))
    actor: Mapped[str] = mapped_column(sa.String(120))
    message: Mapped[str] = mapped_column(sa.Text, default="")
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())


class SupplierOrder(TimestampMixin, Base):
    __tablename__ = "supplier_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(sa.ForeignKey("suppliers.id", ondelete="RESTRICT"), index=True)
    supplier_product_id: Mapped[int | None] = mapped_column(sa.ForeignKey("supplier_products.id", ondelete="SET NULL"))
    order_item_id: Mapped[int | None] = mapped_column(sa.ForeignKey("order_items.id", ondelete="SET NULL"), index=True)
    idempotency_key: Mapped[str] = mapped_column(sa.String(120), unique=True)
    external_id: Mapped[str | None] = mapped_column(sa.String(120))
    status: Mapped[SupplierOrderStatus] = mapped_column(
        str_enum(SupplierOrderStatus, "supplier_order_status"), default=SupplierOrderStatus.CREATED, index=True
    )
    quantity: Mapped[int] = mapped_column(default=1)
    cost: Mapped[Decimal | None] = mapped_column(MONEY)
    currency: Mapped[str] = mapped_column(sa.String(8), default="RUB")
    cost_rub: Mapped[Decimal | None] = mapped_column(MONEY)
    is_test: Mapped[bool] = mapped_column(default=False)
    request: Mapped[dict[str, Any]] = mapped_column(default=dict)
    response: Mapped[dict[str, Any]] = mapped_column(default=dict)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    confirmed_by: Mapped[str | None] = mapped_column(sa.String(120))


class DigitalCode(Base):
    __tablename__ = "digital_codes"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(sa.ForeignKey("products.id", ondelete="RESTRICT"))
    code_enc: Mapped[str] = mapped_column(sa.Text)
    code_hash: Mapped[str] = mapped_column(sa.String(64), unique=True)  # one code exists once: no double sale
    code_mask: Mapped[str] = mapped_column(sa.String(32))
    status: Mapped[CodeStatus] = mapped_column(str_enum(CodeStatus, "code_status"), default=CodeStatus.AVAILABLE)
    order_item_id: Mapped[int | None] = mapped_column(sa.ForeignKey("order_items.id", ondelete="RESTRICT"), index=True)
    supplier_order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("supplier_orders.id", ondelete="SET NULL"))
    unit_cost: Mapped[Decimal | None] = mapped_column(MONEY)
    source: Mapped[str] = mapped_column(sa.String(32), default="manual")
    is_test: Mapped[bool] = mapped_column(default=False)
    expires_at: Mapped[datetime | None]
    reserved_at: Mapped[datetime | None]
    issued_at: Mapped[datetime | None]
    revealed_count: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())

    __table_args__ = (
        sa.Index("ix_digital_codes_pick", "product_id", "status", "id"),
        sa.CheckConstraint("(status IN ('available','void')) OR order_item_id IS NOT NULL", name="assigned_when_used"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[TransactionKind] = mapped_column(str_enum(TransactionKind, "transaction_kind"), index=True)
    order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    supplier_order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("supplier_orders.id", ondelete="SET NULL"))
    amount: Mapped[Decimal] = mapped_column(MONEY)  # signed, in currency
    currency: Mapped[str] = mapped_column(sa.String(8), default="RUB")
    amount_rub: Mapped[Decimal] = mapped_column(MONEY)
    fx_rate: Mapped[Decimal | None] = mapped_column(RATE)
    description: Mapped[str] = mapped_column(sa.String(300), default="")
    dedupe_key: Mapped[str | None] = mapped_column(sa.String(120), unique=True)
    is_test: Mapped[bool] = mapped_column(default=False)
    occurred_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)


# ---------------------------------------------------------------------------
# Buyer communication
# ---------------------------------------------------------------------------


class CustomerMessage(Base):
    __tablename__ = "customer_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    marketplace: Mapped[str] = mapped_column(sa.String(32), default="playerok")
    external_id: Mapped[str | None] = mapped_column(sa.String(120))
    chat_external_id: Mapped[str | None] = mapped_column(sa.String(120))
    order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    buyer_name: Mapped[str | None] = mapped_column(sa.String(120))
    direction: Mapped[MessageDirection] = mapped_column(str_enum(MessageDirection, "message_direction"))
    text: Mapped[str] = mapped_column(sa.Text)
    status: Mapped[MessageStatus] = mapped_column(str_enum(MessageStatus, "message_status"), default=MessageStatus.NEW, index=True)
    source: Mapped[str] = mapped_column(sa.String(16), default="manual")
    matched_rule_id: Mapped[int | None] = mapped_column(sa.ForeignKey("autoresponder_rules.id", ondelete="SET NULL"))
    suggested_reply: Mapped[str | None] = mapped_column(sa.Text)
    problem_hint: Mapped[str | None] = mapped_column(sa.String(255))
    handled_by: Mapped[str | None] = mapped_column(sa.String(120))
    handled_at: Mapped[datetime | None]
    received_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)

    __table_args__ = (
        sa.Index(
            "uq_customer_messages_external",
            "marketplace",
            "external_id",
            unique=True,
            postgresql_where=sa.text("external_id IS NOT NULL"),
        ),
    )


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    marketplace: Mapped[str] = mapped_column(sa.String(32), default="playerok")
    external_id: Mapped[str | None] = mapped_column(sa.String(120))
    order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"), index=True)
    rating: Mapped[int | None]
    text: Mapped[str] = mapped_column(sa.Text, default="")
    sentiment: Mapped[Sentiment] = mapped_column(str_enum(Sentiment, "sentiment"))
    source: Mapped[str] = mapped_column(sa.String(16), default="manual")
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)

    __table_args__ = (
        sa.CheckConstraint("rating IS NULL OR (rating BETWEEN 1 AND 5)", name="rating_range"),
        sa.Index("uq_reviews_external", "marketplace", "external_id", unique=True, postgresql_where=sa.text("external_id IS NOT NULL")),
    )


class AutoresponderRule(TimestampMixin, Base):
    __tablename__ = "autoresponder_rules"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(120))
    priority: Mapped[int] = mapped_column(default=100)
    enabled: Mapped[bool] = mapped_column(default=True)
    match_type: Mapped[str] = mapped_column(sa.String(16), default="keywords")  # keywords | regex | fallback
    patterns: Mapped[list[Any]] = mapped_column(default=list)
    order_statuses: Mapped[list[Any]] = mapped_column(default=list)  # empty: any
    action: Mapped[str] = mapped_column(sa.String(16), default="reply")  # reply | escalate | status
    reply_template: Mapped[str] = mapped_column(sa.Text, default="")
    hits: Mapped[int] = mapped_column(default=0, server_default="0")
    last_hit_at: Mapped[datetime | None]


# ---------------------------------------------------------------------------
# Automation, notifications, sync, audit
# ---------------------------------------------------------------------------


class AutomationJob(TimestampMixin, Base):
    __tablename__ = "automation_jobs"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(48), index=True)
    status: Mapped[JobStatus] = mapped_column(str_enum(JobStatus, "job_status"), default=JobStatus.QUEUED)
    dedupe_key: Mapped[str | None] = mapped_column(sa.String(160))
    payload: Mapped[dict[str, Any]] = mapped_column(default=dict)
    run_after: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    max_attempts: Mapped[int] = mapped_column(default=5)
    locked_by: Mapped[str | None] = mapped_column(sa.String(64))
    locked_until: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    finished_at: Mapped[datetime | None]

    __table_args__ = (
        sa.Index("ix_automation_jobs_pick", "status", "run_after"),
        # only one queued/running job per dedupe key
        sa.Index(
            "uq_automation_jobs_dedupe",
            "dedupe_key",
            unique=True,
            postgresql_where=sa.text("dedupe_key IS NOT NULL AND status IN ('queued','running')"),
        ),
    )


class AutomationLog(Base):
    __tablename__ = "automation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    feature: Mapped[str] = mapped_column(sa.String(48), index=True)
    action: Mapped[str] = mapped_column(sa.String(64))
    result: Mapped[LogResult] = mapped_column(str_enum(LogResult, "log_result"))
    message: Mapped[str] = mapped_column(sa.Text, default="")
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    order_id: Mapped[int | None] = mapped_column(sa.ForeignKey("orders.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(sa.String(48), index=True)
    severity: Mapped[Severity] = mapped_column(str_enum(Severity, "severity"), default=Severity.INFO)
    title: Mapped[str] = mapped_column(sa.String(200))
    body: Mapped[str] = mapped_column(sa.Text)
    buttons: Mapped[list[Any]] = mapped_column(default=list)  # [[{"text","callback_data"|"url"}]]
    entity_type: Mapped[str | None] = mapped_column(sa.String(32))
    entity_id: Mapped[int | None]
    chat_id: Mapped[int | None] = mapped_column(sa.BigInteger)
    status: Mapped[NotificationStatus] = mapped_column(
        str_enum(NotificationStatus, "notification_status"), default=NotificationStatus.PENDING, index=True
    )
    dedupe_key: Mapped[str | None] = mapped_column(sa.String(160), unique=True)
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(server_default=sa.func.now())
    last_error: Mapped[str | None] = mapped_column(sa.Text)
    sent_at: Mapped[datetime | None]
    read_at: Mapped[datetime | None]
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)


class SyncRun(Base):
    __tablename__ = "sync_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(sa.String(48), index=True)
    kind: Mapped[str] = mapped_column(sa.String(48))
    status: Mapped[SyncStatus] = mapped_column(str_enum(SyncStatus, "sync_status"), default=SyncStatus.RUNNING)
    started_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)
    finished_at: Mapped[datetime | None]
    records_received: Mapped[int] = mapped_column(default=0)
    records_saved: Mapped[int] = mapped_column(default=0)
    errors_count: Mapped[int] = mapped_column(default=0)
    message: Mapped[str] = mapped_column(sa.Text, default="")
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_type: Mapped[str] = mapped_column(sa.String(16))  # web | telegram | system | cli
    actor_id: Mapped[str | None] = mapped_column(sa.String(64))
    actor_name: Mapped[str | None] = mapped_column(sa.String(120))
    action: Mapped[str] = mapped_column(sa.String(64), index=True)
    entity_type: Mapped[str | None] = mapped_column(sa.String(32))
    entity_id: Mapped[str | None] = mapped_column(sa.String(64))
    ip: Mapped[str | None] = mapped_column(sa.String(64))
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.func.now(), index=True)


class Heartbeat(Base):
    __tablename__ = "heartbeats"

    service: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    instance: Mapped[str] = mapped_column(sa.String(64))
    started_at: Mapped[datetime]
    last_seen_at: Mapped[datetime]
    details: Mapped[dict[str, Any]] = mapped_column(default=dict)
