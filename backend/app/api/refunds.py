import uuid
from fastapi import APIRouter, Depends, Header, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.deps import require_customer
from app.core.errors import AppError
from app.models.models import Order, Refund, User
from app.schemas.refunds import RefundCreate, RefundRead
from app.services.refunds import Outcome, ReasonCode, request_refund

router = APIRouter(tags=["Refunds"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=RefundRead)
def create_refund(
    payload: RefundCreate,
    response: Response,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """
    Requests a refund for a delivered customer order.
    Executes through a single validated pipeline enforcing policy rules,
    row-level serialization, and payment rails simulation.
    """
    result = request_refund(
        db=db,
        user=current_user,
        order_id=payload.order_id,
        amount=payload.amount,
        reason=payload.reason,
        ticket_id=payload.ticket_id,
        idempotency_key=idempotency_key,
    )

    if result.outcome == Outcome.PROCESSED:
        response.status_code = status.HTTP_201_CREATED
        return result.refund
    elif result.outcome == Outcome.ESCALATED:
        response.status_code = status.HTTP_202_ACCEPTED
        return result.refund
    elif result.outcome == Outcome.DUPLICATE:
        response.status_code = status.HTTP_200_OK
        return result.refund
    elif result.outcome == Outcome.REJECTED:
        if result.reason_code == ReasonCode.NOT_FOUND:
            raise AppError(
                code="NOT_FOUND",
                message=result.message,
                status_code=status.HTTP_404_NOT_FOUND,
            )
        raise AppError(
            code=result.reason_code.value if result.reason_code else "REFUND_REJECTED",
            message=result.message,
            status_code=status.HTTP_409_CONFLICT,
        )
    elif result.outcome == Outcome.ERROR:
        raise AppError(
            code=result.reason_code.value if result.reason_code else "PAYMENT_FAILED",
            message=result.message or "Refund processing failed. The refund was NOT completed.",
            status_code=status.HTTP_502_BAD_GATEWAY,
        )

    raise AppError(
        code="INTERNAL_ERROR",
        message="An unexpected error occurred. The refund was NOT completed.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )


@router.get("", response_model=list[RefundRead])
def list_refunds(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """
    Lists all refunds belonging to the authenticated customer.
    Enforces tenant boundaries by joining against the customer's orders.
    """
    stmt = (
        select(Refund)
        .join(Order, Refund.order_id == Order.id)
        .where(Order.customer_id == current_user.id)
        .order_by(Refund.created_at.desc())
    )
    return db.scalars(stmt).all()


@router.get("/{refund_id}", response_model=RefundRead)
def get_refund(
    refund_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """
    Retrieves a specific refund by ID for the authenticated customer.
    Returns 404 NOT_FOUND if the refund does not exist or belongs to another user.
    """
    stmt = (
        select(Refund)
        .join(Order, Refund.order_id == Order.id)
        .where(Order.customer_id == current_user.id, Refund.id == refund_id)
    )
    refund = db.scalar(stmt)
    if refund is None:
        raise AppError(
            code="NOT_FOUND",
            message="Refund not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return refund
