# Architecture Decision Records (ADR) Thinking Artifact — LLMGov

> **Option B Alignment (Master Specification):**
> This artifact compiles and synthesizes the complete Architectural Decision Record (ADR) set governing the LLMGov AI Governance Gateway. It documents key architectural trade-offs, technical decisions, rationale, and operational consequences established during design and production deployment.

---

## Index of Architectural Decision Records

1. [ADR-001: LiteLLM for Provider Abstraction vs. Hand-rolled Adapter Layer](file:///d:/Personal/LLMGov/docs/adr/001-litellm-provider-abstraction.md)
2. [ADR-002: Semantic Cache Policy & TTL Architecture](file:///d:/Personal/LLMGov/docs/adr/002-semantic-cache-policy.md)
3. [ADR-003: Redis Startup & Lifecycle Behavior](file:///d:/Personal/LLMGov/docs/adr/003-redis-startup-behavior.md)
4. [ADR-004: Out-of-Band Telemetry & Evaluation Write-Paths](file:///d:/Personal/LLMGov/docs/adr/004-out-of-band-telemetry-and-eval.md)
5. [ADR-005: Cryptographic Hash-Chaining for Audit Logs via Redis Optimistic Locking](file:///d:/Personal/LLMGov/docs/adr/005-audit-log-hash-chain.md)
6. [ADR-006: Circuit Breaker & Local Model Fallback Strategy](file:///d:/Personal/LLMGov/docs/adr/006-circuit-breaker-fallback.md)
7. [ADR-007: Pre-Call PII Redaction & Post-Call Toxicity Classification Guardrails](file:///d:/Personal/LLMGov/docs/adr/007-streaming-guardrails-and-pii.md)
8. [ADR-008: LLM-as-a-Judge Evaluation Architecture for Correctness](file:///d:/Personal/LLMGov/docs/adr/008-llm-as-a-judge-correctness-eval.md)

---

## Architectural Synthesis

### 1. Governance & Hot-Path Performance
A fundamental constraint of LLMGov is ensuring enterprise governance (PII protection, toxicity classification, audit logging, telemetry, evaluation) does not degrade response latency. 

By enforcing out-of-band execution via FastAPI `BackgroundTasks` (ADR-004, ADR-005, ADR-008), network I/O for ClickHouse telemetry (`llm_metrics`, `llm_audit_logs`, `llm_eval_results`) and asynchronous LLM evaluation calls run completely outside the critical HTTP response path.

### 2. Failure Domain Isolation & Resilience
The system isolates failure domains across infrastructure layers:
- **Cloud Outages**: The sliding-window Circuit Breaker (ADR-006) automatically redirects traffic to a local `ollama/qwen2.5:0.5b` container during upstream cloud failures.
- **Cache Failures**: Cache lookups fail open cleanly (ADR-002), logging warnings without dropping requests. Degraded fallback model outputs are excluded from cache writes.
- **Distributed Concurrency**: Audit log hash-chaining uses Redis optimistic concurrency (`WATCH`/`MULTI`/`EXEC`) to maintain sequential SHA-256 hash chains across distributed worker processes without heavyweight locks (ADR-005).

### 3. Safety & Evaluation Decoupling
Safety guardrails (ADR-007) and quality evaluation (ADR-008) are cleanly separated:
- Pre-call PII redaction cleans sensitive data before external cloud API transmission.
- Post-call toxicity and vector-based jailbreak screening detect malicious input/output patterns.
- Mechanical schema validation isolates syntax compliance (`schema_valid`), while a targeted LLM-as-a-Judge prompt scores correctness on a 1-5 scale against hand-labeled ground-truth baselines.
