# ADR-003: Redis Startup Behavior — Fail-Hard, Protected by Compose Healthcheck

## Status
Accepted

## Context
The gateway requires Redis for semantic caching (cache reads/writes) and will
later use it for rate-limiting counters. The question: what should happen if
Redis is unreachable when the gateway starts?

Three options were considered:

1. **Fail-fast (refuse to start)** — The gateway pings Redis during startup
   and crashes if the ping fails. Simple, but brittle if Redis takes a few
   extra seconds to initialize.
2. **Retry then fail-hard** — Same as fail-fast, but with a bounded retry
   window (e.g. 3 attempts, 2s apart) before giving up.
3. **Degrade gracefully** — Start anyway, treat cache as permanently missed
   until Redis comes back. Conceptually clean, but adds complexity (lazy
   reconnection, health-status tracking) for a scenario that can't currently
   happen in the only deployment pattern that exists.

## Decision
**Option 1: Fail-fast, single ping, protected by Docker Compose healthcheck.**

The gateway's `redis_lifespan` hook creates the Redis connection pool, issues
one `ping()`, and lets the exception propagate if it fails — the app does not
start. No retry loop is added.

This is safe because the only deployment pattern that exists today is
`docker compose up`, where the gateway service declares
`depends_on: redis: condition: service_healthy`. Docker guarantees Redis is
healthy before the gateway container starts. The ping is a belt-and-suspenders
check, not the primary reliability mechanism.

### Why not retry?
Retries add code for a scenario the Compose healthcheck already prevents.
If Redis passes its own healthcheck but fails the gateway's ping, the problem
is likely a misconfiguration (wrong URL, wrong port), not a timing issue — and
retries won't fix misconfiguration.

### Why not degrade gracefully?
Runtime degradation (Redis goes down after startup) is already handled:
`get_cached_completion` and `set_cached_completion` in `cache.py` both wrap
Redis calls in `try/except Exception`, log the error, and return
None / silently drop the write. The request path never crashes on a Redis
failure.

Startup degradation (start without Redis at all) would require lazy
reconnection logic and health-status tracking. Since the Compose healthcheck
dependency makes this scenario unreachable today, implementing it would be
speculative engineering. Deferred, not forgotten — tracked in `task.md` for
when a deployment pattern emerges where the gateway starts without Redis
being pre-verified.

## Consequences
- The gateway will not start if Redis is unreachable, giving a clear,
  immediate failure signal rather than silent degradation.
- Deployment patterns without Docker Compose (e.g. bare-metal, Kubernetes)
  will need their own equivalent of the healthcheck dependency, or this ADR
  should be revisited to add retry/degrade logic.
- Runtime Redis failures are already gracefully handled and do not affect
  the request path.
