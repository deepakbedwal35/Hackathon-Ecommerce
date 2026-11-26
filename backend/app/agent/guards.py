import re
from typing import Any
import uuid
from sqlalchemy.orm import Session
import structlog

from app.agent.prompts import CANARY_TOKEN
from app.models.enums import ActorType
from app.models.models import AuditEvent, Ticket, User

logger = structlog.get_logger("agent.guards")

INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous\s+)?instructions",
    r"disregard\s+(?:all\s+)?(?:previous\s+)?rules",
    r"system\s+prompt",
    r"you\s+are\s+now",
    r"developer\s+mode",
    r"override\s+(?:all\s+)?rules",
    r"(?:act|login|behave)\s+as\s+admin",
    r"i('?m|\s+am)\s+(?:an?\s+)?admin",
    r"pretend\s+you\s+are",
    r"jailbreak",
    r"canary_sec_token",
]


def flag_suspected_injection(
    db: Session,
    user: User,
    ticket: Ticket,
    text: str,
) -> bool:
    """
    Evaluates customer input for common prompt injection or manipulation markers.
    Flag-only defense: records audit event without blocking execution.
    """
    if not text:
        return False

    lowered = text.lower()
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, lowered):
            logger.warning("injection_suspected", pattern=pattern, ticket_id=str(ticket.id))
            audit = AuditEvent(
                actor_id=user.id,
                actor_type=ActorType.CUSTOMER,
                event_type="agent.injection_suspected",
                entity_type="ticket",
                entity_id=ticket.id,
                audit_metadata={"pattern_detected": pattern},
            )
            db.add(audit)
            db.flush()
            return True

    return False


CLAIM_PATTERNS = [
    r"\b(?:refund|money)\s+(?:has\s+been|was|is)?\s*(?:successfully\s+)?(?:processed|issued|approved|completed|sent|refunded)\b",
    r"\bprocessed\s+(?:your|the)\s+refund\b",
    r"\bapproved\s+(?:your|the)\s+refund\b",
    r"\byour\s+refund\s+is\s+processed\b",
    r"\brefund\s+of\s+inr\s*[\d,.]+\s+(?:has\s+been\s+)?processed\b",
]


def verify_reply_claims(
    db: Session,
    user: User,
    ticket: Ticket,
    reply: str,
    tool_trace: list[dict[str, Any]],
    ticket_state_has_processed: bool = False,
) -> str:
    """
    Validates that any claim of refund issuance in the agent's reply is strictly
    grounded in an actual PROCESSED tool outcome or existing processed refund.
    If an ungrounded refund claim is found, rewrites it with a verified factual status.
    Also strips any leaked canary token.
    """
    if not reply:
        return reply

    # 1. Canary leak check
    if CANARY_TOKEN in reply:
        logger.error("canary_token_leaked", ticket_id=str(ticket.id))
        audit = AuditEvent(
            actor_id=user.id,
            actor_type=ActorType.SYSTEM,
            event_type="agent.canary_triggered",
            entity_type="ticket",
            entity_id=ticket.id,
            audit_metadata={"reason": "Canary token detected in reply"},
        )
        db.add(audit)
        db.flush()
        return "I am here to assist you with your orders and returns. How may I help you today?"

    # 2. Check for processed refund outcome in tool trace
    has_processed_tool_call = False
    last_outcome = None
    last_message = ""

    for step in tool_trace:
        res = step.get("result", {})
        outcome = res.get("outcome")
        if outcome:
            last_outcome = outcome
            last_message = res.get("message", "")
        if outcome == "PROCESSED":
            has_processed_tool_call = True
            break

    # If backed by truth, reply is valid
    if has_processed_tool_call or ticket_state_has_processed:
        return reply

    # Check if reply claims a refund was processed
    claims_refund = False
    for pattern in CLAIM_PATTERNS:
        if re.search(pattern, reply, re.IGNORECASE):
            claims_refund = True
            break

    if not claims_refund:
        return reply

    # Ungrounded claim detected! Correct it based on actual outcome
    logger.warning("ungrounded_refund_claim_corrected", ticket_id=str(ticket.id), last_outcome=last_outcome)
    audit = AuditEvent(
        actor_id=user.id,
        actor_type=ActorType.SYSTEM,
        event_type="agent.claim_corrected",
        entity_type="ticket",
        entity_id=ticket.id,
        audit_metadata={"original_claim": reply[:200], "last_outcome": last_outcome},
    )
    db.add(audit)
    db.flush()

    if last_outcome == "ESCALATED":
        return (
            "Your refund request requires human review and has been submitted to our team. "
            "No refund has been issued yet; a staff member will review and decide on your request."
        )
    elif last_outcome == "REJECTED":
        return (
            "Your refund request could not be processed due to store policy. "
            f"{last_message if last_message else 'Please refer to our return policy for further details.'}"
        )
    elif last_outcome in ("ERROR", "PAYMENT_FAILED"):
        return (
            "The refund was NOT completed. We encountered an error during processing. "
            "Your request has been logged and a support representative will follow up."
        )
    else:
        return (
            "No refund has been issued. If you would like to initiate a return or refund, "
            "please provide your order number so we can look up your details."
        )
