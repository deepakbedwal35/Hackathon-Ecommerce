import uuid
from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.models.enums import UserRole
from app.models.models import Order, Ticket, User


def get_order_for_user(db: Session, user: User, order_id: uuid.UUID) -> Order:
    """
    Fetches an order enforcing tenant boundary ownership.
    Customers can only access their own orders (customer_id == user.id).
    Staff (agent, admin) can access any order.
    Returns 404 NOT_FOUND with an identical message whether the record belongs
    to another user or does not exist at all, preventing existence leakage.
    """
    stmt = select(Order).where(Order.id == order_id)
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
