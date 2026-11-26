from datetime import timedelta
from decimal import Decimal
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.db import get_db
from app.core.deps import require_customer
from app.core.policy import NON_RETURNABLE_CATEGORIES, RETURN_WINDOW_DAYS, get_today_date
from app.models.enums import OrderStatus, RefundStatus
from app.models.models import Order, Refund, User
from app.schemas.orders import CustomerOrderDetail, CustomerOrderItemRead, CustomerOrderListItem
from app.schemas.refunds import RefundRead
from app.services.access import get_order_for_user

router = APIRouter(tags=["Customer Orders"])


def _compute_order_refund_status(refunds: list[Refund]) -> str | None:
    if not refunds:
        return None
    for r in refunds:
        if r.status == RefundStatus.PROCESSED:
            return "Refunded"
        if r.status in (RefundStatus.PENDING_REVIEW, RefundStatus.APPROVED):
            return "Refund pending"
    for r in refunds:
        if r.status == RefundStatus.REJECTED:
            return "Refund rejected"
    return None


@router.get("", response_model=list[CustomerOrderListItem])
def list_customer_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """Lists all orders belonging to the authenticated customer."""
    today = get_today_date()
    stmt = (
        select(Order)
        .where(Order.customer_id == current_user.id)
        .options(
            selectinload(Order.items),
            selectinload(Order.refunds),
        )
        .order_by(Order.created_at.desc())
    )
    orders = db.scalars(stmt).all()

    items = []
    for o in orders:
        is_returnable = False
        if o.status == OrderStatus.DELIVERED and o.delivery_date:
            last_date = o.delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
            has_non_returnable = any(it.category.value in NON_RETURNABLE_CATEGORIES for it in o.items)
            is_returnable = today <= last_date and not has_non_returnable

        items.append(
            CustomerOrderListItem(
                id=o.id,
                order_number=o.order_number,
                status=o.status,
                total_amount=o.total_amount,
                delivery_date=o.delivery_date,
                created_at=o.created_at,
                item_count=len(o.items),
                refund_status=_compute_order_refund_status(o.refunds),
                is_returnable=is_returnable,
            )
        )
    return items


@router.get("/{order_id}", response_model=CustomerOrderDetail)
def get_customer_order(
    order_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_customer),
):
    """
    Retrieves full order details including line items, past refunds,
    remaining refundable balance, and return window eligibility.
    Accepts either UUID or human-readable order_number (e.g. 'ORD-1001').
    """
    order = get_order_for_user(db, current_user, order_id)
    db.refresh(order, ["items", "refunds"])

    today = get_today_date()
    is_returnable = False
    last_eligible_date = None

    if order.status == OrderStatus.DELIVERED and order.delivery_date:
        last_eligible_date = order.delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
        has_non_returnable = any(it.category.value in NON_RETURNABLE_CATEGORIES for it in order.items)
        is_returnable = today <= last_eligible_date and not has_non_returnable

    # Calculate remaining refundable balance
    refunded_sum = sum(
        r.amount for r in order.refunds
        if r.status in (RefundStatus.PENDING_REVIEW, RefundStatus.APPROVED, RefundStatus.PROCESSED)
    )
    refundable = max(Decimal("0.00"), order.total_amount - refunded_sum)

    return CustomerOrderDetail(
        id=order.id,
        order_number=order.order_number,
        status=order.status,
        total_amount=order.total_amount,
        delivery_date=order.delivery_date,
        created_at=order.created_at,
        items=[
            CustomerOrderItemRead(
                id=it.id,
                name=it.name,
                category=it.category,
                quantity=it.quantity,
                unit_price=it.unit_price,
            )
            for it in order.items
        ],
        refunds=[RefundRead.model_validate(r) for r in order.refunds],
        is_returnable=is_returnable,
        last_eligible_date=last_eligible_date,
        refundable_amount=refundable,
    )
