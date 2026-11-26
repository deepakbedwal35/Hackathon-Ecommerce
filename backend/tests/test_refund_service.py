from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
import uuid
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.errors import AppError
from app.models.enums import (
    ActorType,
    EscalationDecision,
    OrderStatus,
    RefundStatus,
    TicketStatus,
    UserRole,
)
from app.models.models import AuditEvent, Escalation, Order, Refund, Ticket, User
from app.services.payment_mock import clear_payment_mock_registry, _payment_registry
from app.services.refunds import (
    Outcome,
    ReasonCode,
    RefundResult,
    approve_escalated_refund,
    reject_refund,
    request_refund,
)
from scripts.seed import seed_database


@pytest.fixture(autouse=True)
def clean_payment_mock():
    """Resets mock payment registry and mode before and after each test."""
    clear_payment_mock_registry()
    original_mode = settings.PAYMENT_MOCK_MODE
    settings.PAYMENT_MOCK_MODE = "ok"
    yield
    clear_payment_mock_registry()
    settings.PAYMENT_MOCK_MODE = original_mode


@pytest.fixture
def seeded_db(db_session: Session) -> Session:
    """Pre-seeds the test database with standard seed data."""
    seed_database(reset=True, session=db_session)
    return db_session


def _get_user_by_email(db: Session, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def _get_order_by_amount(db: Session, amount: Decimal) -> Order:
    return db.scalar(select(Order).where(Order.total_amount == amount))


# ---------------------------------------------------------------------------
# 1. Order A: Auto-eligible happy path and Idempotency
# ---------------------------------------------------------------------------

def test_order_a_processed_successfully(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Earbuds defect on left side",
    )

    assert result.outcome == Outcome.PROCESSED
    assert result.refund is not None
    assert result.refund.status == RefundStatus.PROCESSED
    assert result.refund.payment_reference is not None
    assert len(result.refund.payment_reference) > 0

    # Verify exactly 1 refund row in database
    refunds = seeded_db.scalars(select(Refund).where(Refund.order_id == order_a.id)).all()
    assert len(refunds) == 1
    assert refunds[0].id == result.refund.id

    # Verify audit events present
    audits = seeded_db.scalars(
        select(AuditEvent).where(AuditEvent.entity_id == result.refund.id)
    ).all()
    event_types = [a.event_type for a in audits]
    assert "refund.requested" in event_types
    assert "refund.processed" in event_types


def test_order_a_idempotency_duplicate_submission(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))

    # First request
    res1 = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Earbuds defect",
        idempotency_key="idemp-key-order-a-1",
    )
    assert res1.outcome == Outcome.PROCESSED

    # Second request with identical key
    res2 = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Earbuds defect again",
        idempotency_key="idemp-key-order-a-1",
    )
    assert res2.outcome == Outcome.DUPLICATE
    assert res2.refund is not None
    assert res2.refund.id == res1.refund.id

    # Verify exactly 1 refund row and 1 mock payment in registry
    count = seeded_db.scalar(select(func.count(Refund.id)).where(Refund.order_id == order_a.id))
    assert count == 1
    assert len(_payment_registry) == 1


# ---------------------------------------------------------------------------
# 2. Concurrency: 10 concurrent requests for Order A
# ---------------------------------------------------------------------------

def test_10_concurrent_requests_for_order_a(setup_test_postgres, seeded_db: Session) -> None:
    engine = setup_test_postgres
    ThreadSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    cust1_id = _get_user_by_email(seeded_db, "customer1@example.com").id
    order_a_id = _get_order_by_amount(seeded_db, Decimal("1299.00")).id

    def worker(worker_id: int) -> RefundResult:
        with ThreadSession() as session:
            user = session.get(User, cust1_id)
            return request_refund(
                db=session,
                user=user,
                order_id=order_a_id,
                amount=Decimal("1299.00"),
                reason=f"Concurrent thread request {worker_id}",
                # Intentionally let sha256 or same key apply
                idempotency_key="concurrent-shared-key-10",
            )

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(worker, i) for i in range(10)]
        results = [f.result() for f in futures]

    # Verify results distribution: exactly 1 PROCESSED, remaining 9 are DUPLICATE
    processed = [r for r in results if r.outcome == Outcome.PROCESSED]
    duplicates = [r for r in results if r.outcome == Outcome.DUPLICATE]
    assert len(processed) == 1
    assert len(duplicates) == 9

    # Verify DB has exactly 1 refund row and payment mock has 1 record
    with ThreadSession() as verify_session:
        count = verify_session.scalar(
            select(func.count(Refund.id)).where(Refund.order_id == order_a_id)
        )
        assert count == 1
        assert len(_payment_registry) == 1


# ---------------------------------------------------------------------------
# 3. Order B: Return window expired, Day 30 vs Day 31 boundary
# ---------------------------------------------------------------------------

