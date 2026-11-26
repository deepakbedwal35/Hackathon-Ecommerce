from decimal import Decimal
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.models.enums import (
    EscalationDecision,
    OrderStatus,
    RefundStatus,
    TicketCategory,
    TicketPriority,
    TicketStatus,
)

router = APIRouter(tags=["Meta"])

LABEL_MAP: dict[str, str] = {
    # TicketCategory
    TicketCategory.ORDER_ISSUE.value: "Order issue",
    TicketCategory.REFUND.value: "Refund",
    TicketCategory.DELIVERY.value: "Delivery",
    TicketCategory.PAYMENT.value: "Payment",
    TicketCategory.PRODUCT.value: "Product",
    TicketCategory.OTHER.value: "Other",

    # TicketPriority
    TicketPriority.LOW.value: "Low",
    TicketPriority.MEDIUM.value: "Medium",
    TicketPriority.HIGH.value: "High",
    TicketPriority.URGENT.value: "Urgent",

    # TicketStatus
    TicketStatus.OPEN.value: "Open",
    TicketStatus.AWAITING_CUSTOMER.value: "Awaiting customer",
    TicketStatus.ESCALATED.value: "Escalated",
    TicketStatus.RESOLVED.value: "Resolved",
    TicketStatus.CLOSED.value: "Closed",

    # OrderStatus
    OrderStatus.PLACED.value: "Placed",
    OrderStatus.SHIPPED.value: "Shipped",
    OrderStatus.DELIVERED.value: "Delivered",
    OrderStatus.CANCELLED.value: "Cancelled",

    # RefundStatus
    RefundStatus.PENDING_REVIEW.value: "Pending review",
    RefundStatus.APPROVED.value: "Approved",
    RefundStatus.PROCESSED.value: "Processed",
    RefundStatus.REJECTED.value: "Rejected",
    RefundStatus.FAILED.value: "Failed",

    # EscalationDecision
    EscalationDecision.PENDING.value: "Pending",
    EscalationDecision.APPROVED.value: "Approved",
    EscalationDecision.REJECTED.value: "Rejected",
    EscalationDecision.MORE_INFO_REQUESTED.value: "More info requested",
}


def _enum_options(enum_cls) -> list[dict[str, str]]:
    options = []
    for item in enum_cls:
        label = LABEL_MAP.get(item.value, item.value.replace("_", " ").capitalize())
        options.append({"value": item.value, "label": label})
    return options


@router.get("/enums")
def get_meta_enums() -> dict[str, list[dict[str, str]]]:
    """Returns all system enums with consistent sentence-case labels."""
    return {
        "ticket_categories": _enum_options(TicketCategory),
        "ticket_priorities": _enum_options(TicketPriority),
        "ticket_statuses": _enum_options(TicketStatus),
        "order_statuses": _enum_options(OrderStatus),
        "refund_statuses": _enum_options(RefundStatus),
        "escalation_decisions": _enum_options(EscalationDecision),
    }


@router.get("/config")
def get_meta_config() -> dict[str, object]:
    """Returns safe public policy configuration settings without exposing secrets."""
    limit_val = settings.AUTO_REFUND_LIMIT
    try:
        limit_float = float(limit_val)
    except (ValueError, TypeError):
        limit_float = 5000.0
    return {
        "refund_review_mode": getattr(settings, "REFUND_REVIEW_MODE", "above_limit"),
        "auto_refund_limit": limit_float,
        "return_window_days": settings.RETURN_WINDOW_DAYS,
    }
