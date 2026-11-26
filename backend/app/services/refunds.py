from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import enum
import hashlib
import uuid
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
import structlog

from app.core.errors import AppError
from app.core.policy import (
    AUTO_REFUND_LIMIT,
    NON_RETURNABLE_CATEGORIES,
    RETURN_WINDOW_DAYS,
    ClockCallable,
    get_today_date,
)
from app.models.enums import (
    ActorType,
    EscalationDecision,
    OrderStatus,
    RefundStatus,
    SenderType,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.models import AuditEvent, Escalation, Message, Order, Refund, Ticket, User
from app.services.access import get_order_for_user, get_ticket_for_user
from app.services.payment_mock import execute_refund_payment

logger = structlog.get_logger("services.refunds")


class Outcome(str, enum.Enum):
    PROCESSED = "PROCESSED"
    ESCALATED = "ESCALATED"
    REJECTED = "REJECTED"
    DUPLICATE = "DUPLICATE"
    ERROR = "ERROR"


class ReasonCode(str, enum.Enum):
    NOT_FOUND = "NOT_FOUND"
    ORDER_NOT_DELIVERED = "ORDER_NOT_DELIVERED"
    RETURN_WINDOW_EXPIRED = "RETURN_WINDOW_EXPIRED"
    NON_RETURNABLE_CATEGORY = "NON_RETURNABLE_CATEGORY"
    AMOUNT_INVALID = "AMOUNT_INVALID"
    AMOUNT_EXCEEDS_REFUNDABLE = "AMOUNT_EXCEEDS_REFUNDABLE"
    ALREADY_REFUNDED = "ALREADY_REFUNDED"
    ACTIVE_REFUND_EXISTS = "ACTIVE_REFUND_EXISTS"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    ALREADY_DECIDED = "ALREADY_DECIDED"


@dataclass
class RefundResult:
    outcome: Outcome
    refund: Refund | None = None
    reason_code: ReasonCode | None = None
    message: str = ""
    escalation: Escalation | None = None


def _audit(
    db: Session,
    actor_id: uuid.UUID | None,
    actor_type: ActorType,
    event_type: str,
    entity_id: uuid.UUID,
    metadata: dict[str, Any],
) -> None:
    audit_event = AuditEvent(
        actor_id=actor_id,
        actor_type=actor_type,
        event_type=event_type,
        entity_type="refund",
        entity_id=entity_id,
        audit_metadata=metadata,
        request_id=None,
    )
    db.add(audit_event)


def request_refund(
    db: Session,
    user: User,
    order_id: uuid.UUID,
    amount: Any,
    reason: str,
    ticket_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    clock: ClockCallable | None = None,
) -> RefundResult:
    """
    Unified, single code path for creating and executing refunds.
    Executed in a strict sequential pipeline inside a row-locked transaction.
    """
    today_fn = clock or get_today_date
    today = today_fn()

    # 1. Ownership validation
    try:
        get_order_for_user(db, user, order_id)
    except AppError as err:
        if err.code == "NOT_FOUND":
            return RefundResult(
                outcome=Outcome.REJECTED,
                reason_code=ReasonCode.NOT_FOUND,
                message="Order not found.",
            )
        raise

    if ticket_id is not None:
        try:
            ticket = get_ticket_for_user(db, user, ticket_id)
            if ticket.order_id is not None and ticket.order_id != order_id:
                return RefundResult(
                    outcome=Outcome.REJECTED,
                    reason_code=ReasonCode.NOT_FOUND,
                    message="Order not found.",
                )
        except AppError as err:
            if err.code == "NOT_FOUND":
                return RefundResult(
                    outcome=Outcome.REJECTED,
                    reason_code=ReasonCode.NOT_FOUND,
                    message="Ticket not found.",
                )
            raise

    # 2. Row Lock: SELECT ... FOR UPDATE on the order row
    order = db.execute(
        select(Order).where(Order.id == order_id).with_for_update()
    ).scalar_one()

    # 3. Idempotency Key Computation & Verification
    if idempotency_key and idempotency_key.strip():
        computed_key = idempotency_key.strip()
    else:
        raw_key = f"{user.id}:{order.id}:{amount}"
        computed_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()

    existing_refund = db.scalar(
        select(Refund).where(Refund.idempotency_key == computed_key)
    )
    if existing_refund is not None:
        logger.info(
            "refund_duplicate",
            refund_id=str(existing_refund.id),
            order_id=str(order.id),
            outcome=Outcome.DUPLICATE.value,
        )
        return RefundResult(
            outcome=Outcome.DUPLICATE,
            refund=existing_refund,
            message="A refund request with this idempotency key has already been processed or submitted.",
        )

    # 4. Order Status Check
    if order.status != OrderStatus.DELIVERED or order.delivery_date is None:
        _audit(
            db,
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="refund.rejected_by_policy",
            entity_id=order.id,
            metadata={"reason_code": ReasonCode.ORDER_NOT_DELIVERED.value, "ticket_id": str(ticket_id) if ticket_id else None},
        )
        db.commit()
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.ORDER_NOT_DELIVERED,
            message="Refunds can only be requested for orders that have been successfully delivered.",
        )

    # 5. Return Window Check
    last_eligible_date = order.delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
    if today > last_eligible_date:
        _audit(
            db,
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="refund.rejected_by_policy",
            entity_id=order.id,
            metadata={
                "reason_code": ReasonCode.RETURN_WINDOW_EXPIRED.value,
                "delivery_date": order.delivery_date.isoformat(),
                "last_eligible_date": last_eligible_date.isoformat(),
                "ticket_id": str(ticket_id) if ticket_id else None,
            },
        )
        db.commit()
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.RETURN_WINDOW_EXPIRED,
            message=(
                f"The {RETURN_WINDOW_DAYS}-day return window for this order has expired. "
                f"The last eligible date was {last_eligible_date.isoformat()}."
            ),
        )

    # 6. Non-Returnable Category Check
    contains_non_returnable = any(
        item.category in NON_RETURNABLE_CATEGORIES for item in order.items
    )
    if contains_non_returnable:
        _audit(
            db,
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="refund.rejected_by_policy",
            entity_id=order.id,
            metadata={"reason_code": ReasonCode.NON_RETURNABLE_CATEGORY.value, "ticket_id": str(ticket_id) if ticket_id else None},
        )
        db.commit()
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.NON_RETURNABLE_CATEGORY,
            message="This order contains items from a non-returnable category (grocery) and is not eligible for refund.",
        )

    # 7. Amount Validation & Refundable Balance Calculation
    if isinstance(amount, float):
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.AMOUNT_INVALID,
            message="Invalid refund amount. Floating point numbers are not allowed; use exact decimal values.",
        )

    try:
        dec_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.AMOUNT_INVALID,
            message="Invalid refund amount format.",
        )

    # Quantize and check decimal places (at most 2 decimal places)
    if dec_amount <= 0 or dec_amount.as_tuple().exponent < -2:
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.AMOUNT_INVALID,
            message="Invalid refund amount. Amount must be positive and have at most 2 decimal places.",
        )

    dec_amount = dec_amount.quantize(Decimal("0.01"))

    # Sum of pending/approved/processed refunds
    existing_refunds_sum = db.scalar(
        select(func.coalesce(func.sum(Refund.amount), Decimal("0.00"))).where(
            Refund.order_id == order.id,
            Refund.status.in_([
                RefundStatus.PENDING_REVIEW,
                RefundStatus.APPROVED,
                RefundStatus.PROCESSED,
            ]),
        )
    ) or Decimal("0.00")

    refundable = order.total_amount - existing_refunds_sum

    if dec_amount > refundable:
        if refundable == Decimal("0.00"):
            _audit(
                db,
                actor_id=user.id,
                actor_type=ActorType.CUSTOMER,
                event_type="refund.rejected_by_policy",
                entity_id=order.id,
                metadata={"reason_code": ReasonCode.ALREADY_REFUNDED.value, "ticket_id": str(ticket_id) if ticket_id else None},
            )
            db.commit()
            return RefundResult(
                outcome=Outcome.REJECTED,
                reason_code=ReasonCode.ALREADY_REFUNDED,
                message="This order has already been fully refunded.",
            )

        _audit(
            db,
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="refund.rejected_by_policy",
            entity_id=order.id,
            metadata={"reason_code": ReasonCode.AMOUNT_EXCEEDS_REFUNDABLE.value, "ticket_id": str(ticket_id) if ticket_id else None},
        )
        db.commit()
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.AMOUNT_EXCEEDS_REFUNDABLE,
            message=f"Requested refund amount exceeds the remaining refundable amount of {refundable:.2f} INR.",
        )

    # 8. Check for active refund on order (partial unique index backstop)
    active_refund = db.scalar(
        select(Refund).where(
            Refund.order_id == order.id,
            Refund.status.in_([
                RefundStatus.PENDING_REVIEW,
                RefundStatus.APPROVED,
                RefundStatus.PROCESSED,
            ]),
        )
    )
    if active_refund is not None:
        return RefundResult(
            outcome=Outcome.REJECTED,
            reason_code=ReasonCode.ACTIVE_REFUND_EXISTS,
            refund=active_refund,
            message="An active refund request already exists for this order.",
        )

    # 9. Threshold Check: > 5000.00 INR -> Human Escalation Path
    if dec_amount > AUTO_REFUND_LIMIT:
        try:
            # Bind to ticket or create one
            bound_ticket_id = ticket_id
            if bound_ticket_id is None:
                new_ticket = Ticket(
                    customer_id=user.id,
                    order_id=order.id,
                    subject=f"Refund Escalation for Order {order.id}",
                    description=reason,
                    category=TicketCategory.REFUND,
                    status=TicketStatus.ESCALATED,
                    priority=TicketPriority.HIGH,
                )
                db.add(new_ticket)
                db.flush()
                bound_ticket_id = new_ticket.id
            else:
                existing_t = db.get(Ticket, bound_ticket_id)
                if existing_t:
                    existing_t.status = TicketStatus.ESCALATED
                    existing_t.priority = TicketPriority.HIGH

            refund = Refund(
                order_id=order.id,
                ticket_id=bound_ticket_id,
                amount=dec_amount,
                reason=reason,
                status=RefundStatus.PENDING_REVIEW,
                requested_by=user.id,
                idempotency_key=computed_key,
            )
            db.add(refund)
            db.flush()

            escalation = Escalation(
                ticket_id=bound_ticket_id,
                refund_id=refund.id,
                summary=(
                    f"Refund amount {dec_amount:.2f} INR exceeds auto-approval threshold of {AUTO_REFUND_LIMIT:.2f} INR. "
                    f"Customer: {user.id}, Order: {order.id}, Delivery: {order.delivery_date}. Pre-checks passed."
                ),
                priority=TicketPriority.HIGH,
                decision=EscalationDecision.PENDING,
            )
            db.add(escalation)

            _audit(db, user.id, ActorType.CUSTOMER, "refund.requested", refund.id, {"amount": str(dec_amount)})
            _audit(db, user.id, ActorType.CUSTOMER, "refund.escalated", refund.id, {"escalation_id": str(escalation.id)})

            db.commit()
            db.refresh(refund)
            db.refresh(escalation)

            logger.info(
                "refund_escalated",
                refund_id=str(refund.id),
                order_id=str(order.id),
                outcome=Outcome.ESCALATED.value,
            )
            return RefundResult(
                outcome=Outcome.ESCALATED,
                refund=refund,
                escalation=escalation,
                message="Your refund request exceeds the automatic approval limit and has been escalated for staff review.",
            )
        except IntegrityError:
            db.rollback()
            # Race condition caught by idempotency key or partial unique index
            dup = db.scalar(
                select(Refund).where(Refund.idempotency_key == computed_key)
            )
            if dup:
                return RefundResult(
                    outcome=Outcome.DUPLICATE,
                    refund=dup,
                    message="A refund request with this idempotency key has already been processed or submitted.",
                )
            active_race = db.scalar(
                select(Refund).where(
                    Refund.order_id == order.id,
                    Refund.status.in_([RefundStatus.PENDING_REVIEW, RefundStatus.APPROVED, RefundStatus.PROCESSED]),
                )
            )
            return RefundResult(
                outcome=Outcome.REJECTED,
                refund=active_race,
                reason_code=ReasonCode.ACTIVE_REFUND_EXISTS,
                message="An active refund request already exists for this order.",
            )

    # 10. Auto-Eligible Path (amount <= 5000.00 INR)
    try:
        refund = Refund(
            order_id=order.id,
            ticket_id=ticket_id,
            amount=dec_amount,
            reason=reason,
            status=RefundStatus.APPROVED,
            requested_by=user.id,
            idempotency_key=computed_key,
        )
        db.add(refund)
        db.flush()
        _audit(db, user.id, ActorType.CUSTOMER, "refund.requested", refund.id, {"amount": str(dec_amount)})
        db.commit()
        db.refresh(refund)
    except IntegrityError:
        db.rollback()
        dup = db.scalar(
            select(Refund).where(Refund.idempotency_key == computed_key)
        )
        if dup:
            return RefundResult(
                outcome=Outcome.DUPLICATE,
                refund=dup,
                message="A refund request with this idempotency key has already been processed or submitted.",
            )
        active_race = db.scalar(
            select(Refund).where(
                Refund.order_id == order.id,
                Refund.status.in_([RefundStatus.PENDING_REVIEW, RefundStatus.APPROVED, RefundStatus.PROCESSED]),
            )
        )
        return RefundResult(
            outcome=Outcome.REJECTED,
            refund=active_race,
            reason_code=ReasonCode.ACTIVE_REFUND_EXISTS,
            message="An active refund request already exists for this order.",
        )

    # Call payment mock (with 1 safe retry)
    payment_res = execute_refund_payment(refund.id, dec_amount)
    if not payment_res.success:
        # Retry once
        payment_res = execute_refund_payment(refund.id, dec_amount)

    if payment_res.success:
        # Transition to processed in a new transaction
        try:
            ref_row = db.get(Refund, refund.id)
            ref_row.status = RefundStatus.PROCESSED
            ref_row.payment_reference = payment_res.reference
            _audit(db, user.id, ActorType.CUSTOMER, "refund.processed", refund.id, {"reference": payment_res.reference})
            db.commit()
            db.refresh(refund)
            logger.info(
                "refund_processed",
                refund_id=str(refund.id),
                order_id=str(order.id),
                outcome=Outcome.PROCESSED.value,
            )
            return RefundResult(
                outcome=Outcome.PROCESSED,
                refund=refund,
                message="Refund processed successfully.",
            )
        except Exception as exc:
            db.rollback()
            logger.exception("refund_processed_db_error", refund_id=str(refund.id))
            raise

    # Payment failed after retry
    ref_row = db.get(Refund, refund.id)
    ref_row.status = RefundStatus.FAILED
    ref_row.failure_reason = payment_res.error
    ref_row.idempotency_key = f"{computed_key}:failed:{refund.id}"
    _audit(db, user.id, ActorType.CUSTOMER, "refund.failed", refund.id, {"error": payment_res.error})
    db.commit()
    db.refresh(refund)

    logger.warning(
        "refund_payment_failed",
        refund_id=str(refund.id),
        order_id=str(order.id),
        outcome=Outcome.ERROR.value,
        reason_code=ReasonCode.PAYMENT_FAILED.value,
    )
    return RefundResult(
        outcome=Outcome.ERROR,
        refund=refund,
        reason_code=ReasonCode.PAYMENT_FAILED,
        message="Payment processing failed for this refund. Please try again later.",
    )


