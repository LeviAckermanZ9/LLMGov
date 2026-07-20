# LLMGov

A production-grade LLM gateway that unifies routing, semantic caching, safety guardrails, cost/latency telemetry, and automated evaluation across multiple providers, with sub-second failover and a tamper-evident audit trail.

> **Note**: The above describes the target architecture. Current build status is outlined in the "Current Status" section below.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?style=flat&logo=docker&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-7.0+-DC382D?style=flat&logo=redis&logoColor=white)
![ClickHouse](https://img.shields.io/badge/ClickHouse-24.3+-FFCC01?style=flat&logo=clickhouse&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat&logo=pydantic&logoColor=white)
![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-4285F4?style=flat&logo=google&logoColor=white)
![Ollama](https://img.shields.io/badge/Ollama-Local-white?style=flat&logo=ollama&logoColor=black)

## Project Resources

*   **Known Gaps & Active Checklist**: See [task.md](task.md) in the repository root.
*   **Architecture Decision Records (ADRs)**: Detailed rationales and designs are documented under [docs/adr/](docs/adr/).

## What This Is

LLMGov provides a centralized control plane for enterprise LLM consumption. Rather than having disparate services manage their own provider API keys, retries, and usage tracking, applications route requests through this gateway. This allows organizations to enforce compliance, audit all LLM interactions, and track costs and latency systematically without modifying downstream client code.

## Architecture

```mermaid
flowchart TD
    %% Define Styles
    classDef built fill:#2e7d32,stroke:#1b5e20,stroke-width:2px,color:white;
    classDef partial fill:#fb8c00,stroke:#e65100,stroke-width:4px,color:white;
    classDef planned fill:#eeeeee,stroke:#999999,stroke-width:2px,stroke-dasharray: 5 5,color:#555555;

    Client(["Client App"]) --> Gateway
    
    subgraph Gateway ["LLMGov FastAPI Gateway"]
        direction TB
        Ingest["Ingestion & Request ID"]:::built
        Auth["Auth & Rate Limit"]:::built
        
        Ingest --> Auth
        
        subgraph Interceptors ["Middleware Checks"]
            Cache["Semantic Cache"]:::built
            Guard["Safety Guardrails"]:::built
            Eval["Auto-Evaluator"]:::planned
        end
        
        Auth --> Interceptors
        
        Registry["Prompt Registry & Router"]:::built
        Interceptors --> Registry
        
        ProviderAbstraction["Provider Abstraction"]:::built
        Registry --> ProviderAbstraction
        
        CircuitBreaker["Circuit Breaker"]:::built
        ProviderAbstraction --> CircuitBreaker
        
        Telemetry["Telemetry Async Writer"]:::built
        ProviderAbstraction --> Telemetry
    end
    
    PrimaryProvider["Gemini 2.5 Flash"]:::built
    FallbackProvider["Ollama (Local Fallback)"]:::built
    
    CH[("ClickHouse\nllm_metrics")]:::built
    Redis[("Redis\nCache/Limits")]:::built
    
    CircuitBreaker --> PrimaryProvider
    CircuitBreaker --> FallbackProvider
    Telemetry --> CH
    Auth -.-> Redis
    Cache --> Redis
    
    Grafana["Grafana Dashboards"]:::built
    CH -.-> Grafana
```

## Tech Stack

| Technology | Reason |
| :--- | :--- |
| ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) **Python / FastAPI** | High-performance asynchronous processing; native integration with Pydantic for strict request/response validation. |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) **Docker Compose** | Ensures reproducible environments across dev and prod, isolating dependencies and standardizing deployments. |
| ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) **Redis** | Low-latency backing store for semantic caching with automated TTL versioning, powered by a live connection pool initialized at application startup, API key authentication, and rate limiting counters. |
| ![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC01?style=flat&logo=clickhouse&logoColor=white) **ClickHouse** | Columnar database designed for massive OLAP workloads; handles high-throughput telemetry writes without blocking the hot path. |
| ![Grafana](https://img.shields.io/badge/Grafana-F46800?style=flat&logo=grafana&logoColor=white) **Grafana** | Auto-provisioned dashboards on port 3000 connected to ClickHouse for team spend attribution and p50/p95/p99 provider latency analysis. |
| ![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=flat&logo=pydantic&logoColor=white) **Pydantic** | Provides robust, type-safe data validation and serialization for API contracts, ensuring strict compliance with expected schemas. |
| ![Gemini](https://img.shields.io/badge/Gemini-4285F4?style=flat&logo=google&logoColor=white) **Gemini (LiteLLM)** | Utilized via LiteLLM for both completions (Gemini 2.5 Flash) and embeddings (Gemini embedding-001) as part of the primary provider integration, validating multi-modal capabilities and embedding scope policies. |
| ![Ollama](https://img.shields.io/badge/Ollama-white?style=flat&logo=ollama&logoColor=black) **Ollama (qwen2.5:0.5b)** | Local fallback provider used to prove routing and circuit breaker mechanisms work under strict 4GB VRAM constraints, prioritizing architectural validation over model intelligence. |

## Current Status

*Note: The project status tracks which core gateway pillars are fully Live versus Planned for upcoming milestones.*

| Feature | Status | Description |
| :--- | :--- | :--- |
| **Core Infrastructure** | Live | Dockerized environment (Redis, ClickHouse, FastAPI skeleton), `uvicorn` runner. |
| **Observability (Core)** | Live | Structured JSON logging, `X-Request-ID` correlation (`trace_id`), global error handling. |
| **Completions API** | Live | Single-provider proxy (`POST /v1/chat/completions`) using Gemini 2.5 Flash via LiteLLM. |
| **Telemetry (Write-Path)** | Live | Asynchronous writes to ClickHouse `llm_metrics` table upon successful completions. |
| **Semantic Caching** | Live | Exact-match caching is Live: cache key uses a SHA-256 hash of the full normalized message history (all roles, all turns) to guarantee context safety, and embedding generation uses only the latest user message. True cosine-similarity threshold scan against stored vectors remains Planned. |
| **Local Fallback (Ollama)** | Live | Directly wired into the request path via the circuit breaker state machine. |
| **Circuit Breaker** | Live | Full state machine verified (CLOSED -> OPEN -> HALF_OPEN -> CLOSED), including immediate low-latency Ollama fallback and a robust HALF_OPEN concurrent-probe limit (ensuring only a single probe is in-flight via a non-blocking asyncio race condition check). |
| **Safety Guardrails** | Live | PII redaction (email, phone, Luhn credit card, SSN, IPv4), output toxicity classification (weighted lexicon with meta-discussion filters), and input jailbreak detection (cosine similarity against reference embeddings) are Live on cache-miss paths. |
| **Auth & Rate Limiting** | Live | Fail-closed API key verification (returns 401 on invalid/missing key, 503 on service unavailability) and sliding-window rate limits per application (returns 429 when limits are exceeded, fails open and degrades gracefully on Redis failure), with real `app_id` routed to telemetry. |
| **Prompt Registry** | Live | Versioned YAML prompt templates (`prompts.yaml`) with weighted A/B traffic selection and template variable substitution. |
| **Grafana Dashboards** | Live | Auto-provisioned Grafana instance on port 3000 reading ClickHouse `llm_metrics` with team spend and provider latency p50/p95/p99 panels. |

## Quickstart

1. **Clone the repository:**
   ```bash
   git clone https://github.com/LeviAckermanZ9/LLMGov.git
   cd LLMGov
   ```

2. **Configure Environment Variables:**
   Copy the example environment file and configure the required keys.
   ```bash
   cp .env.example .env
   ```
   Edit `.env` and set:
   *   `GEMINI_API_KEY`: Your Google Gemini API key.
   *   `CLICKHOUSE_PASSWORD`: The password for the ClickHouse `default` user (e.g., `llmgov_dev`).

3. **Start the Stack:**
   Bring up the infrastructure and the gateway using Docker Compose.
   ```bash
   docker compose up -d
   ```

4. **Seed a Test API Key:**
   Because API Key Authentication is now active and fail-closed, you must seed a valid API key in Redis to authenticate requests. You can seed a test key (`llmgov_sk_dev_app`) that maps to the application identifier `dev_app` by running:
   ```bash
   docker compose exec redis redis-cli hset llmgov:auth:5329527556114a7930fefa95d192ba0bdf4097fae6191ae468fae0c8b9c73de8 app_id "dev_app"
   ```

5. **Verify Health:**
   Ensure the gateway is running and responding.
   ```bash
   curl http://127.0.0.1:8000/health
   ```
   Expected response: `{"status":"healthy","service":"llmgov-gateway","version":"0.1.0","timestamp":"2026-07-05T16:47:18.532641+00:00"}`

## API Example

Here is a real request and response using the `POST /v1/chat/completions` endpoint, demonstrating a successful proxy through the gateway. Note that a valid API key must be supplied in the `Authorization` header.

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer llmgov_sk_dev_app" \
  -d '{
    "model": "gemini/gemini-2.5-flash",
    "messages": [{"role": "user", "content": "Why is the sky blue? Answer in one short sentence."}],
    "stream": false
  }'
```

**Response:**
```json
{
  "id": "69FUao_dK77djuMP6Ky2qAM",
  "object": "chat.completion",
  "created": 1783943658,
  "model": "gemini-2.5-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "The atmosphere scatters blue sunlight more than other colors."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 13,
    "completion_tokens": 798,
    "total_tokens": 811
  },
  "trace_id": "0ba5829a-aaa7-4f2e-812d-405a81d04aa8"
}

### PII Redaction Example

When a request contains personally identifiable information (PII), the gateway automatically redacts the sensitive values prior to calling the LLM and the embedding generator.

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer llmgov_sk_dev_app" \
  -d '{
    "model": "gemini/gemini-2.5-flash",
    "messages": [{"role": "user", "content": "My email is secret-pii-miss-99@example.com. Repeat that email exactly."}],
    "stream": false
  }'
