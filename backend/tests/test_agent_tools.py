from decimal import Decimal
import uuid

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.tools import (
    ToolExecutionContext,
    execute_tool_call,
)
from app.models.enums import EscalationDecision, TicketCategory, TicketPriority, TicketStatus, UserRole
from app.models.models import AuditEvent, Escalation, Order, Ticket, User


def _get_user_by_email(db: Session, email: str) -> User:
    return db.scalar(select(User).where(User.email == email.lower()))


def _create_test_ticket(db: Session, user: User, order: Order | None = None) -> Ticket:
    ticket = Ticket(
        customer_id=user.id,
        order_id=order.id if order else None,
        subject="Test Tool Ticket",
        description="Ticket created for testing tool execution gating",
        category=TicketCategory.REFUND,
        status=TicketStatus.OPEN,
        priority=TicketPriority.MEDIUM,
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)
    return ticket


def test_get_order_details_validation_and_not_found(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    ticket = _create_test_ticket(seeded_db, cust1)
    ctx = ToolExecutionContext(db=seeded_db, user=cust1, ticket=ticket)

    # 1. Missing order_id -> ORDER_ID_REQUIRED without DB hit
    res_missing = execute_tool_call(ctx, "get_order_details", {})
    assert res_missing["ok"] is False
    assert res_missing["error"] == "ORDER_ID_REQUIRED"

    res_blank = execute_tool_call(ctx, "get_order_details", {"order_id": "   "})
    assert res_blank["ok"] is False
    assert res_blank["error"] == "ORDER_ID_REQUIRED"

    # 2. Unknown order id -> ORDER_NOT_FOUND
    res_unknown = execute_tool_call(ctx, "get_order_details", {"order_id": "ORD-9999"})
    assert res_unknown["ok"] is False
    assert res_unknown["error"] == "ORDER_NOT_FOUND"

    # 3. Customer 1 requesting Customer 2's order (ORD-1006) -> ORDER_NOT_FOUND (no leakage)
    res_other = execute_tool_call(ctx, "get_order_details", {"order_id": "ORD-1006"})
    assert res_other["ok"] is False
    assert res_other["error"] == "ORDER_NOT_FOUND"


def test_get_order_details_success_and_context_tracking(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    ticket = _create_test_ticket(seeded_db, cust1)
    ctx = ToolExecutionContext(db=seeded_db, user=cust1, ticket=ticket)

    # Success with human-readable order number
    res = execute_tool_call(ctx, "get_order_details", {"order_id": "ORD-1001"})
    assert res["ok"] is True
    assert res["order_number"] == "ORD-1001"
    assert res["status"] == "delivered"
    assert res["total_amount"] == "1299.00"
    assert len(res["items"]) >= 1
    assert res["items"][0]["name"] == "Wireless Bluetooth Earbuds"
    assert res["return_window"]["is_open"] is True

    # Check that context recorded the inspected order
    assert "ord-1001" in ctx.inspected_orders


def test_process_refund_gates_and_validation(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    ticket = _create_test_ticket(seeded_db, cust1)
    ctx = ToolExecutionContext(db=seeded_db, user=cust1, ticket=ticket)

    # Gate a: Missing order_id
    res_no_order = execute_tool_call(
        ctx,
        "process_refund",
        {"order_id": "", "amount": "1299.00", "reason": "Defective item"},
    )
    assert res_no_order["ok"] is False
    assert res_no_order["error"] == "ORDER_ID_REQUIRED"

    # Gate b: Calling process_refund before get_order_details
    res_not_inspected = execute_tool_call(
        ctx,
        "process_refund",
        {"order_id": "ORD-1001", "amount": "1299.00", "reason": "Defective item"},
    )
    assert res_not_inspected["ok"] is False
    assert res_not_inspected["error"] == "LOOK_UP_ORDER_FIRST"

    # Now inspect order details
    execute_tool_call(ctx, "get_order_details", {"order_id": "ORD-1001"})

    # Gate d: Invalid amounts
    for bad_amt in ["invalid", "100.999", "-50.00", "0.00", "0"]:
        res_bad_amt = execute_tool_call(
            ctx,
            "process_refund",
            {"order_id": "ORD-1001", "amount": bad_amt, "reason": "Defective item"},
        )
        assert res_bad_amt["ok"] is False
        assert res_bad_amt["error"] == "AMOUNT_INVALID"

    # Unknown argument rejection
    res_extra_args = execute_tool_call(
        ctx,
        "process_refund",
        {
            "order_id": "ORD-1001",
            "amount": "1299.00",
            "reason": "Defective item",
            "customer_id": str(uuid.uuid4()),
            "status": "processed",
        },
    )
    assert res_extra_args["ok"] is False
    assert res_extra_args["error"] == "UNKNOWN_ARGUMENTS"


def test_process_refund_read_only_when_ticket_escalated(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    ticket = _create_test_ticket(seeded_db, cust1)
    ticket.status = TicketStatus.ESCALATED
    seeded_db.commit()

    ctx = ToolExecutionContext(db=seeded_db, user=cust1, ticket=ticket, read_only_mode=True)
    res = execute_tool_call(
        ctx,
        "process_refund",
        {"order_id": "ORD-1001", "amount": "1299.00", "reason": "Defective item"},
    )
    assert res["ok"] is False
    assert res["error"] == "TICKET_ESCALATED"


def test_escalate_to_human_idempotent_and_summary_cap(seeded_db: Session) -> None:
    cust1 = _get_user_by_email(seeded_db, "customer1@example.com")
    ticket = _create_test_ticket(seeded_db, cust1)
    ctx = ToolExecutionContext(db=seeded_db, user=cust1, ticket=ticket)

    long_summary = "X" * 1500
    res1 = execute_tool_call(
        ctx,
        "escalate_to_human",
        {"summary": long_summary, "priority": "urgent"},
    )
    assert res1["ok"] is True
    assert res1["outcome"] == "ESCALATED"

    # Verify escalation row in DB
    seeded_db.refresh(ticket)
    assert ticket.status == TicketStatus.ESCALATED
    assert len(ticket.escalations) == 1
    assert len(ticket.escalations[0].summary) == 1000
    assert ticket.escalations[0].priority == TicketPriority.URGENT

    # Second call should be idempotent (no duplicate escalation row)
    res2 = execute_tool_call(
        ctx,
        "escalate_to_human",
        {"summary": "Second attempt", "priority": "high"},
    )
    assert res2["ok"] is True
    seeded_db.refresh(ticket)
    assert len(ticket.escalations) == 1
