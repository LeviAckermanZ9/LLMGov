# ADR-004: Out-of-Band Telemetry & Evaluation Write-Paths

## Status
Accepted

## Context
The LLMGov gateway processes completion requests where latency overhead introduced by governance layers must be minimized (Spec §5.6 calls for out-of-band execution). Writing detailed telemetry (`llm_metrics`), audit logs (`llm_audit_logs`), and evaluation results (`llm_eval_results`) to ClickHouse synchronously during request processing adds network I/O and DB round-trip latency to the response hot path.

## Decision
We mandate that all ClickHouse telemetry, audit log hash-chaining, and LLM-as-a-Judge evaluation writes execute **out-of-band** via FastAPI `BackgroundTasks` and Python `asyncio.to_thread`.

## Rationale
- **Zero Latency Penalty**: Completion responses return immediately to the client after the LLM stream/response terminates, without waiting for ClickHouse batch inserts or evaluation LLM calls.
- **Fault Tolerance**: Failures or network timeouts when interacting with ClickHouse or the evaluation LLM log warnings silently and never bubble up to cause 500 internal server errors for gateway clients.
- **Resource Offloading**: Database client `insert` calls run in a background thread pool, preventing sync driver I/O from blocking the FastAPI async event loop.

## Consequences
- **Eventual Consistency**: Telemetry and evaluation records appear in ClickHouse with a slight delay (typically 10–500ms).
- **Process Memory Lifetime**: If the FastAPI process crashes abruptly during task execution, queued background tasks in memory may be dropped.
