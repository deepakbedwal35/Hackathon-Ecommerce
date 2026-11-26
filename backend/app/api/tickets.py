from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_customer
from app.core.errors import AppError
from app.models.enums import ActorType, EscalationDecision, SenderType, TicketStatus
from app.models.models import AuditEvent, Escalation, Message, Ticket, User
from app.schemas.tickets import (
    CustomerMessageCreate,
    CustomerMessageRead,
    CustomerTicketDetail,
    CustomerTicketListItem,
)
from app.services.access import get_ticket_for_user

router = APIRouter(tags=["Customer Tickets"])


def _compute_review_status(escalations: list[Escalation]) -> str | None:
    """Computes high-level customer-facing review status without leaking internal metadata."""
    if not escalations:
        return None
    for esc in escalations:
        if esc.decision == EscalationDecision.PENDING:
            return "Under review by our team"
        if esc.decision == EscalationDecision.MORE_INFO_REQUESTED:
            return "More information needed"
    for esc in escalations:
        if esc.decision in (EscalationDecision.APPROVED, EscalationDecision.REJECTED):
            return "Decision made"
    return None


@router.get("", response_model=list[CustomerTicketListItem])
def list_customer_tickets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """Lists all support tickets belonging to the authenticated customer."""
    stmt = (
        select(Ticket)
        .where(Ticket.customer_id == current_user.id)
        .options(selectinload(Ticket.escalations))
        .order_by(Ticket.created_at.desc())
    )
    tickets = db.scalars(stmt).all()
    return [
        CustomerTicketListItem(
            id=t.id,
            order_id=t.order_id,
            subject=t.subject,
            category=t.category,
            status=t.status,
            priority=t.priority,
            review_status=_compute_review_status(t.escalations),
            created_at=t.created_at,
            updated_at=t.updated_at,
        )
        for t in tickets
    ]


@router.get("/{ticket_id}", response_model=CustomerTicketDetail)
def get_customer_ticket(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """
    Fetches ticket detail for the authenticated customer.
    Includes customer-safe review status; strictly omits internal notes.
    """
    ticket = get_ticket_for_user(db, current_user, ticket_id)
    # Eager load escalations for review status computation
    db.refresh(ticket, ["escalations"])

    return CustomerTicketDetail(
        id=ticket.id,
        customer_id=ticket.customer_id,
        order_id=ticket.order_id,
        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        status=ticket.status,
        priority=ticket.priority,
        review_status=_compute_review_status(ticket.escalations),
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


@router.get("/{ticket_id}/messages", response_model=list[CustomerMessageRead])
def list_ticket_messages(
    ticket_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """
    Lists customer-visible messages for a ticket.
    Staff replies appear with sender_type='staff'. Internal notes are never returned.
    """
    ticket = get_ticket_for_user(db, current_user, ticket_id)
    stmt = (
        select(Message)
        .where(Message.ticket_id == ticket.id)
        .order_by(Message.created_at.asc())
    )
    return db.scalars(stmt).all()


@router.post("/{ticket_id}/messages", response_model=CustomerMessageRead, status_code=status.HTTP_201_CREATED)
def post_customer_message(
    ticket_id: uuid.UUID,
    payload: CustomerMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """
    Customer posts a reply to an existing support ticket.
    If an escalation was awaiting more information, automatically resets it to pending
    and re-opens the ticket for staff attention.
    """
    ticket = get_ticket_for_user(db, current_user, ticket_id)

    if ticket.status == TicketStatus.CLOSED:
        raise AppError(
            code="TICKET_CLOSED",
            message="Cannot add messages to a closed ticket.",
            status_code=409,
        )

    msg = Message(
        ticket_id=ticket.id,
        sender_type=SenderType.CUSTOMER,
        sender_id=current_user.id,
        content=payload.content.strip(),
    )
    db.add(msg)
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()

    # Customer-side hook: Check if an escalation on this ticket was awaiting info
    escalation = db.scalar(
        select(Escalation)
        .where(
            Escalation.ticket_id == ticket.id,
            Escalation.decision == EscalationDecision.MORE_INFO_REQUESTED,
        )
        .with_for_update()
    )

    if escalation:
        escalation.decision = EscalationDecision.PENDING
        ticket.status = TicketStatus.OPEN
        audit_esc = AuditEvent(
            actor_id=current_user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="escalation.customer_replied",
            entity_type="escalation",
            entity_id=escalation.id,
            audit_metadata={"ticket_id": str(ticket.id)},
        )
        db.add(audit_esc)

    audit_msg = AuditEvent(
        actor_id=current_user.id,
        actor_type=ActorType.CUSTOMER,
        event_type="ticket.message_added",
        entity_type="ticket",
        entity_id=ticket.id,
        audit_metadata={"message_id": str(msg.id)},
    )
    db.add(audit_msg)

    db.commit()
    db.refresh(msg)
    return msg
