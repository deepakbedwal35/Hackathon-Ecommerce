from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from typing import Any

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session, selectinload
import structlog

from app.core.errors import AppError
from app.core.policy import (
    NON_RETURNABLE_CATEGORIES,
    RETURN_WINDOW_DAYS,
    get_today_date,
)
from app.models.enums import (
    ActorType,
    EscalationDecision,
    RefundStatus,
    SenderType,
    TicketCategory,
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
    StaffEscalationSummary,
    StaffMessageRead,
    StaffNoteRead,
    StaffOrderItemRead,
    StaffOrderRead,
    StaffOrderReturnWindow,
    StaffOverviewRead,
    StaffPaginatedTickets,
    StaffPendingApprovalItem,
    StaffRecentTicketItem,
    StaffRefundRead,
    StaffTicketDetail,
    StaffTicketInfo,
    StaffTicketListItem,
    StaffTicketRefundSummary,
)

logger = structlog.get_logger("services.staff_tickets")


def escape_like(s: str) -> str:
    """Escapes SQL LIKE wildcards (%, _, \\) to prevent user-injected wildcard matching."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


ALLOWED_TRANSITIONS: dict[TicketStatus, set[TicketStatus]] = {
    TicketStatus.OPEN: {TicketStatus.AWAITING_CUSTOMER, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.AWAITING_CUSTOMER: {TicketStatus.OPEN, TicketStatus.RESOLVED, TicketStatus.CLOSED},
    TicketStatus.ESCALATED: set(),  # Only via an escalation decision!
    TicketStatus.RESOLVED: {TicketStatus.OPEN, TicketStatus.CLOSED},
    TicketStatus.CLOSED: set(),     # Terminal state
}

PRIORITY_ORDER = case(
    {
        TicketPriority.URGENT: 1,
        TicketPriority.HIGH: 2,
        TicketPriority.MEDIUM: 3,
        TicketPriority.LOW: 4,
    },
    value=Ticket.priority,
)


def list_staff_tickets(
    db: Session,
    current_user: User,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
    category: TicketCategory | None = None,
    has_escalation: bool | None = None,
    escalation_decision: EscalationDecision | None = None,
    assigned_to: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    q: str | None = None,
    sort: str = "sla",
    page: int = 1,
    page_size: int = 20,
) -> StaffPaginatedTickets:
    """
    Paginated list of support tickets with multi-dimensional filtering,
    secure wildcard-escaped search, and SLA-based sorting.
    """
    stmt = (
        select(Ticket)
        .join(User, Ticket.customer_id == User.id)
        .options(
            selectinload(Ticket.customer),
            selectinload(Ticket.order),
            selectinload(Ticket.escalations),
            selectinload(Ticket.refunds),
        )
    )

    if status is not None:
        stmt = stmt.where(Ticket.status == status)
    if priority is not None:
        stmt = stmt.where(Ticket.priority == priority)
    if category is not None:
        stmt = stmt.where(Ticket.category == category)
    if created_from is not None:
        stmt = stmt.where(Ticket.created_at >= created_from)
    if created_to is not None:
        stmt = stmt.where(Ticket.created_at <= created_to)

    # Escalation relationship filtering
    if has_escalation is not None or escalation_decision is not None or assigned_to is not None:
        esc_filter = select(Escalation.ticket_id)
        if escalation_decision is not None:
            esc_filter = esc_filter.where(Escalation.decision == escalation_decision)
        if assigned_to is not None:
            if assigned_to.lower() == "me":
                target_user_id = current_user.id
            else:
                try:
                    target_user_id = uuid.UUID(assigned_to)
                except (ValueError, TypeError):
                    target_user_id = uuid.uuid4()  # Dummy non-matching UUID
            esc_filter = esc_filter.where(Escalation.assigned_to == target_user_id)

        if has_escalation is True or escalation_decision is not None or assigned_to is not None:
            stmt = stmt.where(Ticket.id.in_(esc_filter))
        elif has_escalation is False:
            stmt = stmt.where(~Ticket.id.in_(select(Escalation.ticket_id)))

    # Search query
    if q is not None and q.strip():
        search_term = q.strip()
        escaped_q = escape_like(search_term)
        like_pattern = f"%{escaped_q}%"
        search_clauses = [
            Ticket.subject.ilike(like_pattern),
            User.email.ilike(like_pattern),
        ]
        try:
            val_uuid = uuid.UUID(search_term)
            search_clauses.append(Ticket.id == val_uuid)
        except (ValueError, TypeError):
            pass

        stmt = stmt.where(or_(*search_clauses))

    # Total count query
    count_stmt = select(func.count()).select_from(stmt.order_by(None).subquery())
    total = db.scalar(count_stmt) or 0

    # Sorting
    if sort == "newest":
        stmt = stmt.order_by(Ticket.created_at.desc())
    else:
        # Default SLA sorting: priority urgent->low, then oldest first
        stmt = stmt.order_by(PRIORITY_ORDER.asc(), Ticket.created_at.asc())

    # Pagination
    offset = (page - 1) * page_size
    stmt = stmt.offset(offset).limit(page_size)
    tickets = db.scalars(stmt).all()

    items: list[StaffTicketListItem] = []
    for t in tickets:
        # Calculate pending escalation flag
        has_pending = any(
            e.decision in (EscalationDecision.PENDING, EscalationDecision.MORE_INFO_REQUESTED)
            for e in t.escalations
        )
        # Calculate refund summary
        ref_summary = None
        if t.refunds:
            latest_refund = sorted(t.refunds, key=lambda r: r.created_at, reverse=True)[0]
            ref_summary = StaffTicketRefundSummary(
                id=latest_refund.id,
                amount=latest_refund.amount,
                status=latest_refund.status,
            )

        items.append(
            StaffTicketListItem(
                id=t.id,
                subject=t.subject,
                category=t.category,
                status=t.status,
                priority=t.priority,
                customer_id=t.customer_id,
                customer_name=t.customer.name,
                order_id=t.order_id,
                order_number=t.order.order_number if t.order else None,
                refund_summary=ref_summary,
                has_pending_escalation=has_pending,
                awaiting_admin_approval=has_pending,
                created_at=t.created_at,
                updated_at=t.updated_at,
            )
        )

    return StaffPaginatedTickets(items=items, page=page, page_size=page_size, total=total)


def get_staff_ticket_detail(db: Session, ticket_id: uuid.UUID) -> StaffTicketDetail:
    """
    Fetches full ticket context in ONE round-trip query without N+1.
    Includes customer, order + items + return window, refunds, escalations, messages, and notes.
    """
    stmt = (
        select(Ticket)
        .where(Ticket.id == ticket_id)
        .options(
            selectinload(Ticket.customer),
            selectinload(Ticket.order).selectinload(Order.items),
            selectinload(Ticket.order).selectinload(Order.refunds),
            selectinload(Ticket.messages),
            selectinload(Ticket.notes).selectinload(TicketNote.author),
            selectinload(Ticket.escalations),
            selectinload(Ticket.refunds),
        )
    )
    ticket = db.scalar(stmt)
    if ticket is None:
        raise AppError(code="NOT_FOUND", message="Ticket not found.", status_code=404)

    # Order & Return Window calculations
    order_read = None
    today = get_today_date()
    if ticket.order:
        last_date = None
        is_returnable = False
        if ticket.order.delivery_date:
            last_date = ticket.order.delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
            is_returnable = (
                today <= last_date
                and not any(it.category in NON_RETURNABLE_CATEGORIES for it in ticket.order.items)
            )

        return_window = StaffOrderReturnWindow(
            return_window_days=RETURN_WINDOW_DAYS,
            is_returnable=is_returnable,
            last_eligible_date=last_date,
        )

        items_read = [
            StaffOrderItemRead(
                id=it.id,
                name=it.name,
                category=it.category,
                quantity=it.quantity,
                unit_price=it.unit_price,
            )
            for it in ticket.order.items
        ]

        order_read = StaffOrderRead(
            id=ticket.order.id,
            order_number=ticket.order.order_number,
            status=ticket.order.status,
            total_amount=ticket.order.total_amount,
            delivery_date=ticket.order.delivery_date,
            return_window=return_window,
            items=items_read,
        )

    # All refunds on order or ticket
    refunds_map: dict[uuid.UUID, Refund] = {}
    if ticket.order and ticket.order.refunds:
        for r in ticket.order.refunds:
            refunds_map[r.id] = r
    for r in ticket.refunds:
        refunds_map[r.id] = r

    refunds_list = [
        StaffRefundRead(
            id=r.id,
            order_id=r.order_id,
            ticket_id=r.ticket_id,
            amount=r.amount,
            reason=r.reason,
            status=r.status,
            payment_reference=r.payment_reference,
            failure_reason=r.failure_reason,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in sorted(refunds_map.values(), key=lambda r: r.created_at)
    ]

    escalations_list = [
        StaffEscalationSummary(
            id=e.id,
            refund_id=e.refund_id,
            summary=e.summary,
            priority=e.priority,
            decision=e.decision,
            assigned_to=e.assigned_to,
            internal_note=e.internal_note,
            created_at=e.created_at,
            decided_at=e.decided_at,
        )
        for e in sorted(ticket.escalations, key=lambda e: e.created_at)
    ]

    messages_list = [
        StaffMessageRead(
            id=m.id,
            ticket_id=m.ticket_id,
            sender_type=m.sender_type,
            sender_id=m.sender_id,
            content=m.content,
            created_at=m.created_at,
        )
        for m in sorted(ticket.messages, key=lambda m: m.created_at)
    ]

    notes_list = [
        StaffNoteRead(
            id=n.id,
            ticket_id=n.ticket_id,
            author_id=n.author_id,
            author_name=n.author.name if n.author else "Staff",
            note=n.note,
            created_at=n.created_at,
        )
        for n in sorted(ticket.notes, key=lambda n: n.created_at)
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
    )

    has_pending_esc = any(
        e.decision in (EscalationDecision.PENDING, EscalationDecision.MORE_INFO_REQUESTED)
        for e in ticket.escalations
    )
    allowed = set(ALLOWED_TRANSITIONS.get(ticket.status, set()))
    if has_pending_esc:
        allowed -= {TicketStatus.RESOLVED, TicketStatus.CLOSED}
    allowed_transitions = sorted(list(allowed), key=lambda s: s.value)

    return StaffTicketDetail(
        ticket=ticket_info,
        customer=StaffCustomerSummary(
            id=ticket.customer.id,
            name=ticket.customer.name,
            email=ticket.customer.email,
        ),
        order=order_read,
        refunds=refunds_list,
        escalations=escalations_list,
        messages=messages_list,
        notes=notes_list,
        awaiting_admin_approval=has_pending_esc,
        allowed_transitions=allowed_transitions,
    )


def patch_staff_ticket(
    db: Session,
    staff_user: User,
    ticket_id: uuid.UUID,
    status: TicketStatus | None = None,
    priority: TicketPriority | None = None,
) -> Ticket:
    """
    Updates a ticket's status and/or priority.
    Enforces strict state transitions, blocks manual transition to/from escalated,
    and forbids resolving/closing while an escalation is pending.
    """
    ticket = db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    ).scalar_one_or_none()

    if ticket is None:
        raise AppError(code="NOT_FOUND", message="Ticket not found.", status_code=404)

    old_status = ticket.status
    old_priority = ticket.priority
    changes: dict[str, Any] = {}

    if status is not None and status != old_status:
        # Staff cannot set status=escalated manually
        if status == TicketStatus.ESCALATED:
            raise AppError(
                code="INVALID_TRANSITION",
                message="Tickets can only be escalated automatically through refund or support policy rules.",
                status_code=409,
            )

        # Check pending escalations
        has_pending_escalation = db.scalar(
            select(func.count(Escalation.id)).where(
                Escalation.ticket_id == ticket.id,
                Escalation.decision.in_([
                    EscalationDecision.PENDING,
                    EscalationDecision.MORE_INFO_REQUESTED,
                ]),
            )
        ) > 0

        # Cannot manually move away from escalated while an escalation is pending
        if old_status == TicketStatus.ESCALATED and has_pending_escalation:
            raise AppError(
                code="ESCALATION_PENDING",
                message="Cannot manually modify ticket status while an escalation decision is pending.",
                status_code=409,
            )

        # Resolving or closing with a pending escalation is forbidden
        if status in (TicketStatus.RESOLVED, TicketStatus.CLOSED) and has_pending_escalation:
            raise AppError(
                code="ESCALATION_PENDING",
                message="Cannot resolve or close a ticket with a pending escalation.",
                status_code=409,
            )

        # Enforce transition graph
        valid_next_states = ALLOWED_TRANSITIONS.get(old_status, set())
        if status not in valid_next_states:
            raise AppError(
                code="INVALID_TRANSITION",
                message=f"Transition from {old_status.value} to {status.value} is not allowed.",
                status_code=409,
            )

        ticket.status = status
        changes["old_status"] = old_status.value
        changes["new_status"] = status.value

    if priority is not None and priority != old_priority:
        ticket.priority = priority
        changes["old_priority"] = old_priority.value
        changes["new_priority"] = priority.value

    if changes:
        ticket.updated_at = datetime.now(timezone.utc)
        audit = AuditEvent(
            actor_id=staff_user.id,
            actor_type=ActorType.STAFF,
            event_type="ticket.updated",
            entity_type="ticket",
            entity_id=ticket.id,
            audit_metadata=changes,
        )
        db.add(audit)
        db.commit()
        db.refresh(ticket)

    return ticket


def add_staff_ticket_message(
    db: Session,
    staff_user: User,
    ticket_id: uuid.UUID,
    content: str,
) -> Message:
    """
    Posts a customer-visible reply from staff on a ticket.
    Rejects if ticket is closed.
    """
    ticket = db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    ).scalar_one_or_none()

    if ticket is None:
        raise AppError(code="NOT_FOUND", message="Ticket not found.", status_code=404)

    if ticket.status == TicketStatus.CLOSED:
        raise AppError(
            code="TICKET_CLOSED",
            message="Cannot add messages to a closed ticket.",
            status_code=409,
        )

    msg = Message(
        ticket_id=ticket.id,
        sender_type=SenderType.STAFF,
        sender_id=staff_user.id,
        content=content.strip(),
    )
    db.add(msg)
    ticket.updated_at = datetime.now(timezone.utc)
    db.flush()

    audit = AuditEvent(
        actor_id=staff_user.id,
        actor_type=ActorType.STAFF,
        event_type="ticket.message_added",
        entity_type="ticket",
        entity_id=ticket.id,
        audit_metadata={"message_id": str(msg.id)},
    )
    db.add(audit)
    db.commit()
    db.refresh(msg)
    return msg


def list_staff_ticket_notes(db: Session, ticket_id: uuid.UUID) -> list[TicketNote]:
    """Retrieves all internal notes for a ticket."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise AppError(code="NOT_FOUND", message="Ticket not found.", status_code=404)

    stmt = (
        select(TicketNote)
        .where(TicketNote.ticket_id == ticket_id)
        .options(selectinload(TicketNote.author))
        .order_by(TicketNote.created_at.asc())
    )
    return db.scalars(stmt).all()


