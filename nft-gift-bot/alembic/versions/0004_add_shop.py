"""Add shop tables: shop_products, shop_orders, shop_order_logs

Revision ID: 0004
Revises: 0003
Create Date: 2024-01-04 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # product_status enum
    op.execute(
        "CREATE TYPE productstatus AS ENUM "
        "('draft', 'active', 'inactive', 'sold_out', 'deleted')"
    )
    # delivery_type enum
    op.execute(
        "CREATE TYPE deliverytype AS ENUM ('manual', 'secure_token')"
    )
    # order_status enum
    op.execute(
        "CREATE TYPE orderstatus AS ENUM "
        "('pending', 'paid', 'delivered', 'cancelled', 'refunded')"
    )

    op.create_table(
        "shop_products",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("price_ton", sa.Numeric(12, 4), nullable=False, server_default="5.0"),
        sa.Column("stock", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status",
            sa.Enum("draft", "active", "inactive", "sold_out", "deleted", name="productstatus"),
            nullable=False,
            server_default="draft",
        ),
        sa.Column(
            "delivery_type",
            sa.Enum("manual", "secure_token", name="deliverytype"),
            nullable=False,
            server_default="manual",
        ),
        sa.Column("encrypted_delivery_info", sa.Text(), nullable=True),
        sa.Column("is_verified", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("verified_by_admin_id", sa.Integer(), nullable=True),
        sa.Column("verification_note", sa.Text(), nullable=True),
        sa.Column("created_by_admin_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_shop_products_status", "shop_products", ["status"])

    op.create_table(
        "shop_orders",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.Integer(),
            sa.ForeignKey("shop_products.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("payment_comment", sa.String(32), nullable=False),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column("amount_ton", sa.Numeric(12, 4), nullable=False),
        sa.Column(
            "status",
            sa.Enum("pending", "paid", "delivered", "cancelled", "refunded", name="orderstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("payment_comment", name="uq_shop_orders_payment_comment"),
        sa.UniqueConstraint("tx_hash", name="uq_shop_orders_tx_hash"),
    )
    op.create_index("ix_shop_orders_user_id", "shop_orders", ["user_id"])
    op.create_index("ix_shop_orders_payment_comment", "shop_orders", ["payment_comment"])
    op.create_index("ix_shop_orders_status", "shop_orders", ["status"])

    op.create_table(
        "shop_order_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("shop_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_shop_order_logs_order_id", "shop_order_logs", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_shop_order_logs_order_id", table_name="shop_order_logs")
    op.drop_table("shop_order_logs")

    op.drop_index("ix_shop_orders_status", table_name="shop_orders")
    op.drop_index("ix_shop_orders_payment_comment", table_name="shop_orders")
    op.drop_index("ix_shop_orders_user_id", table_name="shop_orders")
    op.drop_table("shop_orders")

    op.drop_index("ix_shop_products_status", table_name="shop_products")
    op.drop_table("shop_products")

    op.execute("DROP TYPE IF EXISTS orderstatus")
    op.execute("DROP TYPE IF EXISTS deliverytype")
    op.execute("DROP TYPE IF EXISTS productstatus")
