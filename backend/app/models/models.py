from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
import uuid

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.models.base import Base, TimestampMixin, TimestampUpdateMixin, UUIDPrimaryKeyMixin
from app.models.enums import (
    ActorType,
    EscalationDecision,
    ItemCategory,
    OrderStatus,
    RefundStatus,
    SenderType,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    UserRole,
)


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "users"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )

    # Relationships
    orders: Mapped[list["Order"]] = relationship(
        "Order", back_populates="customer", passive_deletes="all"
    )
    tickets: Mapped[list["Ticket"]] = relationship(
        "Ticket", back_populates="customer", passive_deletes="all"
    )

    __table_args__ = (
        Index("ix_users_email", func.lower(text("email")), unique=True),
    )

    @validates("email")
    def validate_email(self, key: str, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Email cannot be empty")
        return value.strip().lower()


class Order(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "orders"

    order_number: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        unique=True,
        index=True,
        default=lambda: f"ORD-{uuid.uuid4().hex[:8].upper()}",
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_orders_customer_id_users"),
        nullable=False,
    )
    status: Mapped[OrderStatus] = mapped_column(
        Enum(
            OrderStatus,
            name="order_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=OrderStatus.PLACED,
    )
    delivery_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relationships
    customer: Mapped["User"] = relationship("User", back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    refunds: Mapped[list["Refund"]] = relationship(
        "Refund", back_populates="order", passive_deletes="all"
    )
    tickets: Mapped[list["Ticket"]] = relationship("Ticket", back_populates="order")

    __table_args__ = (
        CheckConstraint("total_amount >= 0", name="ck_orders_total_amount_positive"),
        Index("ix_orders_customer_id_created_at", "customer_id", text("created_at DESC")),
    )


class OrderItem(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "order_items"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "orders.id", ondelete="CASCADE", name="fk_order_items_order_id_orders"
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[ItemCategory] = mapped_column(
        Enum(
            ItemCategory,
            name="item_category",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="items")

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_order_items_unit_price_positive"),
    )


class Ticket(Base, UUIDPrimaryKeyMixin, TimestampUpdateMixin):
    __tablename__ = "tickets"

    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT", name="fk_tickets_customer_id_users"),
        nullable=False,
    )
    order_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orders.id", ondelete="SET NULL", name="fk_tickets_order_id_orders"),
        nullable=True,
    )
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[TicketCategory] = mapped_column(
        Enum(
            TicketCategory,
            name="ticket_category",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    status: Mapped[TicketStatus] = mapped_column(
        Enum(
            TicketStatus,
            name="ticket_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TicketStatus.OPEN,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(
            TicketPriority,
            name="ticket_priority",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=TicketPriority.MEDIUM,
    )

    # Relationships
    customer: Mapped["User"] = relationship("User", back_populates="tickets")
    order: Mapped["Order | None"] = relationship("Order", back_populates="tickets")
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="ticket", cascade="all, delete-orphan"
    )
    notes: Mapped[list["TicketNote"]] = relationship(
        "TicketNote", back_populates="ticket", cascade="all, delete-orphan"
    )
    escalations: Mapped[list["Escalation"]] = relationship(
        "Escalation", back_populates="ticket"
    )
    refunds: Mapped[list["Refund"]] = relationship(
        "Refund", back_populates="ticket"
    )

    __table_args__ = (
        Index("ix_tickets_customer_id_status", "customer_id", "status"),
        Index("ix_tickets_status_priority", "status", "priority"),
    )


class Message(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "messages"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tickets.id", ondelete="CASCADE", name="fk_messages_ticket_id_tickets"
        ),
        nullable=False,
    )
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(
            SenderType,
            name="sender_type",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    sender_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL", name="fk_messages_sender_id_users"),
        nullable=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="messages")
    sender: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        Index("ix_messages_ticket_id_created_at", "ticket_id", "created_at"),
    )


class Refund(Base, UUIDPrimaryKeyMixin, TimestampUpdateMixin):
    __tablename__ = "refunds"

    order_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "orders.id", ondelete="RESTRICT", name="fk_refunds_order_id_orders"
        ),
        nullable=False,
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tickets.id", ondelete="SET NULL", name="fk_refunds_ticket_id_tickets"
        ),
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[RefundStatus] = mapped_column(
        Enum(
            RefundStatus,
            name="refund_status",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=RefundStatus.PENDING_REVIEW,
    )
    requested_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="RESTRICT", name="fk_refunds_requested_by_users"
        ),
        nullable=False,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="RESTRICT", name="fk_refunds_reviewed_by_users"
        ),
        nullable=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False
    )
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    order: Mapped["Order"] = relationship("Order", back_populates="refunds")
    ticket: Mapped["Ticket | None"] = relationship("Ticket", back_populates="refunds")
    requester: Mapped["User"] = relationship("User", foreign_keys=[requested_by])
    reviewer: Mapped["User | None"] = relationship("User", foreign_keys=[reviewed_by])
    escalations: Mapped[list["Escalation"]] = relationship(
        "Escalation", back_populates="refund"
    )

    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_refunds_amount_positive"),
        Index("ix_refunds_order_id", "order_id"),
        Index("ix_refunds_status", "status"),
        Index(
            "uq_refunds_one_active_per_order",
            "order_id",
            unique=True,
            postgresql_where=text(
                "status IN ('pending_review', 'approved')"
            ),
        ),
    )


