# ADR-002: Semantic Cache Similarity Threshold and TTL/Versioning Policy

## Status
Partially Implemented

## Context
Spec Section 5.3 mandates a semantic cache to prevent redundant LLM provider calls. We must define how vectors and completion payloads are stored, invalidated, and matched based on similarity.

## Decision

### Implemented Policies
1. **Cache Key Namespacing**: We store the cache keys mapped strictly by `prompt_version` and `model`. As implemented in `app/core/cache_keys.py`:
   - `llmgov:cache:vector:{prompt_version}:{model}:{embedding_hash}`
   - `llmgov:cache:payload:{prompt_version}:{model}:{embedding_hash}`
2. **TTL Default**: We enforce a default Time-To-Live (TTL) of 24 hours (`86400` seconds) for cached responses.

### Specified but Not Yet Built (See `task.md`)
The following components are specified in 5.3 but are currently logged as gaps in `task.md` pending future implementation:
1. **Cosine-Similarity Scan/Comparison Logic**: The actual mathematical comparison against stored vectors is not yet coded.
2. **0.96 Similarity Threshold**: When the comparison logic is built, it will use a strict cosine-similarity threshold of ~0.96 to classify a semantic cache hit.
3. **Embedding-to-Hash Function**: The function to generate the `embedding_hash` from the embedding vector is pending.

## Rationale
Keying the cache rigidly by `prompt_version` and `model` naturally resolves the staleness problem. Rather than running a manual sweep to invalidate old cached records when a prompt is updated, a prompt version bump or model switch natively creates an isolated namespace. The old cache slices are automatically orphaned and eventually cleared by the 24-hour TTL, ensuring responses don't silently go stale even without manual intervention.
