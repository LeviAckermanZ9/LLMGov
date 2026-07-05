"""
LLMGov — Telemetry Write Path

Writes request metrics into ClickHouse `llm_metrics` after each
successful completion. Runs out-of-band (fire-and-forget in a
background thread) so it never sits in the response hot path.

W1-C4 scope: reduced schema (trace_id, timestamp, model_used,
provider, total_duration_ms, status_code). Full schema fields
(app_id, prompt_version, ttft_ms, tokens, cost) are added once
those concepts exist in the code.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from app.config.settings import settings

logger = logging.getLogger(__name__)

# ── Module-level client (lazy-initialized) ──
_ch_client: Optional[Client] = None


def _get_client() -> Client:
    """Return a ClickHouse client, creating one if needed."""
    global _ch_client
    if _ch_client is None:
        # Parse the URL from settings
        url = settings.clickhouse_url  # e.g. "http://localhost:8123"
        host = url.replace("http://", "").replace("https://", "").split(":")[0]
        port = int(url.split(":")[-1]) if ":" in url.split("//")[-1] else 8123

        _ch_client = clickhouse_connect.get_client(
            host=host,
            port=port,
            password=settings.clickhouse_password,
            database="default",
        )
    return _ch_client


async def write_metrics(
    *,
    trace_id: str,
    model_used: str,
    provider: str,
    total_duration_ms: float,
    status_code: int,
    # ── Full-schema fields (default to empty/zero until wired) ──
    app_id: str = "",
    prompt_version: str = "",
    model_requested: str = "",
    ttft_ms: float = 0.0,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    calculated_cost: float = 0.0,
) -> None:
    """
    Insert one row into default.llm_metrics.

    Runs the synchronous clickhouse-connect insert in a thread pool
    so it doesn't block the async event loop.
    """

    def _insert() -> None:
        try:
            client = _get_client()
            client.insert(
                table="llm_metrics",
                data=[[
                    uuid.UUID(trace_id),
                    datetime.now(timezone.utc),
                    app_id,
                    prompt_version,
                    model_requested,
                    model_used,
                    provider,
                    ttft_ms,
                    total_duration_ms,
                    prompt_tokens,
                    completion_tokens,
                    calculated_cost,
                    status_code,
                ]],
                column_names=[
                    "trace_id",
                    "timestamp",
                    "app_id",
                    "prompt_version",
                    "model_requested",
                    "model_used",
                    "provider",
                    "ttft_ms",
                    "total_duration_ms",
                    "prompt_tokens",
                    "completion_tokens",
                    "calculated_cost",
                    "status_code",
                ],
            )
            logger.info(
                "Telemetry row written to llm_metrics",
                extra={"model": model_used, "provider": provider},
            )
        except Exception:
            # Telemetry failures must never break the response path.
            # Log the error and move on.
            logger.error("Failed to write telemetry row", exc_info=True)

    # Fire-and-forget in a thread — never blocks the response
    await asyncio.to_thread(_insert)
