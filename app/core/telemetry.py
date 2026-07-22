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
import hashlib
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import clickhouse_connect
import redis.asyncio as redis
from clickhouse_connect.driver.client import Client

from app.config.settings import settings
from app.core.redis import get_redis

logger = logging.getLogger(__name__)

# ── Module-level client (lazy-initialized) ──
_ch_client: Optional[Client] = None

GENESIS_HASH = "0000000000000000000000000000000000000000000000000000000000000000"


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


def serialize_audit_row(
    *,
    trace_id: str,
    timestamp: datetime,
    sanitized_prompt: str,
    raw_response: str,
    has_pii_redacted: bool | int,
    toxicity_score: float,
    jailbreak_score: float,
) -> str:
    """
    Deterministically serializes an audit log row into alphabetized JSON with no spaces.
    """
    payload_dict = {
        "has_pii_redacted": int(has_pii_redacted),
        "jailbreak_score": jailbreak_score,
        "raw_response": raw_response,
        "sanitized_prompt": sanitized_prompt,
        "timestamp": timestamp.isoformat(),
        "toxicity_score": toxicity_score,
        "trace_id": trace_id,
    }
    return json.dumps(payload_dict, sort_keys=True, separators=(",", ":"))


def compute_row_hash(prev_hash: str, serialized_row: str) -> str:
    """
    Computes sha256(prev_hash + serialized_row).
    """
    return hashlib.sha256(f"{prev_hash}{serialized_row}".encode("utf-8")).hexdigest()


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


async def record_audit_log(
    *,
    trace_id: str,
    sanitized_prompt: str,
    raw_response: str,
    has_pii_redacted: bool | int,
    toxicity_score: float,
    jailbreak_score: float,
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Computes cryptographic hash-chain and writes audit record to ClickHouse `llm_audit_logs`.
    Out-of-band execution using Redis Optimistic Locking for prev_hash updates.
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    serialized_row = serialize_audit_row(
        trace_id=trace_id,
        timestamp=timestamp,
        sanitized_prompt=sanitized_prompt,
        raw_response=raw_response,
        has_pii_redacted=has_pii_redacted,
        toxicity_score=toxicity_score,
        jailbreak_score=jailbreak_score,
    )

    prev_hash = GENESIS_HASH
    row_hash = compute_row_hash(prev_hash, serialized_row)

    # Attempt Redis optimistic locking for sequence ordering across workers
    try:
        redis_client = get_redis()
        max_retries = 5
        for _ in range(max_retries):
            try:
                async with redis_client.pipeline(transaction=True) as pipe:
                    await pipe.watch("llmgov:audit:latest_hash")
                    current_prev = await pipe.get("llmgov:audit:latest_hash")
                    if not current_prev:
                        current_prev = GENESIS_HASH

                    computed_row_hash = compute_row_hash(current_prev, serialized_row)
                    pipe.multi()
                    pipe.set("llmgov:audit:latest_hash", computed_row_hash)
                    await pipe.execute()

                    prev_hash = current_prev
                    row_hash = computed_row_hash
                    break
            except redis.WatchError:
                continue
    except Exception as e:
        logger.warning(
            f"Redis uninitialized or unavailable for audit log hash chain; falling back to genesis hash: {e}"
        )

    def _insert() -> None:
        try:
            client = _get_client()
            client.insert(
                table="llm_audit_logs",
                data=[[
                    uuid.UUID(trace_id),
                    timestamp,
                    sanitized_prompt,
                    raw_response,
                    int(has_pii_redacted),
                    toxicity_score,
                    jailbreak_score,
                    prev_hash,
                    row_hash,
                ]],
                column_names=[
                    "trace_id",
                    "timestamp",
                    "sanitized_prompt",
                    "raw_response",
                    "has_pii_redacted",
                    "toxicity_score",
                    "jailbreak_score",
                    "prev_hash",
                    "row_hash",
                ],
            )
            logger.info(
                "Audit log row written to llm_audit_logs",
                extra={"trace_id": trace_id, "row_hash": row_hash},
            )
        except Exception:
            logger.error("Failed to write audit log row", exc_info=True)

    await asyncio.to_thread(_insert)

