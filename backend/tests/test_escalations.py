from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import json
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings
from app.core.security import create_access_token
from app.models.enums import EscalationDecision, RefundStatus, TicketStatus, UserRole
from app.models.models import AuditEvent, Escalation, Order, Refund, Ticket, User
from app.services.payment_mock import clear_payment_mock_registry, _payment_registry
from app.services.refunds import Outcome, request_refund
from scripts.seed import seed_database


@pytest.fixture(autouse=True)
def clean_mock_and_seed(db_session: Session):
    """Resets mock payment registry and pre-seeds test database."""
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
# 1. Assignment Authorization (Agent self-only, Admin any-staff, Non-staff 422)
# ---------------------------------------------------------------------------

def test_escalation_assignment_rules(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    agent = _get_user_by_email(db_session, "agent1@example.com")
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    # Customer triggers an escalation on Order C
    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen damaged on 4K TV",
    )
    assert res_esc.outcome == Outcome.ESCALATED
    escalation_id = res_esc.escalation.id

    # 1. Agent assigning to themselves -> 200 OK
    res_self = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/assign",
        headers=_auth_header(agent),
        json={"assignee_id": str(agent.id)},
    )
    assert res_self.status_code == 200

    # 2. Agent assigning to another user -> 403 FORBIDDEN
    res_agent_other = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/assign",
        headers=_auth_header(agent),
        json={"assignee_id": str(admin.id)},
    )
    assert res_agent_other.status_code == 403
    assert res_agent_other.json()["error"]["code"] == "FORBIDDEN"

    # 3. Admin assigning to any staff user -> 200 OK
    res_admin_assign = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/assign",
        headers=_auth_header(admin),
        json={"assignee_id": str(agent.id)},
    )
    assert res_admin_assign.status_code == 200
    assert res_admin_assign.json()["assigned_to"] == str(agent.id)

    # 4. Admin assigning to a customer (non-staff) -> 422 VALIDATION_ERROR
    res_admin_cust = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/assign",
        headers=_auth_header(admin),
        json={"assignee_id": str(cust1.id)},
    )
    assert res_admin_cust.status_code == 422
    assert res_admin_cust.json()["error"]["code"] == "VALIDATION_ERROR"


# ---------------------------------------------------------------------------
# 2. Decision: Approve Happy Path & Idempotency
# ---------------------------------------------------------------------------

def test_escalation_approve_happy_path(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on TV",
    )
    escalation_id = res_esc.escalation.id
    ticket_id = res_esc.refund.ticket_id

    # Approve decision
    response = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={
            "decision": "approve",
            "note": "Approved refund after reviewing courier damage report.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processed"
    assert data["payment_reference"] is not None

    # Verify DB: exactly 1 refund row, escalation approved, ticket resolved
    refund_count = db_session.scalar(select(func.count(Refund.id)).where(Refund.order_id == order_c.id))
    assert refund_count == 1

    esc = db_session.get(Escalation, escalation_id)
    assert esc.decision == EscalationDecision.APPROVED
    assert esc.decided_at is not None

    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.status == TicketStatus.RESOLVED

    # Calling decision again -> 409 ALREADY_DECIDED
    res_dup = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={"decision": "approve", "note": "Duplicate approval attempt."},
    )
    assert res_dup.status_code == 409
    assert res_dup.json()["error"]["code"] == "ALREADY_DECIDED"


def test_concurrent_approvals_only_one_succeeds(setup_test_postgres, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on TV",
    )
    escalation_id = res_esc.escalation.id

    from app.main import create_app
    app = create_app()

    def worker(worker_id: int):
        with TestClient(app) as test_client:
            return test_client.post(
                f"/api/v1/staff/escalations/{escalation_id}/decision",
                headers=_auth_header(admin),
                json={"decision": "approve", "note": f"Concurrent worker {worker_id} note"},
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker, 1)
        f2 = executor.submit(worker, 2)
        r1, r2 = f1.result(), f2.result()

    statuses = [r1.status_code, r2.status_code]
    assert 200 in statuses
    assert 409 in statuses

    # Exactly 1 payment dispatched
    assert len(_payment_registry) == 1


# ---------------------------------------------------------------------------
# 3. Decision: Re-check Refundable Balance on Approve
# ---------------------------------------------------------------------------

def test_approve_after_order_refundable_amount_shrank(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("6000.00"),
        reason="Partial high-value return",
    )
    escalation_id = res_esc.escalation.id

    # Artificially shrink order amount
    order_c.total_amount = Decimal("5000.00")
    db_session.commit()

    # Attempt approve -> 409
    res = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={"decision": "approve", "note": "Approving when balance reduced"},
    )
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "AMOUNT_EXCEEDS_REFUNDABLE"
    assert len(_payment_registry) == 0


# ---------------------------------------------------------------------------
# 4. Decision: Gateway Failure on Approve & Retry
# ---------------------------------------------------------------------------

