from datetime import date, datetime, timezone
from decimal import Decimal
import uuid
import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.enums import (
    ItemCategory,
    OrderStatus,
    RefundStatus,
    UserRole,
)
from app.models.models import (
    Order,
    OrderItem,
    Refund,
    User,
)


def create_user(
    session: Session, email: str = "customer@example.com", name: str = "Test User"
) -> User:
    user = User(
        name=name,
        email=email,
        password_hash="argon2id$hashed",
        role=UserRole.CUSTOMER,
    )
    session.add(user)
    session.commit()
    return user


def create_order(
    session: Session,
    customer_id: uuid.UUID,
    total_amount: Decimal = Decimal("1000.00"),
    status: OrderStatus = OrderStatus.DELIVERED,
) -> Order:
    order = Order(
        customer_id=customer_id,
        status=status,
        delivery_date=date.today(),
        total_amount=total_amount,
    )
    session.add(order)
    session.commit()
    return order


def test_duplicate_email_rejected_case_insensitive(db_session: Session) -> None:
    """Proves duplicate emails are rejected case-insensitively by lower(email) unique index."""
    create_user(db_session, email="customer@example.com")

    # Try inserting same email with mixed uppercase
    duplicate = User(
        name="Duplicate User",
        email="CUSTOMER@EXAMPLE.COM",
        password_hash="argon2id$hash",
        role=UserRole.CUSTOMER,
    )
    db_session.add(duplicate)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "ix_users_email" in str(exc_info.value).lower()
    db_session.rollback()


def test_two_active_refunds_on_same_order_rejected(db_session: Session) -> None:
    """Proves partial unique index blocks two active refunds on the same order."""
    user = create_user(db_session)
    order = create_order(db_session, user.id)

    # First active refund (pending_review)
    refund_1 = Refund(
        order_id=order.id,
        amount=Decimal("500.00"),
        reason="Defective product",
        status=RefundStatus.PENDING_REVIEW,
        requested_by=user.id,
        idempotency_key="idemp_key_1",
    )
    db_session.add(refund_1)
    db_session.commit()

    # Second active refund on same order (approved)
    refund_2 = Refund(
        order_id=order.id,
        amount=Decimal("500.00"),
        reason="Duplicate refund request",
        status=RefundStatus.APPROVED,
        requested_by=user.id,
        idempotency_key="idemp_key_2",
    )
    db_session.add(refund_2)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "uq_refunds_one_active_per_order" in str(exc_info.value).lower()
    db_session.rollback()


def test_failed_or_rejected_refund_plus_new_active_refund_allowed(
    db_session: Session,
) -> None:
    """Proves that an order with a rejected or failed refund CAN receive a new active refund."""
    user = create_user(db_session)
    order = create_order(db_session, user.id)

    # Inactive / terminal refund (rejected)
    refund_rejected = Refund(
        order_id=order.id,
        amount=Decimal("500.00"),
        reason="Claim invalid",
        status=RefundStatus.REJECTED,
        requested_by=user.id,
        idempotency_key="idemp_rejected_1",
    )
    db_session.add(refund_rejected)
    db_session.commit()

    # New active refund on the same order should succeed
    refund_active = Refund(
        order_id=order.id,
        amount=Decimal("500.00"),
        reason="Customer re-applied with valid receipt",
        status=RefundStatus.PENDING_REVIEW,
        requested_by=user.id,
        idempotency_key="idemp_active_2",
    )
    db_session.add(refund_active)
    db_session.commit()

    assert refund_active.id is not None


def test_duplicate_idempotency_key_rejected(db_session: Session) -> None:
    """Proves idempotency_key must be globally unique across refunds."""
    user = create_user(db_session)
    order_1 = create_order(db_session, user.id)
    order_2 = create_order(db_session, user.id)

    refund_1 = Refund(
        order_id=order_1.id,
        amount=Decimal("100.00"),
        reason="Return item",
        status=RefundStatus.PENDING_REVIEW,
        requested_by=user.id,
        idempotency_key="reused_idempotency_token",
    )
    db_session.add(refund_1)
    db_session.commit()

    refund_2 = Refund(
        order_id=order_2.id,
        amount=Decimal("200.00"),
        reason="Different order, same key",
        status=RefundStatus.PENDING_REVIEW,
        requested_by=user.id,
        idempotency_key="reused_idempotency_token",
    )
    db_session.add(refund_2)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "uq_refunds_idempotency_key" in str(exc_info.value).lower()
    db_session.rollback()


def test_negative_total_amount_rejected(db_session: Session) -> None:
    """Proves orders.total_amount CHECK constraint (>= 0)."""
    user = create_user(db_session)
    invalid_order = Order(
        customer_id=user.id,
        status=OrderStatus.PLACED,
        total_amount=Decimal("-15.00"),
    )
    db_session.add(invalid_order)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "ck_orders_total_amount_positive" in str(exc_info.value).lower()
    db_session.rollback()


def test_zero_or_negative_refund_amount_rejected(db_session: Session) -> None:
    """Proves refunds.amount CHECK constraint (> 0)."""
    user = create_user(db_session)
    order = create_order(db_session, user.id)

    zero_refund = Refund(
        order_id=order.id,
        amount=Decimal("0.00"),
        reason="Zero amount test",
        status=RefundStatus.PENDING_REVIEW,
        requested_by=user.id,
        idempotency_key="idemp_zero_amount",
    )
    db_session.add(zero_refund)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.commit()

    assert "ck_refunds_amount_positive" in str(exc_info.value).lower()
    db_session.rollback()


def test_deleting_user_with_refunds_blocked_by_restrict(
    db_session: Session,
) -> None:
    """Proves ON DELETE RESTRICT blocks deleting a user referenced by financial records."""
    user = create_user(db_session)
    order = create_order(db_session, user.id)

    refund = Refund(
        order_id=order.id,
        amount=Decimal("150.00"),
        reason="Financial record",
        status=RefundStatus.PENDING_REVIEW,
        requested_by=user.id,
        idempotency_key="idemp_restrict_test",
    )
    db_session.add(refund)
    db_session.commit()

    # Attempt to delete user directly
    db_session.delete(user)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_order_with_refunds_blocked_by_restrict(
    db_session: Session,
) -> None:
    """Proves ON DELETE RESTRICT blocks deleting an order referenced by a refund."""
    user = create_user(db_session)
    order = create_order(db_session, user.id)

    refund = Refund(
        order_id=order.id,
        amount=Decimal("150.00"),
        reason="Financial record",
        status=RefundStatus.PENDING_REVIEW,
        requested_by=user.id,
        idempotency_key="idemp_restrict_order_test",
    )
    db_session.add(refund)
    db_session.commit()

    # Attempt to delete order directly
    db_session.delete(order)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
