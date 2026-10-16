"""Initial schema: users, subscriptions, gifts, transactions

Revision ID: 0001
Revises:
Create Date: 2024-01-01 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(128), nullable=False),
        sa.Column("last_name", sa.String(128), nullable=True),
        sa.Column("language_code", sa.String(8), nullable=True),
        sa.Column("is_bot", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_telegram_id", "users", ["telegram_id"], unique=True)

    # ── subscriptions ──────────────────────────────────────────────────────
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("plan", sa.Enum("basic", "premium", name="subscriptionplan"), nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "expired", "cancelled", "pending", name="subscriptionstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("price_paid", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False, server_default="XTR"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_subscriptions_user_id", "subscriptions", ["user_id"])
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_expires_at", "subscriptions", ["expires_at"])

    # ── gifts ──────────────────────────────────────────────────────────────
    op.create_table(
        "gifts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=True),
        sa.Column("telegram_gift_id", sa.String(256), nullable=True),
        sa.Column("name", sa.String(256), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(512), nullable=True),
        sa.Column("sticker_file_id", sa.String(256), nullable=True),
        sa.Column(
            "rarity",
            sa.Enum("common", "rare", "epic", "legendary", name="giftrarity"),
            nullable=False,
            server_default="common",
        ),
        sa.Column(
            "status",
            sa.Enum("owned", "transferred", "burned", name="giftstatus"),
            nullable=False,
            server_default="owned",
        ),
        sa.Column("is_transferable", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("is_limited", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("total_supply", sa.Integer(), nullable=True),
        sa.Column("serial_number", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gifts_owner_id", "gifts", ["owner_id"])
    op.create_index("ix_gifts_telegram_gift_id", "gifts", ["telegram_gift_id"], unique=True)
    op.create_index("ix_gifts_status", "gifts", ["status"])

    # ── transactions ───────────────────────────────────────────────────────
    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "type",
            sa.Enum(
                "subscription_purchase", "subscription_renewal",
                "gift_purchase", "gift_transfer", "refund",
                name="transactiontype",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum("pending", "completed", "failed", "refunded", name="transactionstatus"),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "provider",
            sa.Enum("telegram_stars", "crypto_bot", "internal", name="paymentprovider"),
            nullable=False,
        ),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("currency", sa.String(8), nullable=False),
        sa.Column("provider_payment_id", sa.String(256), nullable=True),
        sa.Column("provider_charge_id", sa.String(256), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("gift_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["gift_id"], ["gifts.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transactions_user_id", "transactions", ["user_id"])
    op.create_index("ix_transactions_status", "transactions", ["status"])
    op.create_index(
        "ix_transactions_provider_payment_id", "transactions",
        ["provider_payment_id"], unique=True
    )


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("gifts")
    op.drop_table("subscriptions")
    op.drop_table("users")

    op.execute("DROP TYPE IF EXISTS transactionstatus")
    op.execute("DROP TYPE IF EXISTS transactiontype")
    op.execute("DROP TYPE IF EXISTS paymentprovider")
    op.execute("DROP TYPE IF EXISTS giftstatus")
    op.execute("DROP TYPE IF EXISTS giftrarity")
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
    op.execute("DROP TYPE IF EXISTS subscriptionplan")
