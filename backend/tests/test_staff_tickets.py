from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
import uuid
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import (
    EscalationDecision,
    ItemCategory,
    OrderStatus,
    SenderType,
    TicketCategory,
    TicketPriority,
    TicketStatus,
    UserRole,
)
from app.models.models import AuditEvent, Escalation, Message, Order, Ticket, TicketNote, User
from scripts.seed import seed_database


@pytest.fixture(autouse=True)
def setup_seed(db_session: Session):
    seed_database(reset=True, session=db_session)
    yield


def _auth_header(user: User) -> dict[str, str]:
    token = create_access_token(subject=str(user.id))
    return {"Authorization": f"Bearer {token}"}


def _get_user_by_email(db: Session, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))


# ---------------------------------------------------------------------------
# 1. RBAC & Protection on Staff Routes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method, path_template",
    [
        ("GET", "/api/v1/staff/tickets"),
        ("GET", "/api/v1/staff/tickets/{ticket_id}"),
        ("PATCH", "/api/v1/staff/tickets/{ticket_id}"),
        ("POST", "/api/v1/staff/tickets/{ticket_id}/messages"),
        ("GET", "/api/v1/staff/tickets/{ticket_id}/notes"),
        ("POST", "/api/v1/staff/tickets/{ticket_id}/notes"),
        ("GET", "/api/v1/staff/escalations"),
        ("GET", "/api/v1/staff/escalations/{ticket_id}"),
    ],
)
def test_customer_forbidden_on_all_staff_routes(
    client: TestClient, db_session: Session, method: str, path_template: str
) -> None:
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    ticket = db_session.scalar(select(Ticket))
    assert ticket is not None
    path = path_template.format(ticket_id=ticket.id)

    # 1. Unauthenticated -> 401
    res_unauth = client.request(method, path, json={"content": "test", "note": "test"})
    assert res_unauth.status_code == 401
    assert res_unauth.json()["error"]["code"] == "NOT_AUTHENTICATED"

    # 2. Customer -> 403
    res_cust = client.request(
        method, path, headers=_auth_header(cust1), json={"content": "test", "note": "test"}
    )
    assert res_cust.status_code == 403
    assert res_cust.json()["error"]["code"] == "FORBIDDEN"


