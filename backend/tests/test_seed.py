from decimal import Decimal
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.enums import OrderStatus, RefundStatus
from app.models.models import (
    Message,
    Order,
    OrderItem,
    Refund,
    Ticket,
    User,
)
from scripts.seed import seed_database


def test_seed_idempotency_and_row_counts(db_session: Session) -> None:
    """Proves that running the seed script multiple times does not duplicate data."""
    # Run seed first time
    seed_database(reset=True)

    users_count_1 = db_session.scalar(select(func.count(User.id)))
    orders_count_1 = db_session.scalar(select(func.count(Order.id)))
    items_count_1 = db_session.scalar(select(func.count(OrderItem.id)))
    refunds_count_1 = db_session.scalar(select(func.count(Refund.id)))
    tickets_count_1 = db_session.scalar(select(func.count(Ticket.id)))
    messages_count_1 = db_session.scalar(select(func.count(Message.id)))

    assert users_count_1 == 4  # 2 customers, 1 agent, 1 admin
    assert orders_count_1 == 7  # Orders A through G

    # Run seed second time without reset
    seed_database(reset=False)

    users_count_2 = db_session.scalar(select(func.count(User.id)))
    orders_count_2 = db_session.scalar(select(func.count(Order.id)))
    items_count_2 = db_session.scalar(select(func.count(OrderItem.id)))
    refunds_count_2 = db_session.scalar(select(func.count(Refund.id)))
    tickets_count_2 = db_session.scalar(select(func.count(Ticket.id)))
    messages_count_2 = db_session.scalar(select(func.count(Message.id)))

    assert users_count_1 == users_count_2
    assert orders_count_1 == orders_count_2
    assert items_count_1 == items_count_2
    assert refunds_count_1 == refunds_count_2
    assert tickets_count_1 == tickets_count_2
    assert messages_count_1 == messages_count_2


def test_seed_seven_orders_match_expected_criteria(db_session: Session) -> None:
    """Proves the 7 seeded orders exist with exact amounts, statuses, and scenarios."""
    seed_database(reset=True)

    orders = db_session.scalars(select(Order).order_by(Order.total_amount)).all()
    assert len(orders) == 7

    # Verify statuses
    delivered_orders = [o for o in orders if o.status == OrderStatus.DELIVERED]
    shipped_orders = [o for o in orders if o.status == OrderStatus.SHIPPED]
    assert len(delivered_orders) == 6
    assert len(shipped_orders) == 1

    amounts = {o.total_amount for o in orders}
    expected_amounts = {
        Decimal("450.00"),   # Order G: Grocery
        Decimal("799.00"),   # Order D: Shipped
        Decimal("1299.00"),  # Order A: Electronics eligible
        Decimal("1599.00"),  # Order E: Processed refund
        Decimal("1999.00"),  # Order F: Customer 2
        Decimal("2499.00"),  # Order B: Expired return window
        Decimal("8999.00"),  # Order C: High-value escalation (>5000)
    }
    assert amounts == expected_amounts

    # Check Order E has a processed refund
    order_e = next(o for o in orders if o.total_amount == Decimal("1599.00"))
    assert len(order_e.refunds) == 1
    assert order_e.refunds[0].status == RefundStatus.PROCESSED
