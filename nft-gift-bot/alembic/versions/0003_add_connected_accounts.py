"""Add connected_accounts table

Revision ID: 0003
Revises: 0002
Create Date: 2024-01-03 00:00:00.000000
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "connected_accounts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("phone", sa.String(32), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending_code", "pending_2fa", "connected", "error", "disconnected",
                name="accountstatus",
            ),
            nullable=False,
            server_default="pending_code",
        ),
        sa.Column("encrypted_session", sa.Text(), nullable=True),
        sa.Column("error_message", sa.String(256), nullable=True),
        sa.Column("connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", name="uq_connected_accounts_user_id"),
    )
    op.create_index("ix_connected_accounts_user_id", "connected_accounts", ["user_id"])
    op.create_index("ix_connected_accounts_status", "connected_accounts", ["status"])


def downgrade() -> None:
    op.drop_index("ix_connected_accounts_status", table_name="connected_accounts")
    op.drop_index("ix_connected_accounts_user_id", table_name="connected_accounts")
    op.drop_table("connected_accounts")
    op.execute("DROP TYPE IF EXISTS accountstatus")