def test_approve_payment_fail_mode_and_retry(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="TV defective panel",
    )
    escalation_id = res_esc.escalation.id
    refund_id = res_esc.refund.id

    # Simulate banking gateway failure
    settings.PAYMENT_MOCK_MODE = "fail"

    res_fail = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={"decision": "approve", "note": "Approved, testing gateway drop."},
    )
    assert res_fail.status_code == 502
    assert "not completed" in res_fail.json()["error"]["message"].lower()

    # Verify escalation remains open in PENDING
    esc = db_session.get(Escalation, escalation_id)
    assert esc.decision == EscalationDecision.PENDING

    # Switch payment gateway to "ok" and retry approval
    settings.PAYMENT_MOCK_MODE = "ok"
    clear_payment_mock_registry()

    res_retry = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={"decision": "approve", "note": "Retrying after rails restored."},
    )
    assert res_retry.status_code == 200
    data = res_retry.json()
    assert data["status"] == "processed"
    # Reuses the exact same refund row
    assert data["id"] == str(refund_id)

    # Exactly 1 refund row in DB
    count = db_session.scalar(select(func.count(Refund.id)).where(Refund.order_id == order_c.id))
    assert count == 1


# ---------------------------------------------------------------------------
# 5. Decision: Reject Path
# ---------------------------------------------------------------------------

def test_escalation_reject_flow(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen damaged",
    )
    escalation_id = res_esc.escalation.id
    ticket_id = res_esc.refund.ticket_id

    # Missing message_to_customer -> 422 VALIDATION_ERROR
    res_bad = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={"decision": "reject", "note": "Internal reason: physical damage by user"},
    )
    assert res_bad.status_code == 422
    assert res_bad.json()["error"]["code"] == "VALIDATION_ERROR"

    # Reject with note and explanation message
    res_rej = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={
            "decision": "reject",
            "note": "Internal note: Physical impact marks detected near corner mount.",
            "message_to_customer": "We inspected the provided photos and determined the damage was caused by external impact.",
        },
    )
    assert res_rej.status_code == 200

    # Refund is REJECTED
    ref = db_session.get(Refund, res_esc.refund.id)
    assert ref.status == RefundStatus.REJECTED

    # Ticket is RESOLVED with staff message visible to customer
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.status == TicketStatus.RESOLVED
    staff_msgs = [m for m in ticket.messages if m.sender_type.value == "staff"]
    assert len(staff_msgs) >= 1
    assert "external impact" in staff_msgs[-1].content
    assert len(_payment_registry) == 0


# ---------------------------------------------------------------------------
# 6. Decision: Request Info & Customer Reply Loop
# ---------------------------------------------------------------------------

def test_request_info_and_customer_reply_cycle(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    agent = _get_user_by_email(db_session, "agent1@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on TV",
    )
    escalation_id = res_esc.escalation.id
    ticket_id = res_esc.refund.ticket_id

    # Staff decides "request_info"
    res_req = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(agent),
        json={
            "decision": "request_info",
            "note": "Asking customer for unboxing video or outer box photos.",
            "message_to_customer": "Could you please send photos of the outer packaging box?",
        },
    )
    assert res_req.status_code == 200

    # Verify escalation is MORE_INFO_REQUESTED and ticket is AWAITING_CUSTOMER
    esc = db_session.get(Escalation, escalation_id)
    assert esc.decision == EscalationDecision.MORE_INFO_REQUESTED
    ticket = db_session.get(Ticket, ticket_id)
    assert ticket.status == TicketStatus.AWAITING_CUSTOMER

    # Customer fetches ticket -> review_status is "More information needed"
    res_cust_t = client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth_header(cust1))
    assert res_cust_t.status_code == 200
    assert res_cust_t.json()["review_status"] == "More information needed"

    # Customer replies to the ticket
    res_reply = client.post(
        f"/api/v1/tickets/{ticket_id}/messages",
        headers=_auth_header(cust1),
        json={"content": "Here is the photo of the outer box with courier label."},
    )
    assert res_reply.status_code == 201

    # Escalation automatically reverts to PENDING and ticket reopens
    db_session.refresh(esc)
    db_session.refresh(ticket)
    assert esc.decision == EscalationDecision.PENDING
    assert ticket.status == TicketStatus.OPEN

    # Escalation is visible again in staff queue
    res_queue = client.get("/api/v1/staff/escalations", headers=_auth_header(agent))
    assert res_queue.status_code == 200
    queue_ids = [e["id"] for e in res_queue.json()["items"]]
    assert str(escalation_id) in queue_ids

    # Staff can now approve
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")
    res_app = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(admin),
        json={"decision": "approve", "note": "Outer box shows carrier damage. Approved."},
    )
    assert res_app.status_code == 200
    assert res_app.json()["status"] == "processed"


def test_customer_cannot_see_internal_note_anywhere(client: TestClient, db_session: Session) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    agent = _get_user_by_email(db_session, "agent1@example.com")
    order_c = _get_order_by_amount(db_session, Decimal("8999.00"))

    res_esc = request_refund(
        db=db_session,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on TV",
    )
    escalation_id = res_esc.escalation.id
    ticket_id = res_esc.refund.ticket_id

    super_secret = "SUPER_SECRET_INTERNAL_STAFF_POLICY_OVERRIDE_FLAG"

    # Staff requests info with confidential note
    client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        headers=_auth_header(agent),
        json={
            "decision": "request_info",
            "note": super_secret,
            "message_to_customer": "Public customer question text",
        },
    )

    # Customer fetches ticket
    res_t = client.get(f"/api/v1/tickets/{ticket_id}", headers=_auth_header(cust1))
    assert res_t.status_code == 200
    assert super_secret not in json.dumps(res_t.json())

    # Customer fetches messages
    res_m = client.get(f"/api/v1/tickets/{ticket_id}/messages", headers=_auth_header(cust1))
    assert res_m.status_code == 200
    assert super_secret not in json.dumps(res_m.json())
