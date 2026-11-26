from collections import defaultdict
from datetime import datetime, timezone
import math
from typing import DefaultDict
from fastapi import status
from app.core.errors import AppError

# In-memory store: (client_ip, email) -> list of failure timestamps
# NOTE: This implementation is single-process only. A production or multi-replica deployment
# would use Redis (e.g. redis-py with sliding window or token bucket Lua scripts).
_failed_attempts: DefaultDict[tuple[str, str], list[datetime]] = defaultdict(list)

MAX_FAILED_ATTEMPTS = 5
WINDOW_SECONDS = 60


def check_rate_limit(client_ip: str, email: str) -> None:
    """
    Checks if the client IP and email have exceeded MAX_FAILED_ATTEMPTS in WINDOW_SECONDS.
    Raises standard 429 RATE_LIMITED AppError with Retry-After header if blocked.
    """
    now = datetime.now(timezone.utc)
    key = (client_ip.strip(), email.strip().lower())
    history = _failed_attempts[key]

    # Purge attempts older than the window
    recent_failures = [t for t in history if (now - t).total_seconds() < WINDOW_SECONDS]
    _failed_attempts[key] = recent_failures

    if len(recent_failures) >= MAX_FAILED_ATTEMPTS:
        oldest_recent = recent_failures[0]
        elapsed = (now - oldest_recent).total_seconds()
        retry_after = max(1, math.ceil(WINDOW_SECONDS - elapsed))
        raise AppError(
            code="RATE_LIMITED",
            message="Too many failed attempts. Please try again later.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            details={"retry_after": retry_after},
            headers={"Retry-After": str(retry_after)},
        )


def record_failure(client_ip: str, email: str) -> None:
    """Records a timestamped failure for (client_ip, email)."""
    now = datetime.now(timezone.utc)
    key = (client_ip.strip(), email.strip().lower())
    _failed_attempts[key].append(now)


def reset_failures(client_ip: str, email: str) -> None:
    """Clears failure history upon successful authentication."""
    key = (client_ip.strip(), email.strip().lower())
    _failed_attempts.pop(key, None)


def clear_all_rate_limits() -> None:
    """Helper to reset all rate limit state (primarily for tests)."""
    _failed_attempts.clear()
