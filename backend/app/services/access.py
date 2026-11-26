import uuid
from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import UserRole
from app.models.models import Order, Ticket, User


def get_order_for_user(db: Session, user: User, order_id: uuid.UUID | str) -> Order:
    """
    Fetches an order enforcing tenant boundary ownership.
    Accepts either a UUID (or UUID string) or human-readable order_number (e.g. 'ORD-1001').
    Customers can only access their own orders (customer_id == user.id).
    Staff (agent, admin) can access any order.
    Returns 404 NOT_FOUND with an identical message whether the record belongs
    to another user or does not exist at all, preventing existence leakage.
    """
    from sqlalchemy import func, or_

    target_uuid: uuid.UUID | None = None
    target_num: str | None = None

    if isinstance(order_id, uuid.UUID):
        target_uuid = order_id
    elif isinstance(order_id, str):
        cleaned = order_id.strip()
        try:
            target_uuid = uuid.UUID(cleaned)
        except (ValueError, AttributeError):
            target_uuid = None
        target_num = cleaned
    else:
        raise AppError(
            code="NOT_FOUND",
            message="Order not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if target_uuid is not None and target_num is not None:
        stmt = select(Order).where(
            or_(Order.id == target_uuid, func.lower(Order.order_number) == target_num.lower())
        )
    elif target_uuid is not None:
        stmt = select(Order).where(Order.id == target_uuid)
    elif target_num is not None:
        stmt = select(Order).where(func.lower(Order.order_number) == target_num.lower())
    else:
        raise AppError(
            code="NOT_FOUND",
            message="Order not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )

    if user.role == UserRole.CUSTOMER:
        stmt = stmt.where(Order.customer_id == user.id)

    order = db.scalar(stmt)
    if order is None:
        raise AppError(
            code="NOT_FOUND",
            message="Order not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return order


def get_ticket_for_user(db: Session, user: User, ticket_id: uuid.UUID) -> Ticket:
    """
    Fetches a ticket enforcing tenant boundary ownership.
    Customers can only access their own tickets (customer_id == user.id).
    Staff (agent, admin) can access any ticket.
    Returns 404 NOT_FOUND with an identical message if missing or unauthorized.
    """
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    if user.role == UserRole.CUSTOMER:
        stmt = stmt.where(Ticket.customer_id == user.id)

    ticket = db.scalar(stmt)
    if ticket is None:
        raise AppError(
            code="NOT_FOUND",
            message="Ticket not found",
            status_code=status.HTTP_404_NOT_FOUND,
        )
    return ticket
