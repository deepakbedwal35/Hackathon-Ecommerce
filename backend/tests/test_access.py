import uuid
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models.enums import ItemCategory, OrderStatus, TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.models import Order, OrderItem, Ticket, User
from scripts.seed import seed_database


def get_token_for_user(user: User) -> str:
    return create_access_token(subject=str(user.id))


def test_customer_accessing_staff_only_route_returns_403(
    client: TestClient, db_session: Session
) -> None:
    """Test customer role is rejected from staff routes with 403 FORBIDDEN."""
    customer = User(
        name="Cust",
        email="cust@example.com",
        password_hash="hash",
        role=UserRole.CUSTOMER,
    )
    db_session.add(customer)
    db_session.commit()

    token = get_token_for_user(customer)
    res = client.get("/test/staff-only", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 403
    assert res.json()["error"]["code"] == "FORBIDDEN"


def test_agent_and_admin_accessing_staff_only_route_returns_200(
    client: TestClient, db_session: Session
) -> None:
    """Test agent and admin roles are allowed into staff-only routes."""
    agent = User(
        name="Agent User",
        email="agent_test@example.com",
        password_hash="hash",
        role=UserRole.AGENT,
    )
    admin = User(
        name="Admin User",
        email="admin_test@example.com",
        password_hash="hash",
        role=UserRole.ADMIN,
    )
    db_session.add_all([agent, admin])
    db_session.commit()

    # Agent
    agent_token = get_token_for_user(agent)
    res_agent = client.get(
        "/test/staff-only", headers={"Authorization": f"Bearer {agent_token}"}
    )
    assert res_agent.status_code == 200
    assert res_agent.json()["role"] == "agent"

    # Admin
    admin_token = get_token_for_user(admin)
    res_admin = client.get(
        "/test/staff-only", headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert res_admin.status_code == 200
    assert res_admin.json()["role"] == "admin"


def test_ownership_helpers_orders(client: TestClient, db_session: Session) -> None:
    """
    Test customer1 fetching own order -> 200;
    Customer1 fetching customer2 order -> 404;
    Nonexistent order -> 404 with IDENTICAL error body.
    """
    cust1 = User(name="C1", email="c1@example.com", password_hash="h", role=UserRole.CUSTOMER)
    cust2 = User(name="C2", email="c2@example.com", password_hash="h", role=UserRole.CUSTOMER)
    db_session.add_all([cust1, cust2])
    db_session.commit()

    order1 = Order(customer_id=cust1.id, status=OrderStatus.PLACED, total_amount=Decimal("100.00"))
    order2 = Order(customer_id=cust2.id, status=OrderStatus.PLACED, total_amount=Decimal("200.00"))
    db_session.add_all([order1, order2])
    db_session.commit()

    token1 = get_token_for_user(cust1)

    # 1. Customer 1 fetches own order -> 200
    res_own = client.get(
        f"/test/order/{order1.id}", headers={"Authorization": f"Bearer {token1}"}
    )
    assert res_own.status_code == 200
    assert res_own.json()["id"] == str(order1.id)

    # 2. Customer 1 fetches Customer 2 order -> 404
    res_other = client.get(
        f"/test/order/{order2.id}", headers={"Authorization": f"Bearer {token1}"}
    )
    assert res_other.status_code == 404

    # 3. Customer 1 fetches nonexistent order -> 404
    random_id = uuid.uuid4()
    res_nonexistent = client.get(
        f"/test/order/{random_id}", headers={"Authorization": f"Bearer {token1}"}
    )
    assert res_nonexistent.status_code == 404

    # Crucial security verification: error shape and message MUST be identical
    err_other = res_other.json()["error"]
    err_nonexistent = res_nonexistent.json()["error"]
    assert err_other["code"] == "NOT_FOUND"
    assert err_nonexistent["code"] == "NOT_FOUND"
    assert err_other["message"] == err_nonexistent["message"]
    assert err_other["details"] == err_nonexistent["details"]


def test_agent_can_fetch_any_ticket_and_order(
    client: TestClient, db_session: Session
) -> None:
    """Test staff agent can fetch any customer's ticket and order without 404."""
    cust = User(name="Customer", email="cust_ticket@example.com", password_hash="h", role=UserRole.CUSTOMER)
    agent = User(name="Agent", email="agent_ticket@example.com", password_hash="h", role=UserRole.AGENT)
    db_session.add_all([cust, agent])
    db_session.commit()

    order = Order(customer_id=cust.id, status=OrderStatus.DELIVERED, total_amount=Decimal("300.00"))
    db_session.add(order)
    db_session.commit()

    ticket = Ticket(
        customer_id=cust.id,
        order_id=order.id,
        subject="Agent access test",
        description="Issue description",
        category=TicketCategory.ORDER_ISSUE,
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
    )
    db_session.add(ticket)
    db_session.commit()

    agent_token = get_token_for_user(agent)

    # Agent fetches customer's ticket -> 200
    res_ticket = client.get(
        f"/test/ticket/{ticket.id}", headers={"Authorization": f"Bearer {agent_token}"}
    )
    assert res_ticket.status_code == 200
    assert res_ticket.json()["id"] == str(ticket.id)
    assert res_ticket.json()["subject"] == "Agent access test"

    # Agent fetches customer's order -> 200
    res_order = client.get(
        f"/test/order/{order.id}", headers={"Authorization": f"Bearer {agent_token}"}
    )
    assert res_order.status_code == 200
    assert res_order.json()["id"] == str(order.id)
