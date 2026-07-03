"""
LLMGov — Gateway Application Entry Point

FastAPI application with health check. Additional routes
(completions, registry, eval) are mounted in later chunks.
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.config.settings import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Startup / shutdown lifecycle hook."""
    # ── Startup ──
    # Connection pools (Redis, ClickHouse) will be initialized here
    # in later chunks. For now, just log readiness.
    print(f"LLMGov gateway starting on {settings.gateway_host}:{settings.gateway_port}")
    yield
    # ── Shutdown ──
    print("LLMGov gateway shutting down")


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
