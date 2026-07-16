"""
LLMGov — Gateway Application Entry Point

FastAPI application with health check, structured logging,
request-ID correlation, and global error handling wired in.
Chat completions route is live (W1-C3). Additional routes
(registry, eval) are mounted in later chunks.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.api.completions import router as completions_router
from app.config.settings import settings
from app.core.logging import get_logger, setup_logging
from app.middleware.request_id import RequestIDMiddleware

# ── Initialize structured logging before anything else ──
setup_logging(level=settings.log_level)
logger = get_logger(__name__)

from app.core.redis import redis_lifespan


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Startup / shutdown lifecycle hook.
    Initializes the Redis connection pool for caching, API key authentication, and rate limiting.
    """
    logger.info(
        "LLMGov gateway starting",
        extra={"model": None, "provider": None},
    )
    
    async with redis_lifespan(app):
        yield
    # ── Shutdown ──
    logger.info("LLMGov gateway shutting down")


app = FastAPI(
    title="LLMGov",
    summary="Production-grade LLM gateway",
    description=(
        "Unified routing, semantic caching, safety guardrails, "
        "cost/latency telemetry, and automated evaluation across "
        "multiple LLM providers."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

# ── Middleware (outermost = runs first, handles errors + request-ID) ──
app.add_middleware(RequestIDMiddleware)

# ── Routers ──
app.include_router(completions_router)


@app.get("/health", tags=["ops"])
async def health_check() -> JSONResponse:
    """
    Liveness probe. Returns 200 if the gateway process is up.

    Downstream service health (Redis, ClickHouse) will be added
    once those connections are wired.
    """
    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "service": "llmgov-gateway",
            "version": app.version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.gateway_host,
        port=settings.gateway_port,
        log_level=settings.log_level,
        reload=True,
    )
