# ADR-006: Circuit Breaker & Local Model Fallback Strategy

## Status
Accepted

## Context
External cloud LLM providers (e.g. Google AI Studio) can experience upstream outages, rate limits, or network partitions. In production, request failures to primary cloud models must failover seamlessly to maintain service availability without cascading delays.

## Decision
We implement a custom sliding-window **Circuit Breaker** state machine (`CLOSED`, `OPEN`, `HALF_OPEN`) protecting the primary cloud model (`gemini/gemini-2.5-flash`). Upon reaching a threshold of consecutive failures (3 failures within 60s), the gateway automatically trips the breaker and routes traffic to a local containerized fallback model (`ollama/qwen2.5:0.5b`).

## Rationale
- **High Availability**: Fallback to local Ollama ensures 100% completion availability even during complete cloud provider outages.
- **Fast Failover**: When the breaker is `OPEN`, incoming requests bypass the primary cloud call entirely, avoiding connection timeouts.
- **Probe Recovery**: In `HALF_OPEN` state, a single probe request is allowed to check if the primary provider has recovered, automatically resetting to `CLOSED` upon success.
- **Cache Isolation**: Fallback responses are explicitly excluded from being written to the semantic cache, preventing degraded responses from persisting long after cloud recovery.

## Consequences
- **Quality Trade-off**: Local 0.5B models provide lower reasoning capability than cloud 2.5 Flash models during fallback periods.
- **Memory Footprint**: Running local Ollama containers requires at least ~1.5GB RAM allocated on the host system.