def test_order_b_return_window_expired(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_b = _get_order_by_amount(seeded_db, Decimal("2499.00"))

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_b.id,
        amount=Decimal("2499.00"),
        reason="Defective denim jacket",
    )

    assert result.outcome == Outcome.REJECTED
    assert result.reason_code == ReasonCode.RETURN_WINDOW_EXPIRED
    assert "30-day return window" in result.message
    assert result.refund is None

    # Verify 0 refund rows created
    count = seeded_db.scalar(select(func.count(Refund.id)).where(Refund.order_id == order_b.id))
    assert count == 0

    # Verify policy rejection audit event recorded
    audit = seeded_db.scalar(
        select(AuditEvent).where(
            AuditEvent.entity_id == order_b.id,
            AuditEvent.event_type == "refund.rejected_by_policy",
        )
    )
    assert audit is not None
    assert audit.audit_metadata["reason_code"] == ReasonCode.RETURN_WINDOW_EXPIRED.value


def test_return_window_boundary_day_30_allowed_day_31_rejected(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))
    delivery_date = order_a.delivery_date

    # Clock at day 30: exactly allowed
    day_30 = delivery_date + timedelta(days=30)
    res_day_30 = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("500.00"),
        reason="Partial return on day 30",
        idempotency_key="key-day-30",
        clock=lambda: day_30,
    )
    assert res_day_30.outcome == Outcome.PROCESSED

    # Reset refunds for clean test
    seeded_db.execute(select(Refund).where(Refund.order_id == order_a.id))
    for r in seeded_db.scalars(select(Refund).where(Refund.order_id == order_a.id)).all():
        seeded_db.delete(r)
    seeded_db.commit()

    # Clock at day 31: strictly rejected
    day_31 = delivery_date + timedelta(days=31)
    res_day_31 = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("500.00"),
        reason="Partial return on day 31",
        idempotency_key="key-day-31",
        clock=lambda: day_31,
    )
    assert res_day_31.outcome == Outcome.REJECTED
    assert res_day_31.reason_code == ReasonCode.RETURN_WINDOW_EXPIRED


# ---------------------------------------------------------------------------
# 4. Order C & Threshold boundaries (5000.00 vs 5000.01)
# ---------------------------------------------------------------------------

def test_order_c_escalation_above_5000(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_c = _get_order_by_amount(seeded_db, Decimal("8999.00"))

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="4K Smart TV screen is cracked",
    )

    assert result.outcome == Outcome.ESCALATED
    assert result.refund is not None
    assert result.refund.status == RefundStatus.PENDING_REVIEW
    assert result.escalation is not None
    assert result.escalation.decision == EscalationDecision.PENDING

    # Ensure mock payment was NOT called
    assert len(_payment_registry) == 0

    # Ensure bound ticket has escalated status
    ticket = seeded_db.get(Ticket, result.refund.ticket_id)
    assert ticket is not None
    assert ticket.status == TicketStatus.ESCALATED


def test_threshold_exact_5000_is_auto_5000_01_is_escalated(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_c = _get_order_by_amount(seeded_db, Decimal("8999.00"))

    # 5000.00 on order C -> auto-eligible (PROCESSED)
    res_auto = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("5000.00"),
        reason="Partial refund of 5000.00",
        idempotency_key="key-exact-5000",
    )
    assert res_auto.outcome == Outcome.PROCESSED
    assert res_auto.refund.status == RefundStatus.PROCESSED

    # Reset for 5000.01 test
    for r in seeded_db.scalars(select(Refund).where(Refund.order_id == order_c.id)).all():
        seeded_db.delete(r)
    seeded_db.commit()

    # 5000.01 on order C -> escalated
    res_esc = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("5000.01"),
        reason="Partial refund of 5000.01",
        idempotency_key="key-5000-01",
    )
    assert res_esc.outcome == Outcome.ESCALATED
    assert res_esc.refund.status == RefundStatus.PENDING_REVIEW


# ---------------------------------------------------------------------------
# 5. Partial amounts & Balance validation
# ---------------------------------------------------------------------------

def test_partial_amount_and_exceeding_balance(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))

    # Partial refund of 500.00 works
    res_partial = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("500.00"),
        reason="Partial refund of 500",
        idempotency_key="key-partial-500",
    )
    assert res_partial.outcome == Outcome.PROCESSED

    # Reset to test exceeding balance on fresh order
    for r in seeded_db.scalars(select(Refund).where(Refund.order_id == order_a.id)).all():
        seeded_db.delete(r)
    seeded_db.commit()

    # Amount 1300.00 > total 1299.00 is rejected
    res_exceeds = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1300.00"),
        reason="Exceeds total order amount",
        idempotency_key="key-exceeds-total",
    )
    assert res_exceeds.outcome == Outcome.REJECTED
    assert res_exceeds.reason_code == ReasonCode.AMOUNT_EXCEEDS_REFUNDABLE