```

**Response:**
```json
{
  "id": "5bpbavK-OevSjuMP-I-saQ",
  "object": "chat.completion",
  "created": 1784396516,
  "model": "gemini-2.5-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "[EMAIL]"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 12,
    "completion_tokens": 32,
    "total_tokens": 44
  },
  "trace_id": "b5bd2bae-5bd6-4973-a1c3-f3d233a2cf64"
}
```

**Console Log Output:**
```json
{"timestamp": "2026-07-18T17:41:58.272606+00:00", "level": "INFO", "logger": "app.api.completions", "message": "Completion returned", "trace_id": "b5bd2bae-5bd6-4973-a1c3-f3d233a2cf64", "model": "gemini-2.5-flash", "provider": "gemini", "latency_ms": 1337.9, "status_code": 200, "has_pii_redacted": true, "toxicity_score": 0.0, "is_toxic": false, "jailbreak_score": 0.124, "is_jailbreak": false}
```


## Reliability

Gateway failover is hardened by an automated state-machine chaos test that systematically triggers failures to verify circuit breaker transitions (`CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`), ensuring requests bypass failing primary providers instantly and autonomously return once recovery timeouts elapse. Additionally, a concurrency-safe integration test validates the `HALF_OPEN` state using a real `asyncio.Event`-gated interleaving mechanism, proving that multiple parallel requests are safely throttled to a single primary probe while concurrent traffic gets seamlessly routed to Ollama.

Furthermore, the sliding-window rate limiter employs a fail-open design: if Redis encounters a connection or query error while verifying the rate limit, the error is logged loudly and the request is permitted to proceed, avoiding hard-stops on network degradation.

To enforce compliance and data privacy, safety guardrails operate on every request: PII redaction runs automatically before reaching external APIs (preventing leaks to third-party providers), non-blocking output toxicity classification evaluates generated responses against a weighted lexicon, and input jailbreak detection performs cosine-similarity matching against known attack vector embeddings.

## Project Structure

```
LLMGov/
├── app/
│   ├── api/
│   │   └── completions.py       # API routing, proxy, and guardrails wiring
│   ├── config/
│   │   └── settings.py          # Pydantic settings management
│   ├── core/
│   │   ├── auth.py              # Fail-closed API key verification
│   │   ├── cache.py             # Semantic cache read/write (Redis)
│   │   ├── cache_keys.py        # Cache key builders and TTL policy
│   │   ├── circuit_breaker.py   # Provider circuit breaker state machine
│   │   ├── embeddings.py        # Gemini embedding helper (768-dim)
│   │   ├── jailbreak.py         # Cosine-similarity jailbreak detection
│   │   ├── logging.py           # Structured JSON logger
│   │   ├── pii.py               # Regex-based PII redaction module (Luhn validated)
│   │   ├── prompt_registry.py   # Versioned A/B prompt routing registry
│   │   ├── rate_limiter.py      # Fail-open Redis rate limiter
│   │   ├── redis.py             # Redis connection pool lifecycle
│   │   ├── telemetry.py         # Async ClickHouse metric writer
│   │   └── toxicity.py          # Lexicon-based output toxicity classifier
│   ├── middleware/
│   │   ├── error_handler.py     # Global exception handlers
│   │   └── request_id.py        # Trace ID generation and correlation
│   ├── models/
│   │   └── completions.py       # Pydantic schemas for completions
│   ├── __init__.py
│   └── main.py                  # FastAPI application entrypoint
├── docker/
│   ├── clickhouse/
│   │   └── init/
│   │       ├── 001_llm_metrics.sql
│   │       ├── 002_llm_audit_logs.sql
│   │       └── 003_llm_eval_results.sql
│   └── grafana/
│       ├── dashboards/          # Auto-provisioned Grafana JSON dashboard
│       └── provisioning/        # Datasource and dashboard provider configs
├── docs/
│   ├── adr/                     # Architecture Decision Records
│   └── LLMGov_Master_Specification.docx
├── tests/                       # 75+ automated unit and integration tests
├── .dockerignore
├── .env.example
├── .pre-commit-config.yaml
├── docker-compose.yml           # Multi-container orchestration (Redis, ClickHouse, Ollama, Grafana)
├── Dockerfile                   # Multi-stage build for the Gateway
├── prompts.yaml                 # Prompt registry configuration with version weights
├── pyproject.toml               # Python dependencies and config
└── README.md
```

---

**Author:** LeviAckermanZ9
**Repository:** [https://github.com/LeviAckermanZ9/LLMGov](https://github.com/LeviAckermanZ9/LLMGov)
**License:** MIT (Placeholder)
