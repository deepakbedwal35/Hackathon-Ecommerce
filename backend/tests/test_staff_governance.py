from decimal import Decimal
import uuid
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.enums import (
    EscalationDecision,
    RefundStatus,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.models import Escalation, Order, Refund, Ticket, User
from app.services.payment_mock import _payment_registry, clear_payment_mock_registry
from app.services.refunds import Outcome, request_refund


def _auth_header(client: TestClient, email: str) -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "LocalDevDemo123!"},
    )
    assert res.status_code == 200, f"Login failed for {email}: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_agent_cannot_approve_or_reject_refunds_gets_403(
    client: TestClient, seeded_db: Session
) -> None:
    """Agents cannot approve or reject escalations - only admins can."""
    cust1 = seeded_db.query(User).filter(User.email == "customer1@example.com").first()
    order_c = seeded_db.query(Order).filter(Order.total_amount == Decimal("8999.00")).first()

    # Request refund to trigger escalation
    res = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on TV set",
    )
    assert res.outcome == Outcome.ESCALATED
    escalation_id = res.escalation.id

    agent_headers = _auth_header(client, "agent1@example.com")

    # Agent tries to approve -> must return 403
    res_approve = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        json={"decision": "approve", "note": "Agent approval attempt"},
        headers=agent_headers,
    )
    assert res_approve.status_code == 403, f"Agent was allowed to approve: {res_approve.status_code}"

    # Agent tries to reject -> must return 403
    res_reject = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        json={"decision": "reject", "note": "Agent reject attempt"},
        headers=agent_headers,
    )
    assert res_reject.status_code == 403, f"Agent was allowed to reject: {res_reject.status_code}"

    # Agent CAN call request_info -> 200 OK
    res_info = client.post(
        f"/api/v1/staff/escalations/{escalation_id}/decision",
        json={
            "decision": "request_info",
            "note": "Need photo of packaging serial number.",
            "message_to_customer": "Please share a photo of the box serial label.",
        },
        headers=agent_headers,
    )
    assert res_info.status_code == 200