def test_agent_and_admin_authorized_on_staff_routes(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    admin = _get_user_by_email(db_session, "admin1@example.com") or _get_user_by_email(db_session, "admin@example.com")

    # Agent -> 200
    res_agent = client.get("/api/v1/staff/tickets", headers=_auth_header(agent))
    assert res_agent.status_code == 200

    # Admin -> 200
    res_admin = client.get("/api/v1/staff/tickets", headers=_auth_header(admin))
    assert res_admin.status_code == 200


# ---------------------------------------------------------------------------
# 2. Ticket List Filters, Wildcard Escape Search, SLA Sorting & Pagination
# ---------------------------------------------------------------------------

def test_ticket_list_filters_and_pagination(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    cust1 = _get_user_by_email(db_session, "customer1@example.com")

    # Add extra tickets with various statuses, priorities, categories
    t_urgent = Ticket(
        customer_id=cust1.id,
        subject="Urgent server crash report",
        description="Immediate attention required",
        category=TicketCategory.ORDER_ISSUE,
        status=TicketStatus.OPEN,
        priority=TicketPriority.URGENT,
        created_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )
    t_closed = Ticket(
        customer_id=cust1.id,
        subject="Old closed inquiry",
        description="Nothing to do",
        category=TicketCategory.OTHER,
        status=TicketStatus.CLOSED,
        priority=TicketPriority.LOW,
        created_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add_all([t_urgent, t_closed])
    db_session.commit()

    # Filter status=open
    res_open = client.get("/api/v1/staff/tickets?status=open", headers=_auth_header(agent))
    assert res_open.status_code == 200
    for item in res_open.json()["items"]:
        assert item["status"] == "open"

    # Filter priority=urgent
    res_urg = client.get("/api/v1/staff/tickets?priority=urgent", headers=_auth_header(agent))
    assert res_urg.status_code == 200
    assert len(res_urg.json()["items"]) >= 1
    assert res_urg.json()["items"][0]["priority"] == "urgent"

    # Pagination totals and limit
    res_page = client.get("/api/v1/staff/tickets?page=1&page_size=2", headers=_auth_header(agent))
    assert res_page.status_code == 200
    data = res_page.json()
    assert len(data["items"]) <= 2
    assert data["page"] == 1
    assert data["total"] >= 3


def test_ticket_list_search_escaping_and_uuid(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    cust1 = _get_user_by_email(db_session, "customer1@example.com")

    special_ticket = Ticket(
        customer_id=cust1.id,
        subject="Special 50% discount voucher inquiry",
        description="Question about % voucher",
        category=TicketCategory.OTHER,
        status=TicketStatus.OPEN,
        priority=TicketPriority.LOW,
    )
    db_session.add(special_ticket)
    db_session.commit()

    # Search by exact UUID
    res_uuid = client.get(f"/api/v1/staff/tickets?q={special_ticket.id}", headers=_auth_header(agent))
    assert res_uuid.status_code == 200
    assert len(res_uuid.json()["items"]) == 1
    assert res_uuid.json()["items"][0]["id"] == str(special_ticket.id)

    # Search by customer email
    res_email = client.get("/api/v1/staff/tickets?q=customer1@example.com", headers=_auth_header(agent))
    assert res_email.status_code == 200
    assert len(res_email.json()["items"]) >= 1

    # Search with q="%" -> MUST NOT match all! It only matches literal '%' in subject
    res_pct = client.get("/api/v1/staff/tickets?q=%25", headers=_auth_header(agent))
    assert res_pct.status_code == 200
    # Exactly matches the one ticket containing "50% discount"
    assert len(res_pct.json()["items"]) == 1
    assert res_pct.json()["items"][0]["id"] == str(special_ticket.id)


def test_ticket_list_sorting_sla_vs_newest(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")

    # Default SLA sort: urgent -> high -> medium -> low
    res_sla = client.get("/api/v1/staff/tickets?sort=sla", headers=_auth_header(agent))
    assert res_sla.status_code == 200
    items = res_sla.json()["items"]
    priorities = [it["priority"] for it in items]
    priority_ranks = {"urgent": 1, "high": 2, "medium": 3, "low": 4}
    ranks = [priority_ranks[p] for p in priorities]
    assert ranks == sorted(ranks)

    # Sort=newest: created_at descending
    res_newest = client.get("/api/v1/staff/tickets?sort=newest", headers=_auth_header(agent))
    assert res_newest.status_code == 200
    items_new = res_newest.json()["items"]
    created_dates = [it["created_at"] for it in items_new]
    assert created_dates == sorted(created_dates, reverse=True)


# ---------------------------------------------------------------------------
# 3. Ticket Detail & N+1 Prevention
# ---------------------------------------------------------------------------

def test_ticket_detail_full_context_and_no_n_plus_one(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    ticket = db_session.scalar(select(Ticket))
    assert ticket is not None

    # Attach note to ticket
    db_session.add(
        TicketNote(
            ticket_id=ticket.id,
            author_id=agent.id,
            note="Internal evaluation: customer contacted previously.",
        )
    )
    db_session.commit()

    # Query count listener to prove no N+1 query proliferation
    query_count = 0

    def query_listener(conn, cursor, statement, parameters, context, executemany):
        nonlocal query_count
        query_count += 1

    event.listen(db_session.bind, "before_cursor_execute", query_listener)
    try:
        res = client.get(f"/api/v1/staff/tickets/{ticket.id}", headers=_auth_header(agent))
    finally:
        event.remove(db_session.bind, "before_cursor_execute", query_listener)

    assert res.status_code == 200
    data = res.json()

    # Verify all related trees populated in one response
    assert "ticket" in data
    assert "customer" in data
    assert data["customer"]["email"] is not None
    assert "order" in data
    assert "messages" in data
    assert "notes" in data
    assert len(data["notes"]) >= 1
    assert "escalations" in data

    # Verify query count is small, fixed, and bounded (O(1) relation loads, proving no N+1)
    assert query_count <= 15


# ---------------------------------------------------------------------------
# 4. PATCH Ticket State Machine & Invariants
# ---------------------------------------------------------------------------

def test_patch_ticket_transitions_and_pending_escalation_guard(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    cust1 = _get_user_by_email(db_session, "customer1@example.com")

    # Fresh open ticket
    ticket = Ticket(
        customer_id=cust1.id,
        subject="Status transition test ticket",
        description="Testing state transitions",
        category=TicketCategory.ORDER_ISSUE,
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
    )
    db_session.add(ticket)
    db_session.commit()

    # 1. Valid transition: open -> awaiting_customer
    res_awaiting = client.patch(
        f"/api/v1/staff/tickets/{ticket.id}",
        headers=_auth_header(agent),
        json={"status": "awaiting_customer"},
    )
    assert res_awaiting.status_code == 200
    assert res_awaiting.json()["status"] == "awaiting_customer"

    # 2. Staff cannot set status=escalated manually -> 409
    res_esc_manual = client.patch(
        f"/api/v1/staff/tickets/{ticket.id}",
        headers=_auth_header(agent),
        json={"status": "escalated"},
    )
    assert res_esc_manual.status_code == 409
    assert res_esc_manual.json()["error"]["code"] == "INVALID_TRANSITION"

    # 3. Attach pending escalation
    esc = Escalation(
        ticket_id=ticket.id,
        summary="Pending refund escalation",
        priority=TicketPriority.HIGH,
        decision=EscalationDecision.PENDING,
    )
    db_session.add(esc)
    db_session.commit()

    # 4. Attempting to resolve with pending escalation -> 409 ESCALATION_PENDING
    res_resolve = client.patch(
        f"/api/v1/staff/tickets/{ticket.id}",
        headers=_auth_header(agent),
        json={"status": "resolved"},
    )
    assert res_resolve.status_code == 409
    assert res_resolve.json()["error"]["code"] == "ESCALATION_PENDING"

    # 5. Invalid transition: closed ticket cannot transition -> 409 INVALID_TRANSITION
    # Mark escalation approved and ticket closed
    esc.decision = EscalationDecision.APPROVED
    ticket.status = TicketStatus.CLOSED
    db_session.commit()

    res_reopen = client.patch(
        f"/api/v1/staff/tickets/{ticket.id}",
        headers=_auth_header(agent),
        json={"status": "open"},
    )
    assert res_reopen.status_code == 409
    assert res_reopen.json()["error"]["code"] == "INVALID_TRANSITION"


# ---------------------------------------------------------------------------
# 5. Staff Messages & Notes Isolation
# ---------------------------------------------------------------------------

def test_staff_message_visible_to_customer_with_staff_sender(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    ticket = db_session.scalar(select(Ticket).where(Ticket.customer_id == cust1.id))
    assert ticket is not None

    # Staff posts message
    res_post = client.post(
        f"/api/v1/staff/tickets/{ticket.id}/messages",
        headers=_auth_header(agent),
        json={"content": "Hello customer, we are looking into this right now."},
    )
    assert res_post.status_code == 201

    # Customer fetches messages
    res_cust_msgs = client.get(
        f"/api/v1/tickets/{ticket.id}/messages",
        headers=_auth_header(cust1),
    )
    assert res_cust_msgs.status_code == 200
    msgs = res_cust_msgs.json()
    staff_msgs = [m for m in msgs if m["sender_type"] == "staff"]
    assert len(staff_msgs) >= 1
    assert "looking into this right now" in staff_msgs[-1]["content"]


def test_internal_notes_completely_hidden_from_customer(client: TestClient, db_session: Session) -> None:
    agent = _get_user_by_email(db_session, "agent1@example.com")
    cust1 = _get_user_by_email(db_session, "customer1@example.com")
    ticket = db_session.scalar(select(Ticket).where(Ticket.customer_id == cust1.id))
    assert ticket is not None

    secret_note = "CONFIDENTIAL_FRAUD_CHECK_PASSED_AGENT_ONLY_SECRET"

    # Staff adds internal note
    res_note = client.post(
        f"/api/v1/staff/tickets/{ticket.id}/notes",
        headers=_auth_header(agent),
        json={"note": secret_note},
    )
    assert res_note.status_code == 201

    # Customer fetches ticket detail
    res_ticket = client.get(f"/api/v1/tickets/{ticket.id}", headers=_auth_header(cust1))
    assert res_ticket.status_code == 200
    raw_ticket_json = json.dumps(res_ticket.json())
    assert secret_note not in raw_ticket_json

    # Customer fetches messages
    res_msgs = client.get(f"/api/v1/tickets/{ticket.id}/messages", headers=_auth_header(cust1))
    assert res_msgs.status_code == 200
    raw_msgs_json = json.dumps(res_msgs.json())
    assert secret_note not in raw_msgs_json

    # Customer cannot call staff notes endpoint -> 403
    res_notes_cust = client.get(f"/api/v1/staff/tickets/{ticket.id}/notes", headers=_auth_header(cust1))
    assert res_notes_cust.status_code == 403
