from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Any
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session
import structlog

from app.agent.policy_search import search_return_policy as do_search_return_policy
from app.core.errors import AppError
from app.core.policy import (
    NON_RETURNABLE_CATEGORIES,
    RETURN_WINDOW_DAYS,
    get_today_date,
)
from app.models.enums import ActorType, EscalationDecision, TicketPriority, TicketStatus
from app.models.models import AuditEvent, Escalation, Order, Ticket, User
from app.services.access import get_order_for_user
from app.services.escalations import create_escalation_for_ticket
from app.services.refunds import Outcome, request_refund

logger = structlog.get_logger("agent.tools")

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_order_details",
            "description": "Retrieves verified order items, delivery status, and return window eligibility. You must call this before requesting a refund.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order number (e.g. 'ORD-1001') or UUID.",
                    }
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_return_policy",
            "description": "Searches the store return and refund policy documentation for specific categories and conditions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "description": "Item category to look up (e.g. 'electronics', 'grocery', 'fashion', 'books').",
                    }
                },
                "required": ["category"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "process_refund",
            "description": "Submits a refund request for an order. Requires get_order_details to have been executed first for the same order.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {
                        "type": "string",
                        "description": "The customer's order number (e.g. 'ORD-1001') or UUID.",
                    },
                    "amount": {
                        "type": "string",
                        "description": "The exact decimal refund amount in INR (e.g. '1299.00'). Must be <= 2 decimal places.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of the return/refund request (10-1000 characters).",
                    },
                },
                "required": ["order_id", "amount", "reason"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate_to_human",
            "description": "Escalates the ticket to human support staff when the customer requests a representative, makes threats, or when policy does not cover the request.",
            "parameters": {
                "type": "object",
                "properties": {
                    "summary": {
                        "type": "string",
                        "description": "Concise summary of the reason for escalation (max 1000 characters).",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "description": "Urgency level of the escalation.",
                    },
                },
                "required": ["summary", "priority"],
                "additionalProperties": False,
            },
        },
    },
]

READ_ONLY_TOOL_NAMES = {"get_order_details", "search_return_policy"}


@dataclass
class ToolExecutionContext:
    db: Session
    user: User
    ticket: Ticket
    inspected_orders: set[str] = field(default_factory=set)
    read_only_mode: bool = False


def _check_extra_args(allowed: set[str], args: dict[str, Any]) -> str | None:
    for k in args.keys():
        if k not in allowed:
            return k
    return None


