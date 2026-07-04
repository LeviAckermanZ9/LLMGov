"""
LLMGov — Global Exception Handler

Catches all unhandled exceptions and returns a structured JSON error
response instead of FastAPI's default HTML 500 page. Every error
response includes the request's trace_id for correlation.

In production, error messages are generic to avoid leaking internals.
In debug mode (LOG_LEVEL=debug), the full traceback is included.
"""

import traceback

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.logging import get_logger
from app.middleware.request_id import get_request_id

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register global exception handlers on the FastAPI app instance."""

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        trace_id = get_request_id() or "unknown"

        logger.error(
            "Unhandled exception",
            extra={"status_code": 500},
            exc_info=exc,
        )

        # Include traceback only when running in debug mode
        detail: str | None = None
        if logger.isEnabledFor(10):  # DEBUG level
            detail = traceback.format_exc()

        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "type": "internal_error",
                    "message": "An internal error occurred." if not detail else str(exc),
                    "trace_id": trace_id,
                    **({"detail": detail} if detail else {}),
                }
            },
        )
