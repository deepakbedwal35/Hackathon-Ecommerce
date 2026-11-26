from decimal import Decimal
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token
from app.models.enums import RefundStatus
from app.models.models import Order, Refund, User
from app.services.payment_mock import clear_payment_mock_registry
from scripts.seed import seed_database


@pytest.fixture(autouse=True)
def clean_mock_and_seed(db_session: Session):
    """Pre-seeds test DB and resets payment mock registry before each test."""
    clear_payment_mock_registry()
    original_mode = settings.PAYMENT_MOCK_MODE
    settings.PAYMENT_MOCK_MODE = "ok"
    seed_database(reset=True, session=db_session)
    yield
    clear_payment_mock_registry()
    settings.PAYMENT_MOCK_MODE = original_mode


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _get_user_by_email(db: Session, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


def _get_order_by_amount(db: Session, amount: Decimal) -> Order:
    return db.scalar(select(Order).where(Order.total_amount == amount))


# ---------------------------------------------------------------------------
# 1. Authentication & RBAC Guards
# ---------------------------------------------------------------------------

def test_unauthenticated_requests_return_401(client: TestClient, db_session: Session) -> None:
    order_a = _get_order_by_amount(db_session, Decimal("1299.00"))

    # POST /refunds without token
    res_post = client.post(
        "/api/v1/refunds",
        json={"order_id": str(order_a.id), "amount": "1299.00", "reason": "Defective earbuds"},
    )
    assert res_post.status_code == 401
    assert res_post.json()["error"]["code"] == "NOT_AUTHENTICATED"

    # GET /refunds without token
    res_list = client.get("/api/v1/refunds")
    assert res_list.status_code == 401

    # GET /refunds/{id} without token
    res_get = client.get(f"/api/v1/refunds/{uuid.uuid4()}")
    assert res_get.status_code == 401


def test_staff_agent_forbidden_on_customer_endpoints(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    order_a = _get_order_by_amount(db_session, Decimal("1299.00"))

    res = client.post(
        "/api/v1/refunds",
        headers=_auth_header(agent),
        json={"order_id": str(order_a.id), "amount": "1299.00", "reason": "Agent cannot request"},
    )
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_client_cannot_inject_status_or_forbidden_fields(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    order_a = _get_order_by_amount(db_session, Decimal("1299.00"))

    # Attempting to inject "status": "processed" -> 422
    res_status = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(order_a.id),
            "amount": "1299.00",
            "reason": "Attempting exploit",
            "status": "processed",
        },
    )
    assert res_status.status_code == 422
    assert res_status.json()["error"]["code"] == "VALIDATION_ERROR"

    # Attempting to inject "reviewed_by" -> 422
    res_reviewed = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(order_a.id),
            "amount": "1299.00",
            "reason": "Attempting exploit",
            "reviewed_by": str(cust1.id),
        },
    )
    assert res_reviewed.status_code == 422


# ---------------------------------------------------------------------------
# 2. HTTP Status Code Mapping: 201, 200, 202, 404, 409, 502
# ---------------------------------------------------------------------------

def test_api_outcome_201_processed(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    order_a = _get_order_by_amount(db_session, Decimal("1299.00"))

    response = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(order_a.id),
            "amount": "1299.00",
            "reason": "Earbuds defect on left speaker",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "processed"
    assert data["progress"] == "Completed"
    assert data["payment_reference"] is not None
    assert Decimal(str(data["amount"])) == Decimal("1299.00")


def test_api_outcome_200_duplicate(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    order_a = _get_order_by_amount(db_session, Decimal("1299.00"))

    headers = _auth_header(cust1)
    headers["Idempotency-Key"] = "client-custom-header-key-99"

    # First submission -> 201
    res1 = client.post(
        "/api/v1/refunds",
        headers=headers,
        json={
            "order_id": str(order_a.id),
            "amount": "1299.00",
            "reason": "Earbuds defect submission one",
        },
    )
    assert res1.status_code == 201
    refund_id_1 = res1.json()["id"]

    # Second submission with same Idempotency-Key header -> 200 DUPLICATE
    res2 = client.post(
        "/api/v1/refunds",
        headers=headers,
        json={
            "order_id": str(order_a.id),
            "amount": "1299.00",
            "reason": "Earbuds defect submission two",
        },
    )
    assert res2.status_code == 200
    assert res2.json()["id"] == refund_id_1


def test_api_outcome_202_escalated(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    response = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(order_c.id),
            "amount": "8999.00",
            "reason": "Screen cracked on 4K Smart TV",
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert data["status"] == "pending_review"
    assert data["progress"] == "Under Review"
    assert data["payment_reference"] is None


def test_api_outcome_404_not_found(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    order_f = _get_order_by_amount(db_session, Decimal("1999.00"))  # customer2's order

    # Attempting to refund another customer's order
    res_other = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(order_f.id),
            "amount": "1999.00",
            "reason": "Attempting refund on unowned order",
        },
    )
    assert res_other.status_code == 404
    assert res_other.json()["error"]["code"] == "NOT_FOUND"

    # Attempting to refund random UUID
    res_rand = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(uuid.uuid4()),
            "amount": "1999.00",
            "reason": "Attempting refund on non-existent order",
        },
    )
    assert res_rand.status_code == 404
    assert res_rand.json()["error"]["code"] == "NOT_FOUND"
    assert res_other.json()["error"]["message"] == res_rand.json()["error"]["message"]


