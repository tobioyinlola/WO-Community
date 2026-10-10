"""Structured JSON logging with redaction at source."""

import logging
from typing import Any

import structlog

REDACTED = "[redacted]"
SENSITIVE_KEYS = (
    "password",
    "token",
    "secret",
    "authorization",
    "cookie",
    "api_key",
    "refresh",
    "email_body",
    "private_key",
)


def is_sensitive(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SENSITIVE_KEYS)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: REDACTED if is_sensitive(str(k)) else redact(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [redact(item) for item in value]
    return value


def redact_processor(_logger: Any, _name: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    return redact(event_dict)


shared_processors: list[Any] = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_logger_name,
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    structlog.processors.format_exc_info,
    redact_processor,
]


def configure_logging() -> None:
    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logging.captureWarnings(True)
