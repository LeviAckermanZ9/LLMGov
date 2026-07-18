"""
LLMGov — Structured JSON Logging

Configures Python's stdlib logging to emit JSON lines with consistent
fields (timestamp, level, message, trace_id) so logs are parseable by
ELK, Loki, CloudWatch, or any structured-log ingestion pipeline.

Usage:
    from app.core.logging import get_logger
    logger = get_logger(__name__)
    logger.info("request processed", extra={"model": "gpt-4o", "latency_ms": 142})
"""

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

from app.middleware.request_id import get_request_id


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Attach trace_id from the current request context (if available)
        trace_id = get_request_id()
        if trace_id:
            log_entry["trace_id"] = trace_id

        # Merge any extra fields passed via `extra={...}`
        for key in ("model", "provider", "app_id", "latency_ms", "status_code", "has_pii_redacted"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        # Exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    """Configure root logger with JSON output to stdout."""
    root = logging.getLogger()
    root.setLevel(level.upper())

    # Remove any existing handlers to avoid duplicate output
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.addHandler(handler)

    # Quiet down noisy third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger. Call setup_logging() once at startup first."""
    return logging.getLogger(name)
