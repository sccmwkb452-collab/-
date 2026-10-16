"""Add ton_payments and bot_settings tables

Revision ID: 0002
Revises: 0001
Create Date: 2024-01-02 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── ton_payments ──────────────────────────────────────────────────────────
    op.create_table(
        "ton_payments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("subscription_id", sa.Integer(), nullable=True),
        sa.Column("payment_comment", sa.String(32), nullable=False),
        sa.Column("tx_hash", sa.String(128), nullable=True),
        sa.Column("amount_nanoton", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "confirmed", "expired", "failed", "duplicate",
                name="tonpaymentstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscription_id"], ["subscriptions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("payment_comment", name="uq_ton_payments_comment"),
        sa.UniqueConstraint("tx_hash", name="uq_ton_payments_tx_hash"),
    )
    op.create_index("ix_ton_payments_user_id", "ton_payments", ["user_id"])
    op.create_index("ix_ton_payments_status", "ton_payments", ["status"])
    op.create_index("ix_ton_payments_expires_at", "ton_payments", ["expires_at"])

    # ── bot_settings ──────────────────────────────────────────────────────────
    op.create_table(
        "bot_settings",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("bot_settings")
    op.drop_index("ix_ton_payments_expires_at", table_name="ton_payments")
    op.drop_index("ix_ton_payments_status", table_name="ton_payments")
    op.drop_index("ix_ton_payments_user_id", table_name="ton_payments")
    op.drop_table("ton_payments")
    op.execute("DROP TYPE IF EXISTS tonpaymentstatus")
