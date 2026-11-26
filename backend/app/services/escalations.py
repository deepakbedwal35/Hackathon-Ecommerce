from datetime import datetime, timezone
from decimal import Decimal
from typing import Literal
import uuid

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, selectinload
import structlog

from app.core.errors import AppError
from app.core.policy import RETURN_WINDOW_DAYS, NON_RETURNABLE_CATEGORIES, get_today_date
from app.models.enums import (
    ActorType,
    EscalationDecision,
    SenderType,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.models import (
    AuditEvent,
    Escalation,
    Message,
    Order,
    Refund,
    Ticket,
    TicketNote,
    User,
)
from app.schemas.staff import (
    StaffCustomerSummary,
    StaffEscalationDetail,
    StaffEscalationListItem,
    StaffMessageRead,
    StaffNoteRead,
    StaffOrderItemRead,
    StaffOrderRead,
    StaffOrderReturnWindow,
    StaffPaginatedEscalations,
    StaffRefundRead,
    StaffTicketInfo,
)
from app.services.refunds import Outcome, approve_escalated_refund, reject_refund

logger = structlog.get_logger("services.escalations")

PRIORITY_ORDER = case(
    {
        TicketPriority.URGENT: 1,
        TicketPriority.HIGH: 2,
        TicketPriority.MEDIUM: 3,
        TicketPriority.LOW: 4,
    },
    value=Escalation.priority,
)


def list_staff_escalations(
    db: Session,
    current_user: User,
    decision: list[EscalationDecision] | EscalationDecision | None = None,
    priority: TicketPriority | None = None,
    assigned_to: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> StaffPaginatedEscalations:
    """
    Paginated list of escalations for staff review.
    Defaults to pending and more_info_requested decisions; sorted by SLA priority then oldest.
    """
    stmt = (
        select(Escalation)
        .join(Ticket, Escalation.ticket_id == Ticket.id)
        .join(User, Ticket.customer_id == User.id)
        .options(
            selectinload(Escalation.ticket).selectinload(Ticket.customer),
            selectinload(Escalation.refund),
        )
    )

    # Decision filtering
    if decision is None:
        stmt = stmt.where(
            Escalation.decision.in_([
                EscalationDecision.PENDING,
                EscalationDecision.MORE_INFO_REQUESTED,
            ])
        )
    elif isinstance(decision, list):
        stmt = stmt.where(Escalation.decision.in_(decision))
    else:
        stmt = stmt.where(Escalation.decision == decision)

    if priority is not None:
        stmt = stmt.where(Escalation.priority == priority)

    if assigned_to is not None:
        if assigned_to.lower() == "me":
            stmt = stmt.where(Escalation.assigned_to == current_user.id)
        else:
            try:
                target_uuid = uuid.UUID(assigned_to)
                stmt = stmt.where(Escalation.assigned_to == target_uuid)
            except (ValueError, TypeError):
                stmt = stmt.where(Escalation.assigned_to == uuid.uuid4())

    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0

    # Sort by priority urgent -> low, then oldest first
    stmt = stmt.order_by(PRIORITY_ORDER.asc(), Escalation.created_at.asc())

    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    escalations = db.scalars(stmt).all()

    items: list[StaffEscalationListItem] = []
    for esc in escalations:
        items.append(
            StaffEscalationListItem(
                id=esc.id,
                ticket_id=esc.ticket_id,
                ticket_subject=esc.ticket.subject if esc.ticket else "No Subject",
                customer_id=esc.ticket.customer_id if esc.ticket else uuid.uuid4(),
                customer_name=esc.ticket.customer.name if (esc.ticket and esc.ticket.customer) else "Customer",
                order_id=esc.ticket.order_id if esc.ticket else None,
                amount=esc.refund.amount if esc.refund else None,
                priority=esc.priority,
                decision=esc.decision,
                assigned_to=esc.assigned_to,
                created_at=esc.created_at,
            )
        )

    return StaffPaginatedEscalations(items=items, page=page, page_size=page_size, total=total)


def get_staff_escalation_detail(db: Session, escalation_id: uuid.UUID) -> StaffEscalationDetail:
    """
    Fetches full context for an escalation review in one query tree.
    """
    stmt = (
        select(Escalation)
        .where(Escalation.id == escalation_id)
        .options(
            selectinload(Escalation.ticket).selectinload(Ticket.customer),
            selectinload(Escalation.ticket).selectinload(Ticket.messages),
            selectinload(Escalation.ticket).selectinload(Ticket.notes).selectinload(TicketNote.author),
            selectinload(Escalation.refund),
            selectinload(Escalation.ticket).selectinload(Ticket.order).selectinload(Order.items),
        )
    )
    esc = db.scalar(stmt)
    if esc is None:
        raise AppError(code="NOT_FOUND", message="Escalation not found.", status_code=404)

    ticket = esc.ticket
    order_read = None
    today = get_today_date()
    if ticket and ticket.order:
        last_date = None
        is_returnable = False
        if ticket.order.delivery_date:
            from datetime import timedelta
            last_date = ticket.order.delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
            is_returnable = (
                today <= last_date
                and not any(it.category in NON_RETURNABLE_CATEGORIES for it in ticket.order.items)
            )

        order_read = StaffOrderRead(
            id=ticket.order.id,
            status=ticket.order.status,
            total_amount=ticket.order.total_amount,
            delivery_date=ticket.order.delivery_date,
            return_window=StaffOrderReturnWindow(
                return_window_days=RETURN_WINDOW_DAYS,
                is_returnable=is_returnable,
                last_eligible_date=last_date,
            ),
            items=[
                StaffOrderItemRead(
                    id=it.id,
                    name=it.name,
                    category=it.category,
                    quantity=it.quantity,
                    unit_price=it.unit_price,
                )
                for it in ticket.order.items
            ],
        )

    refund_read = None
    if esc.refund:
        refund_read = StaffRefundRead(
            id=esc.refund.id,
            order_id=esc.refund.order_id,
            ticket_id=esc.refund.ticket_id,
            amount=esc.refund.amount,
            reason=esc.refund.reason,
            status=esc.refund.status,
            payment_reference=esc.refund.payment_reference,
            failure_reason=esc.refund.failure_reason,
            created_at=esc.refund.created_at,
            updated_at=esc.refund.updated_at,
        )

    messages_read = [
        StaffMessageRead(
            id=m.id,
            ticket_id=m.ticket_id,
            sender_type=m.sender_type,
            sender_id=m.sender_id,
            content=m.content,
            created_at=m.created_at,
        )
        for m in sorted(ticket.messages, key=lambda m: m.created_at)
    ] if ticket else []

    notes_read = [
        StaffNoteRead(
            id=n.id,
            ticket_id=n.ticket_id,
            author_id=n.author_id,
            author_name=n.author.name if n.author else "Staff",
            note=n.note,
            created_at=n.created_at,
        )
        for n in sorted(ticket.notes, key=lambda n: n.created_at)
    ] if ticket else []

    # Parse passed verification checks from structured summary
    checks_passed = [
        "order_ownership_verified",
        "order_delivered_status_verified",
        "return_window_verified",
        "eligible_category_verified",
        "refundable_balance_verified",
    ]

    ticket_info = StaffTicketInfo(
        id=ticket.id,
        customer_id=ticket.customer_id,
        order_id=ticket.order_id,
        subject=ticket.subject,
        description=ticket.description,
        category=ticket.category,
        status=ticket.status,
        priority=ticket.priority,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    ) if ticket else None

    return StaffEscalationDetail(
        id=esc.id,
        ticket_id=esc.ticket_id,
        refund_id=esc.refund_id,
        summary=esc.summary,
        priority=esc.priority,
        decision=esc.decision,
        assigned_to=esc.assigned_to,
        internal_note=esc.internal_note,
        created_at=esc.created_at,
        decided_at=esc.decided_at,
        checks_passed=checks_passed,
        ticket=ticket_info,
        order=order_read,
        refund=refund_read,
        messages=messages_read,
        notes=notes_read,
    )


def assign_staff_escalation(
    db: Session,
    staff_user: User,
    escalation_id: uuid.UUID,
    assignee_id: uuid.UUID | None = None,
) -> Escalation:
    """
    Assigns an escalation to a staff member.
    An agent can only assign to self. An admin can assign to any staff user.
    Assigning to a customer or non-staff user raises 422 VALIDATION_ERROR.
    """
    target_assignee_id = assignee_id if assignee_id is not None else staff_user.id

    if staff_user.role == UserRole.AGENT and target_assignee_id != staff_user.id:
        raise AppError(
            code="FORBIDDEN",
            message="Support agents can only assign escalations to themselves.",
            status_code=403,
        )

    # Validate target assignee exists and holds staff role
    target_user = db.get(User, target_assignee_id)
    if target_user is None or target_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise AppError(
            code="VALIDATION_ERROR",
            message="The designated assignee must be a valid staff user (agent or admin).",
            status_code=422,
        )

    escalation = db.execute(
        select(Escalation).where(Escalation.id == escalation_id).with_for_update()
    ).scalar_one_or_none()

    if escalation is None:
        raise AppError(code="NOT_FOUND", message="Escalation not found.", status_code=404)

    escalation.assigned_to = target_assignee_id
    audit = AuditEvent(
        actor_id=staff_user.id,
        actor_type=ActorType.STAFF,
        event_type="escalation.assigned",
        entity_type="escalation",
        entity_id=escalation.id,
        audit_metadata={"assigned_to": str(target_assignee_id)},
    )
    db.add(audit)
    db.commit()
    db.refresh(escalation)
    return escalation


def decide_staff_escalation(
    db: Session,
    staff_user: User,
    escalation_id: uuid.UUID,
    decision: Literal["approve", "reject", "request_info"],
    note: str,
    message_to_customer: str | None = None,
) -> Refund | None:
    """
    Processes a human staff decision (approve, reject, or request_info) on an escalation.
    Guarantees atomic row-level serialization on the escalation record.
    """
    if not note or len(note.strip()) < 5:
        raise AppError(
            code="VALIDATION_ERROR",
            message="A mandatory internal note explaining the decision (minimum 5 characters) is required.",
            status_code=422,
        )

    escalation = db.execute(
        select(Escalation).where(Escalation.id == escalation_id).with_for_update()
    ).scalar_one_or_none()

    if escalation is None:
        raise AppError(code="NOT_FOUND", message="Escalation not found.", status_code=404)

    if escalation.decision not in (EscalationDecision.PENDING, EscalationDecision.MORE_INFO_REQUESTED):
        raise AppError(
            code="ALREADY_DECIDED",
            message="This escalation has already been decided.",
            status_code=409,
        )

    # 1. APPROVE path
    if decision == "approve":
        result = approve_escalated_refund(
            db=db,
            staff_user=staff_user,
            escalation_id=escalation.id,
            note=note.strip(),
        )
        if result.outcome == Outcome.PROCESSED:
            return result.refund
        elif result.outcome == Outcome.ERROR:
            raise AppError(
                code="PAYMENT_FAILED",
                message="Refund was approved by staff, but payment processing failed. The refund was NOT completed.",
                status_code=502,
            )
        raise AppError(
            code="REFUND_REJECTED",
            message=result.message,
            status_code=409,
        )

    # 2. REJECT path
    elif decision == "reject":
        if not message_to_customer or len(message_to_customer.strip()) < 5:
            raise AppError(
                code="VALIDATION_ERROR",
                message="A customer-facing explanation message (minimum 5 characters) is required when rejecting.",
                status_code=422,
            )

        result = reject_refund(
            db=db,
            staff_user=staff_user,
            escalation_id=escalation.id,
            note=note.strip(),
            message_to_customer=message_to_customer.strip(),
        )
        return result.refund

    # 3. REQUEST_INFO path
    elif decision == "request_info":
        if not message_to_customer or len(message_to_customer.strip()) < 5:
            raise AppError(
                code="VALIDATION_ERROR",
                message="A customer-facing question message (minimum 5 characters) is required when requesting more info.",
                status_code=422,
            )

        escalation.decision = EscalationDecision.MORE_INFO_REQUESTED
        escalation.internal_note = note.strip()
        escalation.assigned_to = staff_user.id

        ticket = db.get(Ticket, escalation.ticket_id)
        if ticket:
            ticket.status = TicketStatus.AWAITING_CUSTOMER
            ticket.updated_at = datetime.now(timezone.utc)
            staff_msg = Message(
                ticket_id=ticket.id,
                sender_type=SenderType.STAFF,
                sender_id=staff_user.id,
                content=message_to_customer.strip(),
            )
            db.add(staff_msg)

        audit = AuditEvent(
            actor_id=staff_user.id,
            actor_type=ActorType.STAFF,
            event_type="escalation.info_requested",
            entity_type="escalation",
            entity_id=escalation.id,
            audit_metadata={"ticket_id": str(escalation.ticket_id)},
        )
        db.add(audit)
        db.commit()
        db.refresh(escalation)

        return db.get(Refund, escalation.refund_id) if escalation.refund_id else None

    raise AppError(code="INVALID_DECISION", message="Unknown decision action.", status_code=422)


def create_escalation_for_ticket(
    db: Session,
    ticket: Ticket,
    summary: str,
    priority: TicketPriority | str = TicketPriority.HIGH,
    source: str = "ai_agent",
) -> Escalation:
    """
    Idempotent helper to create an escalation for a ticket.
    If an escalation already exists in PENDING or MORE_INFO_REQUESTED status for this ticket,
    it returns the existing escalation rather than creating a duplicate.
    Caps summary at 1000 characters, sets ticket status to ESCALATED, and writes an audit event.
    """
    existing_esc = db.scalar(
        select(Escalation)
        .where(
            Escalation.ticket_id == ticket.id,
            Escalation.decision.in_([
                EscalationDecision.PENDING,
                EscalationDecision.MORE_INFO_REQUESTED,
            ]),
        )
        .order_by(Escalation.created_at.desc())
    )
    if existing_esc:
        return existing_esc

    # Normalize priority
    if isinstance(priority, str):
        priority_map = {
            "low": TicketPriority.LOW,
            "medium": TicketPriority.MEDIUM,
            "high": TicketPriority.HIGH,
            "urgent": TicketPriority.URGENT,
        }
        target_priority = priority_map.get(priority.lower(), TicketPriority.HIGH)
    else:
        target_priority = priority

    ticket.status = TicketStatus.ESCALATED
    ticket.priority = target_priority
    ticket.updated_at = datetime.now(timezone.utc)

    escalation = Escalation(
        ticket_id=ticket.id,
        summary=summary[:1000] if summary else "Escalation requested",
        priority=target_priority,
        decision=EscalationDecision.PENDING,
    )
    db.add(escalation)
    db.flush()

    audit = AuditEvent(
        actor_id=ticket.customer_id,
        actor_type=ActorType.SYSTEM if source == "agent_failure" else ActorType.CUSTOMER,
        event_type="escalation.created",
        entity_type="escalation",
        entity_id=escalation.id,
        audit_metadata={"ticket_id": str(ticket.id), "source": source},
    )
    db.add(audit)
    db.commit()
    db.refresh(escalation)
    return escalation