# ---------------------------------------------------------------------------
# 6. Status & Category rejections: D, E, G, F
# ---------------------------------------------------------------------------

def test_order_d_shipped_not_delivered(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_d = _get_order_by_amount(seeded_db, Decimal("799.00"))
    assert order_d.status == OrderStatus.SHIPPED

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_d.id,
        amount=Decimal("799.00"),
        reason="Want to cancel shipped order",
    )
    assert result.outcome == Outcome.REJECTED
    assert result.reason_code == ReasonCode.ORDER_NOT_DELIVERED


def test_order_e_already_refunded(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_e = _get_order_by_amount(seeded_db, Decimal("1599.00"))

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_e.id,
        amount=Decimal("1599.00"),
        reason="Requesting refund on already refunded order",
    )
    assert result.outcome == Outcome.REJECTED
    assert result.reason_code == ReasonCode.ALREADY_REFUNDED


def test_order_g_non_returnable_grocery_category(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_g = _get_order_by_amount(seeded_db, Decimal("450.00"))

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_g.id,
        amount=Decimal("450.00"),
        reason="Tea leaves taste different than expected",
    )
    assert result.outcome == Outcome.REJECTED
    assert result.reason_code == ReasonCode.NON_RETURNABLE_CATEGORY


def test_customer1_requesting_customer2_order_f_returns_not_found(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_f = _get_order_by_amount(seeded_db, Decimal("1999.00"))  # belongs to cust2

    res_f = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_f.id,
        amount=Decimal("1999.00"),
        reason="Attempting refund on other customer order",
    )
    assert res_f.outcome == Outcome.REJECTED
    assert res_f.reason_code == ReasonCode.NOT_FOUND

    # Compare message with non-existent random UUID
    random_id = uuid.uuid4()
    res_rand = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=random_id,
        amount=Decimal("1999.00"),
        reason="Non-existent order",
    )
    assert res_rand.outcome == Outcome.REJECTED
    assert res_rand.reason_code == ReasonCode.NOT_FOUND
    assert res_f.message == res_rand.message


# ---------------------------------------------------------------------------
# 7. Amount validation: float, negative, zero, 3-decimals
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "bad_amount",
    [
        1299.00,                 # raw Python float
        Decimal("-10.00"),       # negative
        Decimal("0.00"),         # zero
        Decimal("1299.999"),     # 3 decimals
    ],
)
def test_invalid_amounts_rejected(seeded_db: Session, bad_amount) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=bad_amount,
        reason="Testing invalid amount inputs",
    )
    assert result.outcome == Outcome.REJECTED
    assert result.reason_code == ReasonCode.AMOUNT_INVALID


# ---------------------------------------------------------------------------
# 8. Mock payment modes: fail, fail_once, retry recovery
# ---------------------------------------------------------------------------

def test_mock_payment_fail_mode_and_retry_recovery(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))

    # Set mock mode to 'fail'
    settings.PAYMENT_MOCK_MODE = "fail"

    res_fail = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Earbuds defect - failure test",
        idempotency_key="key-fail-test",
    )
    assert res_fail.outcome == Outcome.ERROR
    assert res_fail.reason_code == ReasonCode.PAYMENT_FAILED
    assert res_fail.refund.status == RefundStatus.FAILED
    assert res_fail.refund.failure_reason is not None

    # Switch back to 'ok' and retry with the same key
    settings.PAYMENT_MOCK_MODE = "ok"
    clear_payment_mock_registry()

    res_retry = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Earbuds defect - retry after failure",
        idempotency_key="key-fail-test",
    )
    assert res_retry.outcome == Outcome.PROCESSED
    assert res_retry.refund.status == RefundStatus.PROCESSED

    # Exactly 1 processed refund row in DB
    processed_count = seeded_db.scalar(
        select(func.count(Refund.id)).where(
            Refund.order_id == order_a.id,
            Refund.status == RefundStatus.PROCESSED,
        )
    )
    assert processed_count == 1


def test_mock_payment_fail_once_internal_retry_succeeds(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))

    settings.PAYMENT_MOCK_MODE = "fail_once"

    result = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Earbuds defect with transient payment timeout",
    )
    assert result.outcome == Outcome.PROCESSED
    assert result.refund.status == RefundStatus.PROCESSED
    assert result.refund.payment_reference is not None


# ---------------------------------------------------------------------------
# 9. DB crash mid-flow (monkeypatch)
# ---------------------------------------------------------------------------

