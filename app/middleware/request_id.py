"""
LLMGov — Request ID + Error Handling Middleware

Combined middleware that:
  1. Generates/propagates X-Request-ID (trace_id) via contextvars.
  2. Catches all unhandled exceptions and returns structured JSON
     error responses — solving the Starlette BaseHTTPMiddleware
     exception-handler ordering issue where @app.exception_handler
     doesn't catch exceptions that bubble through outer middleware.

This is the outermost middleware, so it sees every request and every
exception. Error responses include trace_id for correlation.
"""

import json
import traceback
import uuid
from contextvars import ContextVar
from typing import Optional

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response, JSONResponse

# ── Context variable: accessible from any async code in the request ──
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)

logger = logging.getLogger(__name__)


def get_request_id() -> Optional[str]:
    """Retrieve the current request's trace_id. Returns None outside a request."""
    return _request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware that:
    - Manages X-Request-ID propagation
    - Catches unhandled exceptions (outermost error boundary)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Accept caller-provided ID or generate a new one
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store in context for the duration of this request
        token = _request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
            response.headers["X-Request-ID"] = request_id
            return response
        except Exception as exc:
            # ── This is the real error boundary ──
            logger.error(
                "Unhandled exception",
                extra={"status_code": 500},
                exc_info=exc,
            )

            # Include traceback only when running in debug mode
            detail: str | None = None
            if logger.isEnabledFor(10):  # DEBUG level
                detail = traceback.format_exc()

            error_response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "type": "internal_error",
                        "message": (
                            "An internal error occurred." if not detail else str(exc)
                        ),
                        "trace_id": request_id,
                        **({"detail": detail} if detail else {}),
                    }
                },
            )
            error_response.headers["X-Request-ID"] = request_id
            return error_response
        finally:
            _request_id_ctx.reset(token)