def approve_escalated_refund(
    db: Session,
    staff_user: User,
    escalation_id: uuid.UUID,
    note: str | None = None,
) -> RefundResult:
    """Staff decision path to approve an escalated refund."""
    if staff_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise AppError(
            code="FORBIDDEN",
            message="Only staff agents or administrators can approve escalated refunds.",
            status_code=403,
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

    if escalation.refund_id is None:
        raise AppError(code="NOT_FOUND", message="No refund associated with this escalation.", status_code=404)

    refund = db.execute(
        select(Refund).where(Refund.id == escalation.refund_id).with_for_update()
    ).scalar_one()

    if refund.status == RefundStatus.PROCESSED:
        raise AppError(
            code="ALREADY_DECIDED",
            message="This refund has already been processed.",
            status_code=409,
        )

    order = db.execute(
        select(Order).where(Order.id == refund.order_id).with_for_update()
    ).scalar_one()

    # Re-verify order checks
    if order.status != OrderStatus.DELIVERED:
        raise AppError(code="ORDER_NOT_DELIVERED", message="Order is not in delivered status.", status_code=409)

    # Check available refundable amount excluding this refund row
    other_refunds_sum = db.scalar(
        select(func.coalesce(func.sum(Refund.amount), Decimal("0.00"))).where(
            Refund.order_id == order.id,
            Refund.id != refund.id,
            Refund.status.in_([RefundStatus.PENDING_REVIEW, RefundStatus.APPROVED, RefundStatus.PROCESSED]),
        )
    ) or Decimal("0.00")

    refundable = order.total_amount - other_refunds_sum
    if refund.amount > refundable:
        raise AppError(
            code="AMOUNT_EXCEEDS_REFUNDABLE",
            message=f"Refund amount exceeds the available refundable balance of {refundable:.2f} INR.",
            status_code=409,
        )

    # If the refund was previously marked failed, clean up any suffixed idempotency key
    if ":failed:" in refund.idempotency_key:
        clean_key = refund.idempotency_key.split(":failed:")[0]
        refund.idempotency_key = clean_key

    # Stage escalation as approved to serialize concurrent staff actions
    now = datetime.now(timezone.utc)
    escalation.decision = EscalationDecision.APPROVED
    escalation.decided_at = now
    escalation.assigned_to = staff_user.id
    if note:
        escalation.internal_note = note
    refund.status = RefundStatus.APPROVED
    refund.failure_reason = None
    refund.reviewed_by = staff_user.id

    _audit(db, staff_user.id, ActorType.STAFF, "refund.staff_approved", refund.id, {"note": note})
    db.commit()
    db.refresh(refund)

    # Dispatch payment
    payment_res = execute_refund_payment(refund.id, refund.amount)
    if not payment_res.success:
        payment_res = execute_refund_payment(refund.id, refund.amount)

    if payment_res.success:
        ref_row = db.get(Refund, refund.id)
        ref_row.status = RefundStatus.PROCESSED
        ref_row.payment_reference = payment_res.reference

        esc_row = db.get(Escalation, escalation.id)
        if esc_row.ticket_id:
            t = db.get(Ticket, esc_row.ticket_id)
            if t:
                t.status = TicketStatus.RESOLVED

        _audit(db, staff_user.id, ActorType.STAFF, "refund.processed", refund.id, {"reference": payment_res.reference})
        db.commit()
        db.refresh(refund)
        return RefundResult(
            outcome=Outcome.PROCESSED,
            refund=refund,
            message="Refund approved and payment processed successfully.",
        )

    # Payment failed again: revert escalation to PENDING to leave it open for retry
    ref_row = db.get(Refund, refund.id)
    ref_row.status = RefundStatus.FAILED
    ref_row.failure_reason = payment_res.error
    ref_row.idempotency_key = f"{refund.idempotency_key}:failed:{refund.id}"

    esc_row = db.get(Escalation, escalation.id)
    esc_row.decision = EscalationDecision.PENDING
    esc_row.decided_at = None

    _audit(db, staff_user.id, ActorType.STAFF, "refund.failed", refund.id, {"error": payment_res.error})
    db.commit()
    db.refresh(refund)
    return RefundResult(
        outcome=Outcome.ERROR,
        refund=refund,
        reason_code=ReasonCode.PAYMENT_FAILED,
        message="Refund was approved by staff, but payment processing failed. The refund was NOT completed.",
    )


def reject_refund(
    db: Session,
    staff_user: User,
    escalation_id: uuid.UUID,
    note: str,
    message_to_customer: str | None = None,
) -> RefundResult:
    """Staff decision path to reject an escalated refund."""
    if staff_user.role not in (UserRole.AGENT, UserRole.ADMIN):
        raise AppError(
            code="FORBIDDEN",
            message="Only staff agents or administrators can reject refunds.",
            status_code=403,
        )

    if not note or not note.strip():
        raise AppError(
            code="VALIDATION_ERROR",
            message="A mandatory note explaining the rejection reason must be provided.",
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

    if escalation.refund_id is None:
        raise AppError(code="NOT_FOUND", message="No refund associated with this escalation.", status_code=404)

    refund = db.execute(
        select(Refund).where(Refund.id == escalation.refund_id).with_for_update()
    ).scalar_one()

    now = datetime.now(timezone.utc)
    escalation.decision = EscalationDecision.REJECTED
    escalation.decided_at = now
    escalation.assigned_to = staff_user.id
    escalation.internal_note = note.strip()
    refund.status = RefundStatus.REJECTED
    refund.reviewed_by = staff_user.id

    if escalation.ticket_id:
        t = db.get(Ticket, escalation.ticket_id)
        if message_to_customer and message_to_customer.strip():
            staff_msg = Message(
                ticket_id=escalation.ticket_id,
                sender_type=SenderType.STAFF,
                sender_id=staff_user.id,
                content=message_to_customer.strip(),
            )
            db.add(staff_msg)
            if t:
                t.status = TicketStatus.RESOLVED
        else:
            sys_msg = Message(
                ticket_id=escalation.ticket_id,
                sender_type=SenderType.SYSTEM,
                sender_id=None,
                content=f"Refund request rejected by staff. Note: {note.strip()}",
            )
            db.add(sys_msg)
            if t:
                t.status = TicketStatus.CLOSED

    _audit(db, staff_user.id, ActorType.STAFF, "refund.staff_rejected", refund.id, {"note": note.strip()})
    db.commit()
    db.refresh(refund)

    return RefundResult(
        outcome=Outcome.REJECTED,
        refund=refund,
        message="Refund request has been rejected.",
    )

    _audit(db, staff_user.id, ActorType.STAFF, "refund.staff_rejected", refund.id, {"note": note.strip()})
    db.commit()
    db.refresh(refund)

    return RefundResult(
        outcome=Outcome.REJECTED,
        refund=refund,
        message="Refund request has been rejected.",
    )
