"""telegram premium, referral withdrawals

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-25 10:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_KIND_FIELDS = (
    "(kind = 'package' AND stars_amount > 0 AND price >= 0) OR "
    "(kind = 'custom' AND price_per_star > 0 AND min_stars > 0 AND max_stars >= min_stars)"
)
KIND_FIELDS = OLD_KIND_FIELDS + " OR (kind = 'premium' AND premium_months IN (3, 6, 12) AND price >= 0)"
ITEM_PRESENT = "(premium_months IS NULL AND stars_amount > 0) OR (premium_months IN (3, 6, 12) AND stars_amount = 0)"
# Starting prices of the DEMO catalog; the administrator changes them in the catalog.
PREMIUM = ((3, "1590.00", 101), (6, "2290.00", 102), (12, "3990.00", 103))


def _in(column: str, values: Sequence[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _replace_check(table: str, name: str, condition: str) -> None:
    op.drop_constraint(op.f(name), table, type_="check")
    op.create_check_constraint(op.f(name), table, condition)


def upgrade() -> None:
    op.add_column("products", sa.Column("premium_months", sa.SmallInteger(), nullable=True))
    op.add_column("products", sa.Column("cost_price", sa.Numeric(precision=14, scale=2), nullable=True))
    op.create_check_constraint(op.f("ck_products_cost_price_non_negative"), "products", "cost_price IS NULL OR cost_price >= 0")
    _replace_check("products", "ck_products_product_kind", _in("kind", ("package", "custom", "premium")))
    _replace_check("products", "ck_products_kind_fields", KIND_FIELDS)

    op.add_column("orders", sa.Column("premium_months", sa.SmallInteger(), nullable=True))
    _replace_check("orders", "ck_orders_order_product_kind", _in("product_kind", ("package", "custom", "premium")))
    _replace_check("orders", "ck_orders_order_kind", _in("kind", ("regular", "lucky", "withdrawal")))
    op.drop_constraint(op.f("ck_orders_stars_positive"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_item_present"), "orders", ITEM_PRESENT)

    op.create_table(
        "withdrawals",
        sa.Column("id", sa.Integer(), sa.Identity(always=False), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("stars", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.Column("rate", sa.Numeric(precision=14, scale=4), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "approved",
                "rejected",
                "returned",
                name="withdrawal_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("recipient_username", sa.String(length=64), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("decided_by", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("comment", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("stars > 0 AND amount > 0 AND rate > 0", name=op.f("ck_withdrawals_positive")),
        sa.ForeignKeyConstraint(
            ["decided_by"], ["admin_users.id"], name=op.f("fk_withdrawals_decided_by_admin_users"), ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], name=op.f("fk_withdrawals_order_id_orders"), ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name=op.f("fk_withdrawals_user_id_users"), ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_withdrawals")),
    )
    op.create_index("ix_withdrawals_status_created", "withdrawals", ["status", "created_at"], unique=False)
    op.create_index("ix_withdrawals_user_created", "withdrawals", ["user_id", "created_at"], unique=False)
    op.create_index("uq_withdrawals_one_pending", "withdrawals", ["user_id"], unique=True, postgresql_where=sa.text("status = 'pending'"))

    # Telegram Premium in an existing catalog (a new database gets it from the seed).
    op.execute(
        sa.text(
            "INSERT INTO products (kind, premium_months, price, sort_order, is_active, is_popular, is_archived) "
            "SELECT 'premium', m, p, s, true, false, false FROM (VALUES "
            + ", ".join(f"({m}, {p}::numeric, {s})" for m, p, s in PREMIUM)
            + ") AS v(m, p, s) WHERE EXISTS (SELECT 1 FROM products) AND NOT EXISTS (SELECT 1 FROM products WHERE kind = 'premium')"
        )
    )


def downgrade() -> None:
    # Fails while Premium or withdrawal orders exist: they cannot be represented without this revision.
    op.execute("DELETE FROM products WHERE kind = 'premium'")
    op.drop_index("uq_withdrawals_one_pending", table_name="withdrawals", postgresql_where=sa.text("status = 'pending'"))
    op.drop_index("ix_withdrawals_user_created", table_name="withdrawals")
    op.drop_index("ix_withdrawals_status_created", table_name="withdrawals")
    op.drop_table("withdrawals")
    op.drop_constraint(op.f("ck_orders_item_present"), "orders", type_="check")
    op.create_check_constraint(op.f("ck_orders_stars_positive"), "orders", "stars_amount > 0")
    _replace_check("orders", "ck_orders_order_kind", _in("kind", ("regular", "lucky")))
    _replace_check("orders", "ck_orders_order_product_kind", _in("product_kind", ("package", "custom")))
    op.drop_column("orders", "premium_months")
    _replace_check("products", "ck_products_kind_fields", OLD_KIND_FIELDS)
    _replace_check("products", "ck_products_product_kind", _in("kind", ("package", "custom")))
    op.drop_constraint(op.f("ck_products_cost_price_non_negative"), "products", type_="check")
    op.drop_column("products", "cost_price")
    op.drop_column("products", "premium_months")
