"""
=============================================================================
LOUD NOTICE: SIMULATED / MOCK PAYMENT SERVICE ONLY!
NO REAL BANKING, GATEWAY, OR PAYMENT RAILS ARE CONNECTED OR INVOKED.
This mock provides deterministic simulation of payment success, transient
gateway network timeouts (fail_once), and terminal payment processor declines
for automated unit and integration tests.
=============================================================================
"""
from dataclasses import dataclass
from decimal import Decimal
import threading
import uuid

from app.core.config import settings


@dataclass(frozen=True)
class PaymentResult:
    success: bool
    reference: str | None = None
    error: str | None = None


# Thread-safe in-memory registry for idempotency and attempt counting
# Map: refund_id -> (PaymentResult, attempt_count)
_payment_registry: dict[uuid.UUID, tuple[PaymentResult, int]] = {}
_lock = threading.Lock()


def execute_refund_payment(refund_id: uuid.UUID, amount: Decimal) -> PaymentResult:
    """
    Dispatches a mock refund transaction to simulated banking rails.
    Enforces idempotency per refund_id: calling twice returns the same
    reference and never re-dispatches.

    Behavior mode is governed by settings.PAYMENT_MOCK_MODE:
      - 'ok' (default): Generates a unique transaction reference and succeeds.
      - 'fail': Simulates an outright terminal processor rejection.
      - 'fail_once': Fails on the first invocation; succeeds on subsequent retry.
    """
    with _lock:
        if refund_id in _payment_registry:
            prev_result, attempts = _payment_registry[refund_id]
            if prev_result.success:
                # Idempotent response: return original reference without re-paying
                return prev_result
            new_attempts = attempts + 1
        else:
            new_attempts = 1

        mode = getattr(settings, "PAYMENT_MOCK_MODE", "ok").lower()

        if mode == "fail":
            result = PaymentResult(
                success=False,
                reference=None,
                error="Payment processor declined the transaction.",
            )
            _payment_registry[refund_id] = (result, new_attempts)
            return result

        if mode == "fail_once":
            if new_attempts == 1:
                result = PaymentResult(
                    success=False,
                    reference=None,
                    error="Transient network timeout with payment gateway.",
                )
                _payment_registry[refund_id] = (result, new_attempts)
                return result

            # On second attempt, succeed
            reference = f"pay_ref_{uuid.uuid4().hex[:12]}"
            result = PaymentResult(success=True, reference=reference, error=None)
            _payment_registry[refund_id] = (result, new_attempts)
            return result

        # Default 'ok' mode
        reference = f"pay_ref_{uuid.uuid4().hex[:12]}"
        result = PaymentResult(success=True, reference=reference, error=None)
        _payment_registry[refund_id] = (result, new_attempts)
        return result


def clear_payment_mock_registry() -> None:
    """Resets the mock payment state between test runs."""
    with _lock:
        _payment_registry.clear()
