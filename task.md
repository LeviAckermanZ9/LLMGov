# LLMGov — Known Gaps & Deferred Items

This file tracks pieces that are deliberately deferred, not forgotten.
Check here before assuming something isn't built yet.

---

## Deferred: True Semantic Similarity Matching (Spec §5.3)

**Status:** Not built. Logged as a gap since Week 2.

The current cache uses an **exact-match SHA-256 hash** of the full normalized
message history. What the spec actually calls for — a cosine-similarity scan
against stored embedding vectors with a ~0.96 threshold — is unbuilt.

Building it requires:
- Switching Redis to use RediSearch or a vector similarity module
- Implementing the cosine-similarity comparison scan across stored vectors
- Tuning the 0.96 similarity threshold against real traffic patterns
- An embedding-to-hash function that maps vectors to lookup keys

This changes the Redis schema and likely adds a dependency, both of which are
hard-stop items per AGENTS.md §6. See also ADR-002.

---

## Deferred: P99-Latency-Breach Circuit Breaker Trigger

**Status:** Not built. Deferred because it is a design piece, not a wiring task.

The circuit breaker currently trips only on explicit provider exceptions
(`Timeout`, `APIError`, `RateLimitError`, `ServiceUnavailableError`,
`NotFoundError`). A rolling-window p99 trigger that trips proactively when
latency degrades — before hard errors start — requires:

- In-process telemetry aggregation (a rolling window of recent latencies),
  not just the append-only ClickHouse writes that exist today
- A decision on window size, sample count, and threshold
- Careful interaction with HALF_OPEN probing (a slow probe shouldn't
  immediately re-trip the breaker on latency alone)

The breaker is fully functional without this — it just reacts to errors
rather than anticipating them.

---

## Open: HALF_OPEN Does Not Limit Concurrent Probes

**Status:** Scheduled for fix in the current review pass (Chunk 1).

When the breaker transitions to `HALF_OPEN`, `allow_request()` returns `True`
for every caller. Multiple simultaneous requests during recovery testing would
all be let through to the primary provider instead of limiting to a single
in-flight probe. The fix is to gate HALF_OPEN to one probe at a time;
additional concurrent requests route to the fallback until the probe resolves.

---

## Decision Record: Embedding Input Scope

**Status:** Implemented. Deliberate design choice, not an accident.

Semantic embeddings are generated only from the **latest user message** in the
conversation history, not the full context window. This ensures similarity
matching is based on the user's explicit current intent rather than being
diluted by system prompts or long chat histories.

The **exact-match cache key** still uses the full message history (all roles,
all turns) to guarantee structural correctness — identical final user messages
can yield different valid responses depending on prior conversation turns.

These two scopes are deliberately distinct and serve different purposes:
- The **embedding vector** answers: "Is this semantically similar to something
  we've seen before?" — scoped to the user's latest question.
- The **cache key hash** answers: "Is this structurally identical to a previous
  request?" — scoped to the entire conversation to prevent false positives
  from context-dependent prompts.