def test_db_failure_injected_mid_flow_no_false_success(seeded_db: Session, monkeypatch) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    order_a = _get_order_by_amount(seeded_db, Decimal("1299.00"))

    # Monkeypatch execute_refund_payment to raise an unexpected runtime error
    def crashing_payment(*args, **kwargs):
        raise RuntimeError("Unexpected infrastructure network drop")

    monkeypatch.setattr("app.services.refunds.execute_refund_payment", crashing_payment)

    with pytest.raises(RuntimeError):
        request_refund(
            db=seeded_db,
            user=cust1,
            order_id=order_a.id,
            amount=Decimal("1299.00"),
            reason="Earbuds defect crash test",
        )

    # Verify no refund reached PROCESSED status
    processed = seeded_db.scalar(
        select(Refund).where(
            Refund.order_id == order_a.id,
            Refund.status == RefundStatus.PROCESSED,
        )
    )
    assert processed is None


# ---------------------------------------------------------------------------
# 10. Staff decision paths: approve and reject
# ---------------------------------------------------------------------------

def test_staff_approve_escalated_refund_and_edge_cases(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    admin = _get_user_by_email(seeded_db, "admin1@example.com")
    order_c = _get_order_by_amount(seeded_db, Decimal("8999.00"))

    # Customer creates an escalated refund (> 5000)
    res_esc = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on Smart TV",
    )
    assert res_esc.outcome == Outcome.ESCALATED
    escalation_id = res_esc.escalation.id

    # Customer trying to approve -> FORBIDDEN (403)
    with pytest.raises(AppError) as exc_cust:
        approve_escalated_refund(
            db=seeded_db,
            staff_user=cust1,
            escalation_id=escalation_id,
            note="Customer self-approving",
        )
    assert exc_cust.value.status_code == 403
    assert exc_cust.value.code == "FORBIDDEN"

    # Admin approves -> PROCESSED
    res_app = approve_escalated_refund(
        db=seeded_db,
        staff_user=admin,
        escalation_id=escalation_id,
        note="Approved replacement TV refund after inspecting photos",
    )
    assert res_app.outcome == Outcome.PROCESSED
    assert res_app.refund.status == RefundStatus.PROCESSED
    assert res_app.refund.reviewed_by == admin.id
    assert res_app.refund.payment_reference is not None

    # Approving twice -> 409 ALREADY_DECIDED
    with pytest.raises(AppError) as exc_dup:
        approve_escalated_refund(
            db=seeded_db,
            staff_user=admin,
            escalation_id=escalation_id,
            note="Approving second time",
        )
    assert exc_dup.value.status_code == 409
    assert exc_dup.value.code == "ALREADY_DECIDED"


def test_staff_approve_rechecks_available_balance(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    admin = _get_user_by_email(seeded_db, "admin1@example.com")
    order_c = _get_order_by_amount(seeded_db, Decimal("8999.00"))

    # Customer creates an escalated refund for 6000.00
    res_esc = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("6000.00"),
        reason="Partial high-value refund",
    )
    assert res_esc.outcome == Outcome.ESCALATED
    escalation_id = res_esc.escalation.id

    # Artificially shrink order's total amount so refund exceeds it
    order_c.total_amount = Decimal("5500.00")
    seeded_db.commit()

    # Staff approval re-checks balance -> 409 AMOUNT_EXCEEDS_REFUNDABLE
    with pytest.raises(AppError) as exc_bal:
        approve_escalated_refund(
            db=seeded_db,
            staff_user=admin,
            escalation_id=escalation_id,
            note="Attempting to approve after balance reduced",
        )
    assert exc_bal.value.status_code == 409
    assert exc_bal.value.code == "AMOUNT_EXCEEDS_REFUNDABLE"


def test_staff_reject_requires_note_and_updates_ticket(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    admin = _get_user_by_email(seeded_db, "admin1@example.com")
    order_c = _get_order_by_amount(seeded_db, Decimal("8999.00"))

    res_esc = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on Smart TV",
    )
    escalation_id = res_esc.escalation.id
    ticket_id = res_esc.refund.ticket_id

    # Rejection without note -> 422 VALIDATION_ERROR
    with pytest.raises(AppError) as exc_note:
        reject_refund(
            db=seeded_db,
            staff_user=admin,
            escalation_id=escalation_id,
            note="   ",
        )
    assert exc_note.value.status_code == 422

    # Rejection with note -> REJECTED
    res_rej = reject_refund(
        db=seeded_db,
        staff_user=admin,
        escalation_id=escalation_id,
        note="Customer damaged device due to improper wall mount installation.",
    )
    assert res_rej.outcome == Outcome.REJECTED
    assert res_rej.refund.status == RefundStatus.REJECTED
    assert res_rej.refund.reviewed_by == admin.id

    # Ticket closed with system message
    ticket = seeded_db.get(Ticket, ticket_id)
    assert ticket.status == TicketStatus.CLOSED
    sys_msgs = [m for m in ticket.messages if m.sender_type.value == "system"]
    assert len(sys_msgs) >= 1
    assert "improper wall mount" in sys_msgs[-1].content