@pytest.mark.parametrize(
    "order_amount, refund_amount, expected_code",
    [
        (Decimal("2499.00"), "2499.00", "RETURN_WINDOW_EXPIRED"),    # Order B: window expired
        (Decimal("799.00"), "799.00", "ORDER_NOT_DELIVERED"),         # Order D: shipped
        (Decimal("1599.00"), "1599.00", "ALREADY_REFUNDED"),          # Order E: already refunded
        (Decimal("450.00"), "450.00", "NON_RETURNABLE_CATEGORY"),     # Order G: grocery
    ],
)
def test_api_outcome_409_policy_rejections(
    client: TestClient,
    db_session: Session,
    order_amount: Decimal,
    refund_amount: str,
    expected_code: str,
) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    order = _get_order_by_amount(db_session, order_amount)

    res = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(order.id),
            "amount": refund_amount,
            "reason": "Testing policy rejection mapping",
        },
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == expected_code


def test_api_outcome_502_payment_gateway_error(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    order_a = _get_order_by_amount(db_session, Decimal("1299.00"))

    # Force payment mock mode to fail
    settings.PAYMENT_MOCK_MODE = "fail"

    res = client.post(
        "/api/v1/refunds",
        headers=_auth_header(cust1),
        json={
            "order_id": str(order_a.id),
            "amount": "1299.00",
            "reason": "Earbuds defect with failing gateway rails",
        },
    )
    assert res.status_code == 502
    assert res.json()["error"]["code"] == "PAYMENT_FAILED"
    # Must clearly communicate that the refund was not completed
    msg = res.json()["error"]["message"]
    assert "not completed" in msg.lower() or "failed" in msg.lower()


# ---------------------------------------------------------------------------
# 3. Customer Refund Queries & Progress Field
# ---------------------------------------------------------------------------

def test_get_refunds_lists_customer_own_refunds_with_progress(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    cust2 = _get_user_by_email(db_session, "customer2@example.com")

    # Order E (Customer 1) already has a processed refund in seed data
    res_list1 = client.get("/api/v1/refunds", headers=_auth_header(cust1))
    assert res_list1.status_code == 200
    refunds1 = res_list1.json()
    assert len(refunds1) >= 1
    assert "progress" in refunds1[0]
    assert refunds1[0]["progress"] == "Completed"

    # Customer 2 initially has 0 refunds
    res_list2 = client.get("/api/v1/refunds", headers=_auth_header(cust2))
    assert res_list2.status_code == 200
    assert len(res_list2.json()) == 0


def test_get_refund_by_id_tenant_boundary(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    cust2 = _get_user_by_email(db_session, "customer2@example.com")
    order_e = _get_order_by_amount(db_session, Decimal("1599.00"))
    refund_e = order_e.refunds[0]

    # Customer 1 can access own refund
    res_ok = client.get(f"/api/v1/refunds/{refund_e.id}", headers=_auth_header(cust1))
    assert res_ok.status_code == 200
    assert res_ok.json()["id"] == str(refund_e.id)
    assert res_ok.json()["progress"] == "Completed"

    # Customer 2 gets 404 NOT_FOUND on Customer 1's refund ID (no leakage)
    res_leak = client.get(f"/api/v1/refunds/{refund_e.id}", headers=_auth_header(cust2))
    assert res_leak.status_code == 404
    assert res_leak.json()["error"]["code"] == "NOT_FOUND"
