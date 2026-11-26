from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import time
from typing import Any
import uuid

from sqlalchemy import select, text
from sqlalchemy.orm import Session
import structlog

from app.agent.guards import flag_suspected_injection, verify_reply_claims
from app.agent.llm import LLMClient, LLMResponse, get_default_llm_client
from app.agent.prompts import SYSTEM_PROMPT, build_ticket_state_block
from app.agent.tools import (
    READ_ONLY_TOOL_NAMES,
    TOOL_SCHEMAS,
    ToolExecutionContext,
    execute_tool_call,
)
from app.models.enums import (
    ActorType,
    EscalationDecision,
    RefundStatus,
    SenderType,
    TicketPriority,
    TicketStatus,
)
from app.models.models import AuditEvent, Escalation, Message, Refund, Ticket, User
from app.services.escalations import create_escalation_for_ticket

logger = structlog.get_logger("agent.runner")

MAX_TOOL_ITERATIONS = 6
MAX_TOOL_CALLS = 8
WALL_CLOCK_BUDGET_SECONDS = 45.0
FALLBACK_REPLY = (
    "We're having trouble right now. Your request is saved and a team member will review it."
)


@dataclass
class AgentResult:
    reply_message: Message | None
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    skipped: bool = False
    fallback: bool = False
    flags: dict[str, Any] = field(default_factory=dict)


def _compute_lock_id(ticket_id: uuid.UUID) -> int:
    """Computes a deterministic 64-bit integer advisory lock key from ticket_id."""
    raw_hash = hashlib.md5(ticket_id.bytes).hexdigest()
    # 15 hex chars fit into a positive signed 64-bit int with shift
    return int(raw_hash[:15], 16) - (1 << 59)


