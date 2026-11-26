import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.enums import (
    EscalationDecision,
    OrderStatus,
    RefundStatus,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)
from app.models.models import User


def _auth_header(client: TestClient, email: str = "customer1@example.com") -> dict[str, str]:
    res = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "LocalDevDemo123!"},
    )
    assert res.status_code == 200, f"Login failed: {res.text}"
    token = res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_meta_enums_matches_real_python_enums(client: TestClient) -> None:
    res = client.get("/api/v1/meta/enums")
    assert res.status_code == 200
    data = res.json()

    assert "ticket_categories" in data
    assert "ticket_priorities" in data
    assert "ticket_statuses" in data
    assert "order_statuses" in data
    assert "refund_statuses" in data
    assert "escalation_decisions" in data

    # Verify every enum value in python enum is present in meta endpoint
    actual_cats = {item["value"] for item in data["ticket_categories"]}
    expected_cats = {e.value for e in TicketCategory}
    assert actual_cats == expected_cats

    actual_prios = {item["value"] for item in data["ticket_priorities"]}
    expected_prios = {e.value for e in TicketPriority}
    assert actual_prios == expected_prios

    actual_ticket_statuses = {item["value"] for item in data["ticket_statuses"]}
    expected_ticket_statuses = {e.value for e in TicketStatus}
    assert actual_ticket_statuses == expected_ticket_statuses

    actual_order_statuses = {item["value"] for item in data["order_statuses"]}
    expected_order_statuses = {e.value for e in OrderStatus}
    assert actual_order_statuses == expected_order_statuses

    actual_refund_statuses = {item["value"] for item in data["refund_statuses"]}
    expected_refund_statuses = {e.value for e in RefundStatus}
    assert actual_refund_statuses == expected_refund_statuses

    actual_escalation_decisions = {item["value"] for item in data["escalation_decisions"]}
    expected_escalation_decisions = {e.value for e in EscalationDecision}
    assert actual_escalation_decisions == expected_escalation_decisions


def test_meta_config_returns_policy_settings_without_secrets(client: TestClient) -> None:
    res = client.get("/api/v1/meta/config")
    assert res.status_code == 200
    cfg = res.json()

    assert "refund_review_mode" in cfg
    assert "auto_refund_limit" in cfg
    assert "return_window_days" in cfg

    # Ensure no secrets leak
    for secret_key in ("jwt_secret", "llm_api_key", "groq_api_key", "database_url"):
        assert secret_key not in cfg


def test_post_tickets_succeeds_for_every_category_in_meta_enums(
    client: TestClient, seeded_db: Session
) -> None:
    headers = _auth_header(client, "customer1@example.com")
    res_enums = client.get("/api/v1/meta/enums")
    assert res_enums.status_code == 200
    categories = res_enums.json()["ticket_categories"]

    for cat_item in categories:
        cat_val = cat_item["value"]
        payload = {
            "subject": f"Inquiry regarding {cat_val}",
            "description": f"Testing ticket creation for category {cat_val} to prove enum compatibility.",
            "category": cat_val,
        }
        res = client.post("/api/v1/tickets", json=payload, headers=headers)
        assert res.status_code == 201, f"Failed for category {cat_val}: {res.text}"
        ticket_data = res.json()["ticket"]
        assert ticket_data["category"] == cat_val
