"""product country

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 18:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('products', sa.Column('country', sa.String(length=2), nullable=True))
    op.create_index(op.f('ix_products_country'), 'products', ['country'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_products_country'), table_name='products')
    op.drop_column('products', 'country')