class Escalation(Base, UUIDPrimaryKeyMixin):
    __tablename__ = "escalations"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tickets.id", ondelete="RESTRICT", name="fk_escalations_ticket_id_tickets"
        ),
        nullable=False,
    )
    refund_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "refunds.id", ondelete="RESTRICT", name="fk_escalations_refund_id_refunds"
        ),
        nullable=True,
    )
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(
            TicketPriority,
            name="ticket_priority",
            native_enum=True,
            create_type=False,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    assigned_to: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="RESTRICT", name="fk_escalations_assigned_to_users"
        ),
        nullable=True,
    )
    decision: Mapped[EscalationDecision] = mapped_column(
        Enum(
            EscalationDecision,
            name="escalation_decision",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=EscalationDecision.PENDING,
    )
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=text("now()"),
        nullable=False,
    )
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="escalations")
    refund: Mapped["Refund | None"] = relationship(
        "Refund", back_populates="escalations"
    )
    assignee: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        Index("ix_escalations_decision", "decision"),
    )


class TicketNote(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ticket_notes"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "tickets.id", ondelete="CASCADE", name="fk_ticket_notes_ticket_id_tickets"
        ),
        nullable=False,
    )
    author_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="RESTRICT", name="fk_ticket_notes_author_id_users"
        ),
        nullable=False,
    )
    note: Mapped[str] = mapped_column(Text, nullable=False)

    # Relationships
    ticket: Mapped["Ticket"] = relationship("Ticket", back_populates="notes")
    author: Mapped["User"] = relationship("User")


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """
    Append-only audit log capturing critical events across the platform.
    Never update or delete records from this table.
    """

    __tablename__ = "audit_events"

    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id", ondelete="SET NULL", name="fk_audit_events_actor_id_users"
        ),
        nullable=True,
    )
    actor_type: Mapped[ActorType] = mapped_column(
        Enum(
            ActorType,
            name="actor_type",
            native_enum=True,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # Mapped to database column "metadata" while avoiding python collision with Base.metadata
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata",
        JSONB,
        server_default=text("'{}'::jsonb"),
        nullable=False,
        default=dict,
    )
    request_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    actor: Mapped["User | None"] = relationship("User")

    __table_args__ = (
        Index("ix_audit_events_entity_type_entity_id", "entity_type", "entity_id"),
        Index("ix_audit_events_event_type_created_at", "event_type", "created_at"),
        {"comment": "Append-only audit log of critical system, user, and agent actions."},
    )
