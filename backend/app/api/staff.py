from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_staff
from app.models.enums import EscalationDecision, TicketCategory, TicketPriority, TicketStatus
from app.models.models import User
from app.schemas.refunds import RefundRead
from app.schemas.staff import (
    StaffEscalationAssign,
    StaffEscalationDecision,
    StaffEscalationDetail,
    StaffMessageCreate,
    StaffMessageRead,
    StaffNoteCreate,
    StaffNoteRead,
    StaffPaginatedEscalations,
    StaffPaginatedTickets,
    StaffTicketDetail,
    StaffTicketListItem,
    StaffTicketPatch,
)
from app.services.escalations import (
    assign_staff_escalation,
    decide_staff_escalation,
    get_staff_escalation_detail,
    list_staff_escalations,
)
from app.services.staff_tickets import (
    add_staff_ticket_message,
    add_staff_ticket_note,
    get_staff_ticket_detail,
    list_staff_ticket_notes,
    list_staff_tickets,
    patch_staff_ticket,
)

router = APIRouter(tags=["Staff"])


# ---------------------------------------------------------------------------
# Staff Tickets Endpoints
# ---------------------------------------------------------------------------

@router.get("/tickets", response_model=StaffPaginatedTickets)
def get_staff_tickets(
    status: TicketStatus | None = Query(None),
    priority: TicketPriority | None = Query(None),
    category: TicketCategory | None = Query(None),
    has_escalation: bool | None = Query(None),
    escalation_decision: EscalationDecision | None = Query(None),
    assigned_to: str | None = Query(None),
    created_from: datetime | None = Query(None),
    created_to: datetime | None = Query(None),
    q: str | None = Query(None),
    sort: str = Query("sla"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Lists support tickets for staff with multi-attribute filtering and SLA sorting."""
    return list_staff_tickets(
        db=db,
        current_user=current_user,
        status=status,
        priority=priority,
        category=category,
        has_escalation=has_escalation,
        escalation_decision=escalation_decision,
        assigned_to=assigned_to,
        created_from=created_from,
        created_to=created_to,
        q=q,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.get("/tickets/{ticket_id}", response_model=StaffTicketDetail)
def get_staff_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Fetches full contextual ticket detail in a single optimized query graph."""
    return get_staff_ticket_detail(db=db, ticket_id=ticket_id)


@router.patch("/tickets/{ticket_id}", response_model=StaffTicketListItem)
def patch_ticket(
    ticket_id: uuid.UUID,
    payload: StaffTicketPatch,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Updates ticket status/priority while enforcing valid transition invariants."""
    ticket = patch_staff_ticket(
        db=db,
        staff_user=current_user,
        ticket_id=ticket_id,
        status=payload.status,
        priority=payload.priority,
    )
    return StaffTicketListItem(
        id=ticket.id,
        subject=ticket.subject,
        category=ticket.category,
        status=ticket.status,
        priority=ticket.priority,
        customer_id=ticket.customer_id,
        customer_name=ticket.customer.name,
        order_id=ticket.order_id,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


@router.post("/tickets/{ticket_id}/messages", response_model=StaffMessageRead, status_code=status.HTTP_201_CREATED)
def post_staff_message(
    ticket_id: uuid.UUID,
    payload: StaffMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Posts an official, customer-visible reply from staff on a ticket."""
    return add_staff_ticket_message(
        db=db,
        staff_user=current_user,
        ticket_id=ticket_id,
        content=payload.content,
    )


@router.get("/tickets/{ticket_id}/notes", response_model=list[StaffNoteRead])
def get_ticket_notes(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Lists internal notes on a ticket. Strictly forbidden to customers."""
    notes = list_staff_ticket_notes(db=db, ticket_id=ticket_id)
    return [
        StaffNoteRead(
            id=n.id,
            ticket_id=n.ticket_id,
            author_id=n.author_id,
            author_name=n.author.name if n.author else "Staff",
            note=n.note,
            created_at=n.created_at,
        )
        for n in notes
    ]


@router.post("/tickets/{ticket_id}/notes", response_model=StaffNoteRead, status_code=status.HTTP_201_CREATED)
def post_ticket_note(
    ticket_id: uuid.UUID,
    payload: StaffNoteCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Appends an internal note visible only to support agents and admins."""
    note = add_staff_ticket_note(
        db=db,
        staff_user=current_user,
        ticket_id=ticket_id,
        note=payload.note,
    )
    return StaffNoteRead(
        id=note.id,
        ticket_id=note.ticket_id,
        author_id=note.author_id,
        author_name=current_user.name,
        note=note.note,
        created_at=note.created_at,
    )


# ---------------------------------------------------------------------------
# Staff Escalations Endpoints
# ---------------------------------------------------------------------------

@router.get("/escalations", response_model=StaffPaginatedEscalations)
def get_staff_escalations(
    decision: EscalationDecision | None = Query(None),
    priority: TicketPriority | None = Query(None),
    assigned_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Lists escalations pending review or information request."""
    return list_staff_escalations(
        db=db,
        current_user=current_user,
        decision=decision,
        priority=priority,
        assigned_to=assigned_to,
        page=page,
        page_size=page_size,
    )


@router.get("/escalations/{escalation_id}", response_model=StaffEscalationDetail)
def get_escalation(
    escalation_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Fetches full escalation context with verification checks and audit notes."""
    return get_staff_escalation_detail(db=db, escalation_id=escalation_id)


@router.post("/escalations/{escalation_id}/assign")
def assign_escalation(
    escalation_id: uuid.UUID,
    payload: StaffEscalationAssign,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """Assigns an escalation to self (default for agents) or to another staff member (admins only)."""
    esc = assign_staff_escalation(
        db=db,
        staff_user=current_user,
        escalation_id=escalation_id,
        assignee_id=payload.assignee_id,
    )
    return {"status": "ok", "escalation_id": str(esc.id), "assigned_to": str(esc.assigned_to)}


@router.post("/escalations/{escalation_id}/decision", response_model=RefundRead | None)
def record_escalation_decision(
    escalation_id: uuid.UUID,
    payload: StaffEscalationDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_staff),
):
    """
    Submits a staff decision (approve, reject, or request_info) on an escalation.
    Approval triggers the unified refund engine without bypassing banking rails.
    """
    refund = decide_staff_escalation(
        db=db,
        staff_user=current_user,
        escalation_id=escalation_id,
        decision=payload.decision,
        note=payload.note,
        message_to_customer=payload.message_to_customer,
    )
    return refund
