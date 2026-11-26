import logging
import sys
from typing import Any
import structlog

SENSITIVE_KEYS = {"password", "token", "authorization", "email", "content"}


def mask_sensitive_data(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Recursively masks sensitive keys with [MASKED]."""

    def _mask(key: str, val: Any) -> Any:
        if isinstance(val, dict):
            return {k: _mask(k, v) for k, v in val.items()}
        if isinstance(val, list):
            return [_mask(key, item) for item in val]
        if key.lower() in SENSITIVE_KEYS:
            return "[MASKED]"
        return val

    return {k: _mask(k, v) for k, v in event_dict.items()}


def add_request_id(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """Ensures request_id is always present in output JSON logs."""
    if "request_id" not in event_dict:
        ctx_req_id = structlog.contextvars.get_contextvars().get("request_id")
        event_dict["request_id"] = ctx_req_id
    return event_dict


def setup_logging(log_level: str = "INFO") -> None:
    """Configures structured JSON logging outputting strictly to stdout."""
    root_logger = logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(logging.Formatter("%(message)s"))
    root_logger.addHandler(stdout_handler)
    root_logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    # Suppress duplicate uvicorn access logs to rely on our middleware
    logging.getLogger("uvicorn.access").handlers = []

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        add_request_id,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", key="timestamp"),
        mask_sensitive_data,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    structlog.configure(
        processors=shared_processors + [
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
