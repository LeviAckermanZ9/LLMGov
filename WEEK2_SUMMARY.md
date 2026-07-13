# Week 2 Integration Draft: Circuit Breaker & Sabotage Fallover

This branch (`week2-integration-draft`) wires the isolated components built earlier into the live request path, specifically closing out the Week 2 milestone requirements around resilient multi-provider routing and semantic caching basics.

## Summary of Completed Chunks

- **Chunk 1 (Ollama Fallback):** Added `ollama` (`qwen2.5:0.5b`) to the `docker-compose.yml` to satisfy the strict 4GB VRAM constraint for local fallbacks. Verified container stability and native inference.
- **Chunk 2 (Caching Stub):** Wired the Redis connection pool to the FastAPI lifespan hook. Implemented a temporary `hash_embedding` string-hashing stub to perform exact-match caching. Decided explicitly to embed *only the latest user message* instead of the full conversation history to prepare for future semantic matching, while cache keys still hash the full array to guarantee structural accuracy.
- **Chunk 3 (Exception Hardening):** Addressed concurrency bugs when generating embeddings using `asyncio.create_task()`. Handled `CancelledError` gracefully and ensured task failures don't crash the host request. Type-narrowed `isinstance` checks correctly, and centralized `response.usage` extraction.
- **Chunk 4 (Circuit Breaker & Routing):** Integrated the singleton `primary_breaker` into `app/api/completions.py`. Fallback caching is explicitly **skipped** to avoid polluting the cache with degraded answers. The `ProviderAbstraction` layer cleanly routes to Ollama when `allow_request()` is false, decoupling `model_requested` from `model_used` in the ClickHouse telemetry stream.
- **Chunk 5 (Chaos Testing & State Verification):** Wrote `chaos_test2.py` and executed a full end-to-end chaos test. Verified the circuit breaker state machine perfectly transitions:
  - 5 `gemini-invalid` errors tripped `CLOSED` → `OPEN`.
  - Immediate subsequent requests safely bypassed Gemini entirely with zero timeout latency (proven by branch isolation).
  - After 30s `recovery_timeout`, requests transitioned `OPEN` → `HALF_OPEN` → `CLOSED` with successful execution.

## The Remaining Gaps (`task.md`)

The following logic remains deliberately deferred:

- **True Semantic Comparison:** We still use a string-hash exact match for the semantic cache; the cosine-similarity scan against stored vectors is unbuilt.
- **P99 Latency Tripping:** The circuit breaker only trips on explicit `APIError`/`Timeout`/`NotFoundError`. It does not yet ingest live telemetry streams to trip reactively on p99 degradation.
- **Concurrency in HALF_OPEN:** The `HALF_OPEN` state currently acts as an unthrottled gateway for all incoming traffic rather than limiting concurrent probes to exactly one in-flight request.

The system is now stable, handles network sabotages autonomously, logs all deviations cleanly, and represents a hardened baseline for Opus's final review.