def test_refund_review_mode_all_escalates_every_eligible_refund(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When REFUND_REVIEW_MODE='all', eligible refunds escalate without payment; expired still rejects; duplicate idempotency holds."""
    clear_payment_mock_registry()
    monkeypatch.setattr(settings, "REFUND_REVIEW_MODE", "all")

    cust1 = seeded_db.query(User).filter(User.email == "customer1@example.com").first()
    order_a = seeded_db.query(Order).filter(Order.order_number == "ORD-1001").first()
    order_b = seeded_db.query(Order).filter(Order.order_number == "ORD-1002").first()

    # 1. Eligible 1,299 -> ESCALATED, payment NOT called
    res = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Does not fit ears well",
        idempotency_key="mode-all-key-1",
    )
    assert res.outcome == Outcome.ESCALATED
    assert res.refund.status == RefundStatus.PENDING_REVIEW
    assert res.refund.payment_reference is None
    assert len(_payment_registry) == 0
    assert res.escalation is not None
    assert res.escalation.decision == EscalationDecision.PENDING
    t_a = seeded_db.get(Ticket, res.refund.ticket_id)
    assert t_a.status == TicketStatus.ESCALATED

    # 2. Same request twice creates no second refund or escalation
    res_dup = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_a.id,
        amount=Decimal("1299.00"),
        reason="Does not fit ears well",
        idempotency_key="mode-all-key-1",
    )
    assert res_dup.refund.id == res.refund.id
    assert seeded_db.scalar(select(func.count(Refund.id)).where(Refund.order_id == order_a.id)) == 1
    assert seeded_db.scalar(select(func.count(Escalation.id)).where(Escalation.refund_id == res.refund.id)) == 1

    # 3. Expired return window (Order B) still REJECTED with no escalation
    res_exp = request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_b.id,
        amount=Decimal("2499.00"),
        reason="Delivered too long ago",
    )
    assert res_exp.outcome == Outcome.REJECTED
    assert res_exp.escalation is None
    assert seeded_db.scalar(select(func.count(Refund.id)).where(Refund.order_id == order_b.id)) == 0


def test_staff_overview_endpoint(client: TestClient, seeded_db: Session) -> None:
    """Verifies GET /api/v1/staff/overview matches DB exactly with constant SQL query count (no N+1)."""
    cust1 = seeded_db.query(User).filter(User.email == "customer1@example.com").first()
    order_c = seeded_db.query(Order).filter(Order.order_number == "ORD-1003").first()
    request_refund(
        db=seeded_db,
        user=cust1,
        order_id=order_c.id,
        amount=Decimal("8999.00"),
        reason="Screen cracked on TV",
    )

    agent_headers = _auth_header(client, "agent1@example.com")

    queries_run = []
    engine = seeded_db.get_bind()

    def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        queries_run.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        res1 = client.get("/api/v1/staff/overview", headers=agent_headers)
        q_count_1 = len(queries_run)
        queries_run.clear()

        # Add 8 more tickets to confirm query count stays constant
        for i in range(8):
            seeded_db.add(
                Ticket(
                    customer_id=cust1.id,
                    subject=f"Extra test ticket {i}",
                    description="Testing overview N+1 scaling.",
                    category=TicketCategory.OTHER,
                    status=TicketStatus.OPEN,
                    priority=TicketPriority.LOW,
                )
            )
        seeded_db.commit()
        queries_run.clear()

        res2 = client.get("/api/v1/staff/overview", headers=agent_headers)
        q_count_2 = len(queries_run)
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert res1.status_code == 200
    assert res2.status_code == 200
    assert q_count_1 == q_count_2, f"Query count grew from {q_count_1} to {q_count_2}"

    data = res2.json()
    assert sum(data["ticket_counts"].values()) == seeded_db.scalar(select(func.count(Ticket.id)))
    assert data["awaiting_approval_count"] == seeded_db.scalar(
        select(func.count(Escalation.id)).where(
            Escalation.decision.in_([EscalationDecision.PENDING, EscalationDecision.MORE_INFO_REQUESTED])
        )
    )
    assert Decimal(str(data["pending_refund_total"])) == Decimal("8999.00")
    assert len(data["top_5_pending_approvals"]) == 1
    assert len(data["top_5_recent_tickets"]) == 5


def test_staff_list_tickets_multi_customer_and_auth(
    client: TestClient, seeded_db: Session
) -> None:
    """Staff list returns tickets from ALL customers; customer gets 403; unauth gets 401."""
    # Unauthenticated -> 401
    res_unauth = client.get("/api/v1/staff/tickets")
    assert res_unauth.status_code == 401

    # Customer -> 403
    cust_headers = _auth_header(client, "customer1@example.com")
    res_cust = client.get("/api/v1/staff/tickets", headers=cust_headers)
    assert res_cust.status_code == 403

    # Agent -> 200 with tickets across customers
    agent_headers = _auth_header(client, "agent1@example.com")
    res_agent = client.get("/api/v1/staff/tickets", headers=agent_headers)
    assert res_agent.status_code == 200
    items = res_agent.json()["items"]
    cust_names = {item["customer_name"] for item in items}
    assert len(cust_names) >= 2


def test_staff_ticket_messages_after_cursor(
    client: TestClient, seeded_db: Session
) -> None:
    """Staff ticket messages endpoint supports cursor-based retrieval via after parameter."""
    agent_headers = _auth_header(client, "agent1@example.com")

    # Fetch a ticket
    ticket = seeded_db.query(Ticket).first()
    assert ticket is not None

    # Get initial messages
    res_init = client.get(
        f"/api/v1/staff/tickets/{ticket.id}/messages", headers=agent_headers
    )
    assert res_init.status_code == 200
    init_msgs = res_init.json()
    assert len(init_msgs) >= 1
    cursor_time = init_msgs[-1]["created_at"]

    # Post new staff message
    res_post = client.post(
        f"/api/v1/staff/tickets/{ticket.id}/messages",
        headers=agent_headers,
        json={"content": "Follow up message from support staff"},
    )
    assert res_post.status_code == 201

    # Query with after cursor
    res_after = client.get(
        f"/api/v1/staff/tickets/{ticket.id}/messages",
        params={"after": cursor_time},
        headers=agent_headers,
    )
    assert res_after.status_code == 200
    after_msgs = res_after.json()
    assert len(after_msgs) >= 1
    assert all(m["created_at"] > cursor_time for m in after_msgs)


def test_customer_endpoints_do_not_leak_staff_internals(
    client: TestClient, seeded_db: Session
) -> None:
    """Customer endpoints never expose internal notes or staff fields."""
    ticket = seeded_db.query(Ticket).first()
    assert ticket is not None

    # Staff adds internal note
    agent_headers = _auth_header(client, "agent1@example.com")
    res_note = client.post(
        f"/api/v1/staff/tickets/{ticket.id}/notes",
        headers=agent_headers,
        json={"note": "Confidential internal investigation note."},
    )
    assert res_note.status_code == 201

    # Customer fetches ticket detail
    cust_headers = _auth_header(client, "customer1@example.com")
    res_cust = client.get(f"/api/v1/tickets/{ticket.id}", headers=cust_headers)
    assert res_cust.status_code == 200
    cust_data = res_cust.json()

    assert "notes" not in cust_data
    assert "internal_note" not in cust_data
    assert "awaiting_admin_approval" not in cust_data
    assert "allowed_transitions" not in cust_data


def test_ai_agent_in_mode_all_escalates_and_informs_customer(
    seeded_db: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When mode is 'all', customer asking for refund via agent triggers escalation."""
    monkeypatch.setattr(settings, "REFUND_REVIEW_MODE", "all")

    cust1 = seeded_db.query(User).filter(User.email == "customer1@example.com").first()
    ticket = Ticket(
        customer_id=cust1.id,
        subject="Refund request ORD-1001",
        description="I want a refund for my order ORD-1001.",
        category=TicketCategory.REFUND,
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
    )
    seeded_db.add(ticket)
    seeded_db.flush()

    from app.agent.runner import run_agent_turn
    from app.models.models import Message
    from app.models.enums import SenderType
    from tests.test_agent_runner import FakeLLMClient, LLMResponse, ToolCall

    init_msg = Message(
        ticket_id=ticket.id,
        sender_type=SenderType.CUSTOMER,
        sender_id=cust1.id,
        content="Please refund my order ORD-1001.",
    )
    seeded_db.add(init_msg)
    seeded_db.commit()

    fake_llm = FakeLLMClient([
        LLMResponse(tool_calls=[ToolCall(id="c1", name="get_order_details", arguments={"order_id": "ORD-1001"})]),
        LLMResponse(tool_calls=[ToolCall(id="c2", name="process_refund", arguments={"order_id": "ORD-1001", "amount": "1299.00", "reason": "Customer requested refund in all mode"})]),
        LLMResponse(text="Your refund request has been submitted for human review. Our team will review the details and approve it."),
    ])

    result = run_agent_turn(seeded_db, cust1, ticket, llm_client=fake_llm)
    assert result.reply_message is not None
    assert "human review" in result.reply_message.content.lower()

    # Verify ticket escalated
    seeded_db.refresh(ticket)
    assert ticket.status == TicketStatus.ESCALATED
