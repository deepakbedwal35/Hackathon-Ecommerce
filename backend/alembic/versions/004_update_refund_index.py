"""update_active_refund_index

Revision ID: 004
Revises: 003
Create Date: 2026-11-26 17:48:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '004'
down_revision: Union[str, None] = '003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop previous index that included 'processed'
    op.drop_index(
        'uq_refunds_one_active_per_order',
        table_name='refunds',
        postgresql_where=sa.text("status IN ('pending_review', 'approved', 'processed')")
    )
    # Re-create partial unique index only for active/in-flight statuses
    op.create_index(
        'uq_refunds_one_active_per_order',
        'refunds',
        ['order_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_review', 'approved')")
    )


def downgrade() -> None:
    op.drop_index(
        'uq_refunds_one_active_per_order',
        table_name='refunds',
        postgresql_where=sa.text("status IN ('pending_review', 'approved')")
    )
    op.create_index(
        'uq_refunds_one_active_per_order',
        'refunds',
        ['order_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_review', 'approved', 'processed')")
    )
