"""add_order_number

Revision ID: 003
Revises: 002
Create Date: 2026-11-26 17:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'orders',
        sa.Column('order_number', sa.String(length=50), nullable=True)
    )
    # Backfill any existing orders without order_number
    op.execute(
        "UPDATE orders SET order_number = 'ORD-' || SUBSTRING(id::text, 1, 8) WHERE order_number IS NULL"
    )
    op.alter_column('orders', 'order_number', nullable=False)
    op.create_index('ix_orders_order_number', 'orders', ['order_number'], unique=True)


def downgrade() -> None:
    op.drop_index('ix_orders_order_number', table_name='orders')
    op.drop_column('orders', 'order_number')