def run_agent_turn(
    db: Session,
    user: User,
    ticket: Ticket,
    llm_client: LLMClient | None = None,
) -> AgentResult:
    """
    Executes one conversational turn of the AI support agent for a ticket.
    Guarantees:
    - Advisory per-ticket transaction lock prevents concurrent agent executions.
    - Customer message was already committed prior to running.
    - Model sees only validated tools; write tools withheld in read-only mode.
    - Hard caps on tool iterations, tool counts, and wall-clock execution time.
    - Automated fallback on tool failures or LLM timeouts with ticket escalation.
    """
    client = llm_client or get_default_llm_client()
    lock_id = _compute_lock_id(ticket.id)

    # 1. Acquire per-ticket advisory lock
    lock_acquired = db.scalar(
        text("SELECT pg_try_advisory_xact_lock(:lock_id)"),
        {"lock_id": lock_id},
    )
    if not lock_acquired:
        logger.info("agent_turn_skipped_lock_busy", ticket_id=str(ticket.id))
        return AgentResult(reply_message=None, skipped=True)

    # 2. Check read-only mode (escalated, resolved, or closed)
    has_active_esc = db.scalar(
        select(Escalation).where(
            Escalation.ticket_id == ticket.id,
            Escalation.decision.in_([
                EscalationDecision.PENDING,
                EscalationDecision.MORE_INFO_REQUESTED,
            ]),
        )
    )
    read_only_mode = bool(
        has_active_esc
        or ticket.status in (TicketStatus.ESCALATED, TicketStatus.RESOLVED, TicketStatus.CLOSED)
    )

    offered_tools = [
        t for t in TOOL_SCHEMAS
        if not read_only_mode or t["function"]["name"] in READ_ONLY_TOOL_NAMES
    ]

    # 3. Scan latest customer message for suspected injection
    stmt_last_msg = (
        select(Message)
        .where(Message.ticket_id == ticket.id)
        .order_by(Message.created_at.desc())
    )
    latest_msg = db.scalars(stmt_last_msg).first()
    injection_suspected = False
    if latest_msg and latest_msg.sender_type == SenderType.CUSTOMER:
        injection_suspected = flag_suspected_injection(db, user, ticket, latest_msg.content)

    # Build prompt context
    state_block = build_ticket_state_block(db, ticket, injection_suspected=injection_suspected)
    system_prompt = f"{SYSTEM_PROMPT}\n\n{state_block}"

    # Load up to 30 past messages in chronological order
    stmt_history = (
        select(Message)
        .where(Message.ticket_id == ticket.id)
        .order_by(Message.created_at.asc())
    )
    all_messages = db.scalars(stmt_history).all()[-30:]

    history_payload: list[dict[str, Any]] = []
    for m in all_messages:
        if m.sender_type == SenderType.CUSTOMER:
            history_payload.append({"role": "user", "content": m.content})
        elif m.sender_type == SenderType.AGENT_AI:
            history_payload.append({"role": "assistant", "content": m.content})
        else:
            history_payload.append({"role": "assistant", "content": f"[Support team] {m.content}"})

    # Prepare tool execution context
    tool_ctx = ToolExecutionContext(
        db=db,
        user=user,
        ticket=ticket,
        read_only_mode=read_only_mode,
    )
    # Pre-populate inspected orders if linked to ticket
    if ticket.order:
        tool_ctx.inspected_orders.add(str(ticket.order.id).lower())
        if ticket.order.order_number:
            tool_ctx.inspected_orders.add(ticket.order.order_number.lower())

    tool_trace: list[dict[str, Any]] = []
    total_tool_calls = 0
    malformed_streak = 0
    start_time = time.time()
    trigger_fallback = False

    # 4. Agent Tool Execution Loop
    for iteration in range(MAX_TOOL_ITERATIONS):
        # Check wall-clock budget
        if time.time() - start_time > WALL_CLOCK_BUDGET_SECONDS:
            logger.warning("agent_wall_clock_budget_exceeded", ticket_id=str(ticket.id))
            trigger_fallback = True
            break

        try:
            resp: LLMResponse = client.chat(
                system=system_prompt,
                messages=history_payload,
                tools=offered_tools if offered_tools else None,
            )
        except Exception as exc:
            logger.error("llm_call_exception", error=str(exc), ticket_id=str(ticket.id))
            trigger_fallback = True
            break

        # If LLM returned tool calls
        if resp.tool_calls:
            if total_tool_calls + len(resp.tool_calls) > MAX_TOOL_CALLS:
                logger.warning("agent_max_tool_calls_exceeded", ticket_id=str(ticket.id))
                trigger_fallback = True
                break

            # Append assistant message with tool calls
            history_payload.append({
                "role": "assistant",
                "content": resp.text or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.name, "arguments": tc.arguments},
                        "name": tc.name,
                        "arguments": tc.arguments,
                    }
                    for tc in resp.tool_calls
                ],
            })

            has_malformed = False
            for tc in resp.tool_calls:
                total_tool_calls += 1
                try:
                    tool_result = execute_tool_call(tool_ctx, tc.name, tc.arguments)
                except Exception as exc:
                    logger.error("tool_execution_uncaught_error", tool=tc.name, error=str(exc))
                    tool_result = {"ok": False, "error": "INTERNAL_ERROR", "message": "Tool execution failed"}

                if not tool_result.get("ok", True) and tool_result.get("error") in (
                    "UNKNOWN_ARGUMENTS",
                    "UNKNOWN_TOOL",
                ):
                    has_malformed = True

                tool_trace.append({
                    "tool": tc.name,
                    "arguments": tc.arguments,
                    "result": tool_result,
                })

                # Append tool response
                history_payload.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": json.dumps(tool_result),
                })

            if has_malformed:
                malformed_streak += 1
                if malformed_streak >= 2:
                    logger.warning("agent_malformed_tool_streak_fallback", ticket_id=str(ticket.id))
                    trigger_fallback = True
                    break
            else:
                malformed_streak = 0

            # Continue loop to next turn
            continue

        # Model returned text without tool calls
        if resp.text:
            final_text = resp.text
            break
    else:
        # Loop finished without natural termination (hit MAX_TOOL_ITERATIONS)
        logger.warning("agent_max_iterations_reached", ticket_id=str(ticket.id))
        trigger_fallback = True

    # 5. Fallback Handler
    if trigger_fallback:
        fallback_msg = Message(
            ticket_id=ticket.id,
            sender_type=SenderType.AGENT_AI,
            sender_id=None,
            content=FALLBACK_REPLY,
        )
        db.add(fallback_msg)

        create_escalation_for_ticket(
            db=db,
            ticket=ticket,
            summary="Automated agent loop encountered an issue and escalated for human review.",
            priority=TicketPriority.MEDIUM,
            source="agent_failure",
        )

        audit = AuditEvent(
            actor_id=user.id,
            actor_type=ActorType.SYSTEM,
            event_type="agent.failed",
            entity_type="ticket",
            entity_id=ticket.id,
            audit_metadata={"iterations": iteration if 'iteration' in locals() else 0},
        )
        db.add(audit)
        db.commit()
        db.refresh(fallback_msg)
        return AgentResult(reply_message=fallback_msg, tool_trace=tool_trace, fallback=True)

    # 6. Verify and persist normal agent reply
    has_processed_in_ticket = bool(
        ticket.refunds and any(r.status == RefundStatus.PROCESSED for r in ticket.refunds)
    )
    verified_text = verify_reply_claims(
        db=db,
        user=user,
        ticket=ticket,
        reply=final_text,
        tool_trace=tool_trace,
        ticket_state_has_processed=has_processed_in_ticket,
    )

    agent_msg = Message(
        ticket_id=ticket.id,
        sender_type=SenderType.AGENT_AI,
        sender_id=None,
        content=verified_text,
    )
    db.add(agent_msg)
    ticket.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(agent_msg)

    return AgentResult(reply_message=agent_msg, tool_trace=tool_trace)
