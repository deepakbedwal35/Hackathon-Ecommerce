from datetime import date, datetime
from decimal import Decimal
from typing import Literal
import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import (
    EscalationDecision,
    ItemCategory,
    OrderStatus,
    RefundStatus,
    SenderType,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)


class StaffTicketRefundSummary(BaseModel):
    id: uuid.UUID
    amount: Decimal
    status: RefundStatus

    model_config = ConfigDict(from_attributes=True)


class StaffTicketListItem(BaseModel):
    id: uuid.UUID
    subject: str
    category: TicketCategory
    status: TicketStatus
    priority: TicketPriority
    customer_id: uuid.UUID
    customer_name: str
    order_id: uuid.UUID | None = None
    order_number: str | None = None
    refund_summary: StaffTicketRefundSummary | None = None
    has_pending_escalation: bool = False
    awaiting_admin_approval: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffPaginatedTickets(BaseModel):
    items: list[StaffTicketListItem]
    page: int
    page_size: int
    total: int


class StaffCustomerSummary(BaseModel):
    id: uuid.UUID
    name: str
    email: str

    model_config = ConfigDict(from_attributes=True)


class StaffOrderItemRead(BaseModel):
    id: uuid.UUID
    name: str
    category: ItemCategory
    quantity: int
    unit_price: Decimal

    model_config = ConfigDict(from_attributes=True)


class StaffOrderReturnWindow(BaseModel):
    return_window_days: int
    is_returnable: bool
    last_eligible_date: date | None = None


class StaffOrderRead(BaseModel):
    id: uuid.UUID
    order_number: str | None = None
    status: OrderStatus
    total_amount: Decimal
    delivery_date: date | None = None
    return_window: StaffOrderReturnWindow
    items: list[StaffOrderItemRead] = []

    model_config = ConfigDict(from_attributes=True)


class StaffRefundRead(BaseModel):
    id: uuid.UUID
    order_id: uuid.UUID
    ticket_id: uuid.UUID | None = None
    amount: Decimal
    reason: str
    status: RefundStatus
    payment_reference: str | None = None
    failure_reason: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffEscalationSummary(BaseModel):
    id: uuid.UUID
    refund_id: uuid.UUID | None = None
    summary: str
    priority: TicketPriority
    decision: EscalationDecision
    assigned_to: uuid.UUID | None = None
    internal_note: str | None = None
    created_at: datetime
    decided_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class StaffMessageRead(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    sender_type: SenderType
    sender_id: uuid.UUID | None = None
    content: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffNoteRead(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    author_name: str
    note: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffTicketInfo(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    order_id: uuid.UUID | None = None
    subject: str
    description: str
    category: TicketCategory
    status: TicketStatus
    priority: TicketPriority
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffTicketDetail(BaseModel):
    ticket: StaffTicketInfo
    customer: StaffCustomerSummary
    order: StaffOrderRead | None = None
    refunds: list[StaffRefundRead] = []
    escalations: list[StaffEscalationSummary] = []
    messages: list[StaffMessageRead] = []
    notes: list[StaffNoteRead] = []
    awaiting_admin_approval: bool = False
    allowed_transitions: list[TicketStatus] = []


class StaffTicketPatch(BaseModel):
    status: TicketStatus | None = None
    priority: TicketPriority | None = None

    model_config = ConfigDict(extra="forbid")


class StaffMessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")


class StaffNoteCreate(BaseModel):
    note: str = Field(min_length=1, max_length=4000)

    model_config = ConfigDict(extra="forbid")


# Escalation Schemas
class StaffEscalationListItem(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    ticket_subject: str
    customer_id: uuid.UUID
    customer_name: str
    order_id: uuid.UUID | None = None
    order_number: str | None = None
    amount: Decimal | None = None
    priority: TicketPriority
    decision: EscalationDecision
    assigned_to: uuid.UUID | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffPaginatedEscalations(BaseModel):
    items: list[StaffEscalationListItem]
    page: int
    page_size: int
    total: int


class StaffEscalationDetail(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    refund_id: uuid.UUID | None = None
    summary: str
    priority: TicketPriority
    decision: EscalationDecision
    assigned_to: uuid.UUID | None = None
    internal_note: str | None = None
    created_at: datetime
    decided_at: datetime | None = None
    checks_passed: list[str] = []
    ticket: StaffTicketInfo
    order: StaffOrderRead | None = None
    refund: StaffRefundRead | None = None
    messages: list[StaffMessageRead] = []
    notes: list[StaffNoteRead] = []


class StaffEscalationAssign(BaseModel):
    assignee_id: uuid.UUID | None = None

    model_config = ConfigDict(extra="forbid")


class StaffEscalationDecision(BaseModel):
    decision: Literal["approve", "reject", "request_info"]
    note: str = Field(min_length=5)
    message_to_customer: str | None = None

    model_config = ConfigDict(extra="forbid")


class StaffPendingApprovalItem(BaseModel):
    escalation_id: uuid.UUID
    ticket_id: uuid.UUID | None = None
    order_id: uuid.UUID | None = None
    order_number: str | None = None
    customer_name: str
    amount: Decimal
    priority: TicketPriority
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffRecentTicketItem(BaseModel):
    ticket_id: uuid.UUID
    subject: str
    customer_name: str
    status: TicketStatus
    priority: TicketPriority
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class StaffOverviewRead(BaseModel):
    ticket_counts: dict[str, int]
    awaiting_approval_count: int
    unassigned_count: int
    oldest_pending_approval_created_at: datetime | None = None
    pending_refund_total: Decimal = Decimal("0.00")
    top_5_pending_approvals: list[StaffPendingApprovalItem] = []
    top_5_recent_tickets: list[StaffRecentTicketItem] = []
