"""lucky buy

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-23 22:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

STATUSES = ("created", "pending_payment", "paid", "processing", "completed", "failed", "refund_pending", "refunded", "cancelled")


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def upgrade() -> None:
    op.add_column("orders", sa.Column("kind", sa.String(length=32), server_default="regular", nullable=False))
    op.create_check_constraint(op.f("ck_orders_order_kind"), "orders", _in("kind", ("regular", "lucky")))
    op.drop_constraint(op.f("ck_orders_order_status"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_order_status"), "orders", _in("status", (*STATUSES, "lost")))

    op.create_table(
        "lucky_draws",
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chance_bp", sa.Integer(), nullable=False),
        sa.Column("prize_value", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("prize_cost", sa.Numeric(precision=14, scale=2), nullable=True),
        sa.Column("server_seed", sa.String(length=64), nullable=False),
        sa.Column("server_seed_hash", sa.String(length=64), nullable=False),
        sa.Column("client_seed", sa.String(length=64), nullable=True),
        sa.Column("roll_bp", sa.Integer(), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("drawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("chance_bp BETWEEN 1 AND 9999", name=op.f("ck_lucky_draws_chance_range")),
        sa.CheckConstraint("roll_bp IS NULL OR roll_bp BETWEEN 0 AND 9999", name=op.f("ck_lucky_draws_roll_range")),
        sa.CheckConstraint(
            "(drawn_at IS NULL AND won IS NULL AND roll_bp IS NULL) OR "
            "(drawn_at IS NOT NULL AND won IS NOT NULL AND roll_bp IS NOT NULL AND client_seed IS NOT NULL)",
            name=op.f("ck_lucky_draws_draw_complete"),
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_lucky_draws_order_id_orders"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("order_id", name=op.f("pk_lucky_draws")),
    )


def downgrade() -> None:
    # Fails while 'lost' orders exist: they cannot be represented without Lucky Buy.
    op.drop_table("lucky_draws")
    op.drop_constraint(op.f("ck_orders_order_status"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_order_status"), "orders", _in("status", STATUSES))
    op.drop_constraint(op.f("ck_orders_order_kind"), "orders", type_="check")
    op.drop_column("orders", "kind")