def add_staff_ticket_note(
    db: Session,
    staff_user: User,
    ticket_id: uuid.UUID,
    note: str,
) -> TicketNote:
    """Adds an internal, staff-only note to a ticket."""
    ticket = db.get(Ticket, ticket_id)
    if ticket is None:
        raise AppError(code="NOT_FOUND", message="Ticket not found.", status_code=404)

    ticket_note = TicketNote(
        ticket_id=ticket.id,
        author_id=staff_user.id,
        note=note.strip(),
    )
    db.add(ticket_note)
    db.flush()

    audit = AuditEvent(
        actor_id=staff_user.id,
        actor_type=ActorType.STAFF,
        event_type="ticket.note_added",
        entity_type="ticket",
        entity_id=ticket.id,
        audit_metadata={"note_id": str(ticket_note.id)},
    )
    db.add(audit)
    db.commit()
    db.refresh(ticket_note)
    return ticket_note


def get_staff_overview(db: Session) -> StaffOverviewRead:
    """
    Computes dashboard overview statistics for staff in pure SQL.
    Includes status distribution, queue depths, SLA aging, and top pending tasks.
    """
    # 1. Ticket counts by status in SQL
    status_counts_rows = db.execute(
        select(Ticket.status, func.count(Ticket.id)).group_by(Ticket.status)
    ).all()
    ticket_counts = {s.value: 0 for s in TicketStatus}
    for st, count in status_counts_rows:
        ticket_counts[st.value] = count

    # 2. Awaiting approval count (pending escalations)
    awaiting_approval_count = db.scalar(
        select(func.count(Escalation.id)).where(
            Escalation.decision.in_([
                EscalationDecision.PENDING,
                EscalationDecision.MORE_INFO_REQUESTED,
            ])
        )
    ) or 0

    # 3. Unassigned count
    unassigned_count = db.scalar(
        select(func.count(Escalation.id)).where(
            Escalation.assigned_to.is_(None),
            Escalation.decision.in_([
                EscalationDecision.PENDING,
                EscalationDecision.MORE_INFO_REQUESTED,
            ]),
        )
    ) or 0

    # 4. Oldest pending approval created_at
    oldest_pending_approval_created_at = db.scalar(
        select(func.min(Escalation.created_at)).where(
            Escalation.decision == EscalationDecision.PENDING
        )
    )

    # 5. Pending refund total (sum of amounts in pending_review)
    pending_refund_total = db.scalar(
        select(func.coalesce(func.sum(Refund.amount), Decimal("0.00"))).where(
            Refund.status == RefundStatus.PENDING_REVIEW
        )
    ) or Decimal("0.00")

    # 6. Top 5 pending approvals
    esc_stmt = (
        select(
            Escalation.id.label("escalation_id"),
            Escalation.ticket_id,
            Ticket.order_id,
            Order.order_number,
            User.name.label("customer_name"),
            func.coalesce(Refund.amount, Decimal("0.00")).label("amount"),
            Escalation.priority,
            Escalation.created_at,
        )
        .join(Ticket, Escalation.ticket_id == Ticket.id)
        .join(User, Ticket.customer_id == User.id)
        .outerjoin(Refund, Escalation.refund_id == Refund.id)
        .outerjoin(Order, Ticket.order_id == Order.id)
        .where(
            Escalation.decision.in_([
                EscalationDecision.PENDING,
                EscalationDecision.MORE_INFO_REQUESTED,
            ])
        )
        .order_by(PRIORITY_ORDER.asc(), Escalation.created_at.asc())
        .limit(5)
    )
    esc_rows = db.execute(esc_stmt).all()
    top_5_pending_approvals = [
        StaffPendingApprovalItem(
            escalation_id=row.escalation_id,
            ticket_id=row.ticket_id,
            order_id=row.order_id,
            order_number=row.order_number,
            customer_name=row.customer_name,
            amount=row.amount,
            priority=row.priority,
            created_at=row.created_at,
        )
        for row in esc_rows
    ]

    # 7. Top 5 recent tickets
    recent_stmt = (
        select(
            Ticket.id.label("ticket_id"),
            Ticket.subject,
            User.name.label("customer_name"),
            Ticket.status,
            Ticket.priority,
            Ticket.created_at,
        )
        .join(User, Ticket.customer_id == User.id)
        .order_by(Ticket.created_at.desc())
        .limit(5)
    )
    recent_rows = db.execute(recent_stmt).all()
    top_5_recent_tickets = [
        StaffRecentTicketItem(
            ticket_id=row.ticket_id,
            subject=row.subject,
            customer_name=row.customer_name,
            status=row.status,
            priority=row.priority,
            created_at=row.created_at,
        )
        for row in recent_rows
    ]

    return StaffOverviewRead(
        ticket_counts=ticket_counts,
        awaiting_approval_count=awaiting_approval_count,
        unassigned_count=unassigned_count,
        oldest_pending_approval_created_at=oldest_pending_approval_created_at,
        pending_refund_total=pending_refund_total,
        top_5_pending_approvals=top_5_pending_approvals,
        top_5_recent_tickets=top_5_recent_tickets,
    )


def list_staff_ticket_messages(
    db: Session,
    ticket_id: uuid.UUID,
    after: datetime | None = None,
) -> list[StaffMessageRead]:
    """Lists messages for a ticket, with optional timestamp cursor filter."""
    ticket = db.get(Ticket, ticket_id)
    if not ticket:
        raise AppError(code="NOT_FOUND", message="Ticket not found.", status_code=404)
    stmt = (
        select(Message)
        .where(Message.ticket_id == ticket_id)
    )
    if after is not None:
        stmt = stmt.where(Message.created_at > after)
    stmt = stmt.order_by(Message.created_at.asc())
    messages = db.scalars(stmt).all()
    return [
        StaffMessageRead(
            id=m.id,
            ticket_id=m.ticket_id,
            sender_type=m.sender_type,
            sender_id=m.sender_id,
            content=m.content,
            created_at=m.created_at,
        )
        for m in messages
    ]

