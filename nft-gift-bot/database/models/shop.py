"""Shop models: ShopProduct, ShopOrder, ShopOrderLog."""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Enum, ForeignKey, Integer,
    Numeric, String, Text, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database.base import Base


class ProductStatus(str, enum.Enum):
    DRAFT = "draft"          # created, pending admin verification
    ACTIVE = "active"        # verified + on sale
    INACTIVE = "inactive"    # temporarily hidden by admin
    SOLD_OUT = "sold_out"    # stock == 0
    DELETED = "deleted"      # soft-deleted, never shown


class DeliveryType(str, enum.Enum):
    MANUAL = "manual"               # admin delivers manually after order
    SECURE_TOKEN = "secure_token"   # encrypted payload released after payment


class OrderStatus(str, enum.Enum):
    PENDING = "pending"       # waiting for payment
    PAID = "paid"             # TON payment confirmed on-chain
    DELIVERED = "delivered"   # admin confirmed delivery
    CANCELLED = "cancelled"   # expired or cancelled before payment
    REFUNDED = "refunded"     # refunded by admin


class ShopProduct(Base):
    """
    Product in the account shop.

    A product MUST be admin-verified (is_verified=True) before it appears
    in the catalog. This is an architectural gate: without explicit admin
    confirmation of lawful ownership and transfer rights, status cannot
    be set to ACTIVE.

    Never store session files, phone numbers, or auth credentials in public
    fields. Use encrypted_delivery_info for any private payload.
    """
    __tablename__ = "shop_products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    price_ton: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=5.0)
    stock: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[ProductStatus] = mapped_column(
        Enum(ProductStatus), nullable=False, default=ProductStatus.DRAFT
    )
    delivery_type: Mapped[DeliveryType] = mapped_column(
        Enum(DeliveryType), nullable=False, default=DeliveryType.MANUAL
    )

    # Encrypted delivery payload (Fernet). Never expose in catalog or to buyer
    # before payment is confirmed.
    encrypted_delivery_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Origin verification gate — must be True before product goes ACTIVE
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    verified_by_admin_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verification_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by_admin_id: Mapped[int] = mapped_column(Integer, nullable=False)

    orders: Mapped[list["ShopOrder"]] = relationship(
        "ShopOrder", back_populates="product", lazy="noload"
    )


class ShopOrder(Base):
    """
    Purchase order. Payment must be confirmed on-chain before delivery.

    Double-spend prevention:
    - UNIQUE payment_comment — one pending comment per order
    - UNIQUE tx_hash — same tx cannot confirm two orders
    - SELECT FOR UPDATE used in shop_repo.get_by_comment_for_update()
    """
    __tablename__ = "shop_orders"
    __table_args__ = (
        UniqueConstraint("payment_comment", name="uq_shop_orders_payment_comment"),
        UniqueConstraint("tx_hash", name="uq_shop_orders_tx_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("shop_products.id", ondelete="RESTRICT"), nullable=False
    )
    payment_comment: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tx_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    amount_ton: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False)
    status: Mapped[OrderStatus] = mapped_column(
        Enum(OrderStatus), nullable=False, default=OrderStatus.PENDING
    )
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    product: Mapped["ShopProduct"] = relationship(
        "ShopProduct", back_populates="orders", lazy="joined"
    )
    logs: Mapped[list["ShopOrderLog"]] = relationship(
        "ShopOrderLog", back_populates="order", lazy="noload"
    )


class ShopOrderLog(Base):
    """Audit trail for each order status change."""
    __tablename__ = "shop_order_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("shop_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event: Mapped[str] = mapped_column(Text, nullable=False)

    order: Mapped["ShopOrder"] = relationship(
        "ShopOrder", back_populates="logs", lazy="noload"
    )
