"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2026-11-26 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Users
    op.create_table(
        'users',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('role', sa.Enum('customer', 'agent', 'admin', name='user_role'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users'))
    )
    op.create_index('ix_users_email', 'users', [sa.literal_column('lower(email)')], unique=True)

    # Audit Events
    op.create_table(
        'audit_events',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('actor_id', sa.UUID(), nullable=True),
        sa.Column('actor_type', sa.Enum('customer', 'staff', 'ai_agent', 'system', name='actor_type'), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('entity_type', sa.String(length=100), nullable=False),
        sa.Column('entity_id', sa.UUID(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column('request_id', sa.String(length=255), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id'], name=op.f('fk_audit_events_actor_id_users'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_events')),
        comment='Append-only audit log of critical system, user, and agent actions.'
    )
    op.create_index('ix_audit_events_entity_type_entity_id', 'audit_events', ['entity_type', 'entity_id'], unique=False)
    op.create_index('ix_audit_events_event_type_created_at', 'audit_events', ['event_type', 'created_at'], unique=False)

    # Orders
    op.create_table(
        'orders',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('status', sa.Enum('placed', 'shipped', 'delivered', 'cancelled', name='order_status'), nullable=False),
        sa.Column('delivery_date', sa.Date(), nullable=True),
        sa.Column('total_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('total_amount >= 0', name=op.f('ck_orders_total_amount_positive')),
        sa.ForeignKeyConstraint(['customer_id'], ['users.id'], name=op.f('fk_orders_customer_id_users'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_orders'))
    )
    op.create_index('ix_orders_customer_id_created_at', 'orders', ['customer_id', sa.literal_column('created_at DESC')], unique=False)

    # Order Items
    op.create_table(
        'order_items',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('category', sa.Enum('electronics', 'fashion', 'grocery', 'home', 'beauty', 'books', name='item_category'), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.CheckConstraint('quantity > 0', name=op.f('ck_order_items_quantity_positive')),
        sa.CheckConstraint('unit_price >= 0', name=op.f('ck_order_items_unit_price_positive')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_order_items_order_id_orders'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_order_items'))
    )

    # Tickets
    op.create_table(
        'tickets',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('category', sa.Enum('order_issue', 'refund', 'delivery', 'payment', 'product', 'other', name='ticket_category'), nullable=False),
        sa.Column('status', sa.Enum('open', 'awaiting_customer', 'escalated', 'resolved', 'closed', name='ticket_status'), nullable=False),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', 'urgent', name='ticket_priority'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['customer_id'], ['users.id'], name=op.f('fk_tickets_customer_id_users'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_tickets_order_id_orders'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_tickets'))
    )
    op.create_index('ix_tickets_customer_id_status', 'tickets', ['customer_id', 'status'], unique=False)
    op.create_index('ix_tickets_status_priority', 'tickets', ['status', 'priority'], unique=False)

    # Messages
    op.create_table(
        'messages',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('sender_type', sa.Enum('customer', 'agent_ai', 'staff', 'system', name='sender_type'), nullable=False),
        sa.Column('sender_id', sa.UUID(), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['sender_id'], ['users.id'], name=op.f('fk_messages_sender_id_users'), ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name=op.f('fk_messages_ticket_id_tickets'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index('ix_messages_ticket_id_created_at', 'messages', ['ticket_id', 'created_at'], unique=False)

    # Refunds
    op.create_table(
        'refunds',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('order_id', sa.UUID(), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('status', sa.Enum('pending_review', 'approved', 'rejected', 'processed', 'failed', name='refund_status'), nullable=False),
        sa.Column('requested_by', sa.UUID(), nullable=False),
        sa.Column('reviewed_by', sa.UUID(), nullable=True),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('failure_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('amount > 0', name=op.f('ck_refunds_amount_positive')),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], name=op.f('fk_refunds_order_id_orders'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['requested_by'], ['users.id'], name=op.f('fk_refunds_requested_by_users'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], name=op.f('fk_refunds_reviewed_by_users'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name=op.f('fk_refunds_ticket_id_tickets'), ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_refunds')),
        sa.UniqueConstraint('idempotency_key', name=op.f('uq_refunds_idempotency_key'))
    )
    op.create_index('ix_refunds_order_id', 'refunds', ['order_id'], unique=False)
    op.create_index('ix_refunds_status', 'refunds', ['status'], unique=False)
    op.create_index(
        'uq_refunds_one_active_per_order',
        'refunds',
        ['order_id'],
        unique=True,
        postgresql_where=sa.text("status IN ('pending_review', 'approved', 'processed')")
    )

    # Ticket Notes
    op.create_table(
        'ticket_notes',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('author_id', sa.UUID(), nullable=False),
        sa.Column('note', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id'], name=op.f('fk_ticket_notes_author_id_users'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name=op.f('fk_ticket_notes_ticket_id_tickets'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_ticket_notes'))
    )

    # Escalations
    op.create_table(
        'escalations',
        sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('ticket_id', sa.UUID(), nullable=False),
        sa.Column('refund_id', sa.UUID(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('priority', sa.Enum('low', 'medium', 'high', 'urgent', name='ticket_priority'), nullable=False),
        sa.Column('assigned_to', sa.UUID(), nullable=True),
        sa.Column('decision', sa.Enum('pending', 'approved', 'rejected', 'more_info_requested', name='escalation_decision'), nullable=False),
        sa.Column('internal_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], name=op.f('fk_escalations_assigned_to_users'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['refund_id'], ['refunds.id'], name=op.f('fk_escalations_refund_id_refunds'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['ticket_id'], ['tickets.id'], name=op.f('fk_escalations_ticket_id_tickets'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_escalations'))
    )
    op.create_index('ix_escalations_decision', 'escalations', ['decision'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_escalations_decision', table_name='escalations')
    op.drop_table('escalations')
    op.drop_table('ticket_notes')
    op.drop_index('uq_refunds_one_active_per_order', table_name='refunds', postgresql_where=sa.text("status IN ('pending_review', 'approved', 'processed')"))
    op.drop_index('ix_refunds_status', table_name='refunds')
    op.drop_index('ix_refunds_order_id', table_name='refunds')
    op.drop_table('refunds')
    op.drop_index('ix_messages_ticket_id_created_at', table_name='messages')
    op.drop_table('messages')
    op.drop_index('ix_tickets_status_priority', table_name='tickets')
    op.drop_index('ix_tickets_customer_id_status', table_name='tickets')
    op.drop_table('tickets')
    op.drop_table('order_items')
    op.drop_index('ix_orders_customer_id_created_at', table_name='orders')
    op.drop_table('orders')
    op.drop_index('ix_audit_events_event_type_created_at', table_name='audit_events')
    op.drop_index('ix_audit_events_entity_type_entity_id', table_name='audit_events')
    op.drop_table('audit_events')
    op.drop_index('ix_users_email', table_name='users')
    op.drop_table('users')

    # Drop all native Postgres enums cleanly
    for enum_name in [
        'escalation_decision',
        'refund_status',
        'sender_type',
        'ticket_priority',
        'ticket_status',
        'ticket_category',
        'item_category',
        'order_status',
        'actor_type',
        'user_role',
    ]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name} CASCADE")
