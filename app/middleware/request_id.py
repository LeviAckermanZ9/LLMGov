"""
LLMGov — Request ID Correlation Middleware

Generates or propagates a trace_id (UUID4) for every request:
  1. Reads X-Request-ID from the incoming request header (if present).
  2. Falls back to generating a new uuid4.
  3. Stores it in a contextvars.ContextVar so any code in the call
     stack (logging, telemetry writes, error responses) can access
     the same trace_id without explicit parameter passing.
  4. Adds X-Request-ID to the response headers.

This is the birth point of trace_id, which appears as the first column
in every ClickHouse table (llm_metrics, llm_audit_logs, llm_eval_results).
"""

import uuid
from contextvars import ContextVar
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

# ── Context variable: accessible from any async code in the request ──
_request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id", default=None)


def get_request_id() -> Optional[str]:
    """Retrieve the current request's trace_id. Returns None outside a request."""
    return _request_id_ctx.get()


class RequestIDMiddleware(BaseHTTPMiddleware):
    """ASGI middleware that manages X-Request-ID propagation."""

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
        finally:
            _request_id_ctx.reset(token)