def execute_tool_call(
    ctx: ToolExecutionContext,
    tool_name: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    """
    Executes a single tool call within the turn context.
    Strictly isolates DB queries, enforces argument schema validation,
    validates pre-conditions, and writes audit logs.
    """
    db = ctx.db
    user = ctx.user
    ticket = ctx.ticket

    # Disallow write tools in read-only mode
    if ctx.read_only_mode and tool_name not in READ_ONLY_TOOL_NAMES:
        return {
            "ok": False,
            "error": "TICKET_ESCALATED",
            "message": "This ticket has already been escalated for human review and cannot accept new automated actions.",
        }

    # 1. get_order_details
    if tool_name == "get_order_details":
        extra = _check_extra_args({"order_id"}, args)
        if extra:
            return {"ok": False, "error": "UNKNOWN_ARGUMENTS", "message": f"Unexpected argument: {extra}"}

        raw_order_id = args.get("order_id")
        if not raw_order_id or not str(raw_order_id).strip():
            return {"ok": False, "error": "ORDER_ID_REQUIRED", "message": "Order ID is required."}

        order_str = str(raw_order_id).strip()
        try:
            order = get_order_for_user(db, user, order_str)
        except AppError:
            return {"ok": False, "error": "ORDER_NOT_FOUND", "message": "Order not found"}
        except Exception as exc:
            logger.error("order_lookup_db_error", error=str(exc))
            return {"ok": False, "error": "INTERNAL_ERROR", "message": "Could not retrieve order details."}

        # Track that order details were inspected during this turn
        ctx.inspected_orders.add(order_str.lower())
        ctx.inspected_orders.add(str(order.id).lower())
        if order.order_number:
            ctx.inspected_orders.add(order.order_number.lower())

        # Compute return window eligibility info
        today = get_today_date()
        is_open = False
        last_eligible = None
        if order.delivery_date:
            last_eligible = order.delivery_date + timedelta(days=RETURN_WINDOW_DAYS)
            is_open = today <= last_eligible and not any(
                it.category.value in NON_RETURNABLE_CATEGORIES for it in order.items
            )

        items_data = [
            {
                "name": it.name,
                "category": it.category.value,
                "quantity": it.quantity,
                "unit_price": str(it.unit_price),
            }
            for it in order.items
        ]
        refunds_data = [
            {"status": r.status.value, "amount": str(r.amount)}
            for r in order.refunds
        ]

        result = {
            "ok": True,
            "order_number": order.order_number,
            "order_id": str(order.id),
            "status": order.status.value,
            "delivery_date": str(order.delivery_date) if order.delivery_date else None,
            "total_amount": str(order.total_amount),
            "items": items_data,
            "refunds": refunds_data,
            "return_window": {
                "eligible_until": str(last_eligible) if last_eligible else None,
                "is_open": is_open,
            },
        }

        # Audit event
        audit = AuditEvent(
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="agent.tool_called",
            entity_type="order",
            entity_id=order.id,
            audit_metadata={"tool": "get_order_details", "outcome": "SUCCESS"},
        )
        db.add(audit)
        db.flush()
        return result

    # 2. search_return_policy
    elif tool_name == "search_return_policy":
        extra = _check_extra_args({"category"}, args)
        if extra:
            return {"ok": False, "error": "UNKNOWN_ARGUMENTS", "message": f"Unexpected argument: {extra}"}

        category = str(args.get("category", "")).strip()
        policy_result = do_search_return_policy(category)

        audit = AuditEvent(
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="agent.tool_called",
            entity_type="ticket",
            entity_id=ticket.id,
            audit_metadata={"tool": "search_return_policy", "outcome": "SUCCESS"},
        )
        db.add(audit)
        db.flush()

        return {"ok": True, "policy_text": policy_result}

    # 3. process_refund
    elif tool_name == "process_refund":
        extra = _check_extra_args({"order_id", "amount", "reason"}, args)
        if extra:
            return {"ok": False, "error": "UNKNOWN_ARGUMENTS", "message": f"Unexpected argument: {extra}"}

        raw_order_id = args.get("order_id")
        if not raw_order_id or not str(raw_order_id).strip():
            return {"ok": False, "error": "ORDER_ID_REQUIRED", "message": "Order ID is required."}

        order_str = str(raw_order_id).strip()

        # Gate b: Order details must have been looked up first in this run
        if order_str.lower() not in ctx.inspected_orders:
            return {
                "ok": False,
                "error": "LOOK_UP_ORDER_FIRST",
                "message": "You must look up order details before requesting a refund.",
            }

        # Gate c: Ticket must not already have a pending escalation
        has_pending_esc = db.scalar(
            select(Escalation).where(
                Escalation.ticket_id == ticket.id,
                Escalation.decision.in_([
                    EscalationDecision.PENDING,
                    EscalationDecision.MORE_INFO_REQUESTED,
                ]),
            )
        )
        if has_pending_esc or ticket.status in (TicketStatus.ESCALATED, TicketStatus.RESOLVED, TicketStatus.CLOSED):
            return {
                "ok": False,
                "error": "TICKET_ESCALATED",
                "message": "This ticket has already been escalated for human review.",
            }

        # Gate d: Amount validation
        raw_amount = args.get("amount")
        try:
            parsed_amount = Decimal(str(raw_amount))
            if parsed_amount <= 0 or parsed_amount.as_tuple().exponent < -2:
                return {"ok": False, "error": "AMOUNT_INVALID", "message": "Invalid refund amount."}
        except (InvalidOperation, TypeError, ValueError):
            return {"ok": False, "error": "AMOUNT_INVALID", "message": "Invalid refund amount format."}

        reason = str(args.get("reason", "")).strip() or "Customer refund request via AI agent"

        # Resolve order to get UUID for refund call
        try:
            order = get_order_for_user(db, user, order_str)
        except AppError:
            return {"ok": False, "error": "ORDER_NOT_FOUND", "message": "Order not found"}

        # Call the single-path refund service
        try:
            ref_result = request_refund(
                db=db,
                user=user,
                order_id=order.id,
                amount=parsed_amount,
                reason=reason,
                ticket_id=ticket.id,
            )
        except Exception as exc:
            logger.error("refund_service_exception", error=str(exc))
            return {
                "ok": False,
                "outcome": "ERROR",
                "reason_code": "INTERNAL_ERROR",
                "message": "The refund was NOT completed.",
            }

        outcome_val = ref_result.outcome.value

        audit = AuditEvent(
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="agent.tool_called",
            entity_type="refund",
            entity_id=ref_result.refund.id if ref_result.refund else order.id,
            audit_metadata={"tool": "process_refund", "outcome": outcome_val},
        )
        db.add(audit)
        db.flush()

        if ref_result.outcome == Outcome.PROCESSED:
            return {
                "ok": True,
                "outcome": "PROCESSED",
                "refund_id": str(ref_result.refund.id),
                "amount": str(ref_result.refund.amount),
                "message": ref_result.message or "Refund processed successfully.",
            }
        elif ref_result.outcome == Outcome.ESCALATED:
            return {
                "ok": True,
                "outcome": "ESCALATED",
                "message": "No refund has been issued yet; a human reviewer will decide.",
            }
        elif ref_result.outcome == Outcome.DUPLICATE:
            return {
                "ok": True,
                "outcome": "DUPLICATE",
                "refund_id": str(ref_result.refund.id),
                "message": ref_result.message or "A duplicate refund already exists for this order.",
            }
        elif ref_result.outcome == Outcome.REJECTED:
            return {
                "ok": False,
                "outcome": "REJECTED",
                "reason_code": ref_result.reason_code.value if ref_result.reason_code else "POLICY_REJECTION",
                "message": ref_result.message,
            }
        else:
            return {
                "ok": False,
                "outcome": "ERROR",
                "reason_code": ref_result.reason_code.value if ref_result.reason_code else "PAYMENT_FAILED",
                "message": "The refund was NOT completed.",
            }

    # 4. escalate_to_human
    elif tool_name == "escalate_to_human":
        extra = _check_extra_args({"summary", "priority"}, args)
        if extra:
            return {"ok": False, "error": "UNKNOWN_ARGUMENTS", "message": f"Unexpected argument: {extra}"}

        raw_summary = str(args.get("summary", "")).strip()[:1000]
        raw_priority = str(args.get("priority", "high")).strip().lower()

        priority_map = {
            "low": TicketPriority.LOW,
            "medium": TicketPriority.MEDIUM,
            "high": TicketPriority.HIGH,
            "urgent": TicketPriority.URGENT,
        }
        target_prio = priority_map.get(raw_priority, TicketPriority.HIGH)

        esc = create_escalation_for_ticket(
            db=db,
            ticket=ticket,
            summary=raw_summary or "Escalation requested by customer",
            priority=target_prio,
            source="ai_agent",
        )

        audit = AuditEvent(
            actor_id=user.id,
            actor_type=ActorType.CUSTOMER,
            event_type="agent.tool_called",
            entity_type="escalation",
            entity_id=esc.id,
            audit_metadata={"tool": "escalate_to_human", "outcome": "ESCALATED"},
        )
        db.add(audit)
        db.flush()

        return {
            "ok": True,
            "outcome": "ESCALATED",
            "message": "This ticket has been escalated for human review.",
        }

    return {"ok": False, "error": "UNKNOWN_TOOL", "message": f"Tool '{tool_name}' is not recognized."}
