# ADR-005: Cryptographic Hash-Chaining for Audit Logs via Redis Optimistic Locking

## Status
Accepted

## Context
Compliance requirements (Spec §5.6) require an immutable audit trail (`llm_audit_logs`) where each record is cryptographically linked to the preceding record via `sha256(prev_hash + serialized_row)`. Because multiple worker processes insert records concurrently, maintaining strict sequential hash linkage without global write locks is challenging.

## Decision
We implement cryptographic hash-chaining using **Redis Optimistic Concurrency Control (`WATCH`/`MULTI`/`EXEC`)** to maintain the global `prev_hash` sequence state (`llmgov:audit:latest_hash`) across distributed worker instances.

## Rationale
- **Deterministic Serialization**: Rows are serialized into sorted, unspaced JSON (`serialize_audit_row`) to guarantee identical SHA-256 digests across different hardware architecture implementations.
- **Lock-Free Concurrency**: Redis `WATCH` transactions allow worker processes to verify and swap `latest_hash` atomically. If a race condition occurs, workers retry up to 5 times.
- **Genesis Row Standard**: In the absence of preceding rows or during Redis cold-starts, `GENESIS_HASH` (`0` repeated 64 times) provides a deterministic root hash.
- **Fallback Integrity**: If Redis becomes completely unavailable, audit rows fall back safely to `GENESIS_HASH` with a logged warning, ensuring completion availability is never compromised.

## Consequences
- **Redis Dependency**: Sequential hash chain continuity depends on Redis availability.
- **Retry Overhead**: Under extreme parallel write concurrency, worker retries may increase background task execution time.
