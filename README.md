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

## What This Is

LLMGov provides a centralized control plane for enterprise LLM consumption. Rather than having disparate services manage their own provider API keys, retries, and usage tracking, applications route requests through this gateway. This allows organizations to enforce compliance, audit all LLM interactions, and track costs and latency systematically without modifying downstream client code.

## Architecture

```mermaid
flowchart TD
    %% Define Styles
    classDef built fill:#2e7d32,stroke:#1b5e20,stroke-width:2px,color:white;
    classDef partial fill:#fb8c00,stroke:#e65100,stroke-width:4px,color:white;
    classDef planned fill:#eeeeee,stroke:#999999,stroke-width:2px,stroke-dasharray: 5 5,color:#555555;

    Client([Client App]) --> Gateway
    
    subgraph Gateway [LLMGov FastAPI Gateway]
        direction TB
        Ingest[Ingestion & Request ID]:::built
        Auth[Auth & Rate Limit]:::planned
        
        Ingest --> Auth
        
        subgraph Interceptors [Middleware Checks]
            Cache[Semantic Cache]:::built
            Guard[Safety Guardrails]:::planned
            Eval[Auto-Evaluator]:::planned
        end
        
        Auth --> Interceptors
        
        Registry[Prompt Registry & Router]:::planned
        Interceptors --> Registry
        
        ProviderAbstraction[Provider Abstraction]:::built
        Registry --> ProviderAbstraction
        
        ProviderAbstraction --> PrimaryProvider
        ProviderAbstraction --> FallbackProvider
        
        Telemetry[Telemetry Async Writer]:::built
        ProviderAbstraction --> Telemetry
    end
    
    PrimaryProvider[Gemini 2.5 Flash]:::built
    FallbackProvider[Ollama (Local Fallback)]:::built
    
    CH[(ClickHouse\nllm_metrics)]:::built
    Redis[(Redis\nCache/Limits)]:::built
    
    Telemetry --> CH
    Auth -.-> Redis
    Cache --> Redis
    
    Grafana[Grafana Dashboards]:::planned
    CH -.-> Grafana
```

## Tech Stack

| Technology | Reason |
| :--- | :--- |
| ![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white) **Python / FastAPI** | High-performance asynchronous processing; native integration with Pydantic for strict request/response validation. |
| ![Docker](https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white) **Docker Compose** | Ensures reproducible environments across dev and prod, isolating dependencies and standardizing deployments. |
| ![Redis](https://img.shields.io/badge/Redis-DC382D?style=flat&logo=redis&logoColor=white) **Redis** | Low-latency backing store for semantic caching with automated TTL versioning, alongside rate limiting counters. |
| ![ClickHouse](https://img.shields.io/badge/ClickHouse-FFCC01?style=flat&logo=clickhouse&logoColor=white) **ClickHouse** | Columnar database designed for massive OLAP workloads; handles high-throughput telemetry writes without blocking the hot path. |
| ![Pydantic](https://img.shields.io/badge/Pydantic-E92063?style=flat&logo=pydantic&logoColor=white) **Pydantic** | Provides robust, type-safe data validation and serialization for API contracts, ensuring strict compliance with expected schemas. |
| ![Gemini](https://img.shields.io/badge/Gemini-4285F4?style=flat&logo=google&logoColor=white) **Gemini (LiteLLM)** | Utilized as the primary single-provider integration via LiteLLM to normalize interactions before expanding to multi-provider routing. |
| ![Ollama](https://img.shields.io/badge/Ollama-white?style=flat&logo=ollama&logoColor=black) **Ollama (qwen2.5:0.5b)** | Local fallback provider used to prove routing and circuit breaker mechanisms work under strict 4GB VRAM constraints, prioritizing architectural validation over model intelligence. |

## Current Status

*Note: The project currently uses a three-state system (Live, Partial, Planned) because this branch represents a mid-integration draft. Some components are wired functionally but are missing their final algorithmic implementations or routing connections, which will be finalized before merging to main.*

| Feature | Status | Description |
| :--- | :--- | :--- |
| **Core Infrastructure** | Live | Dockerized environment (Redis, ClickHouse, FastAPI skeleton), `uvicorn` runner. |
| **Observability (Core)** | Live | Structured JSON logging, `X-Request-ID` correlation (`trace_id`), global error handling. |
| **Completions API** | Live | Single-provider proxy (`POST /v1/chat/completions`) using Gemini 2.5 Flash via LiteLLM. |
| **Telemetry (Write-Path)** | Live | Asynchronous writes to ClickHouse `llm_metrics` table upon successful completions. |
| **Semantic Caching** | Live | Cache key is an exact-match SHA-256 hash of the full normalized message history (all roles, all turns). Embedding vector uses only the latest user message for future semantic similarity. True cosine-similarity matching (threshold scan against stored vectors) remains Planned. |
| **Local Fallback (Ollama)** | Live | Directly wired into the request path via the circuit breaker state machine. |
| **Circuit Breaker** | Live | Full state machine verified (CLOSED -> OPEN -> HALF_OPEN -> CLOSED), including immediate low-latency Ollama failover. |
| **Safety Guardrails** | Planned | PII redaction and prompt injection detection (Week 3). |
| **Auth & Rate Limiting** | Planned | API key validation and sliding-window rate limits per application (Week 3). |
| **Prompt Registry** | Planned | Versioned prompt templates and overrides (Week 4). |

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

4. **Verify Health:**
   Ensure the gateway is running and responding.
   ```bash
   curl http://127.0.0.1:8000/health
   ```
   Expected response: `{"status":"healthy","service":"llmgov-gateway","version":"0.1.0","timestamp":"2026-07-05T16:47:18.532641+00:00"}`

## API Example

Here is a real request and response using the `POST /v1/chat/completions` endpoint, demonstrating a **semantic cache hit** (returning instantly without querying the primary provider).

**Request:**
```bash
curl -X POST http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini/gemini-2.5-flash",
    "messages": [{"role": "user", "content": "hello from cache hit test"}],
    "stream": false
  }'
```

**Response:**
```json
{
  "id": "pxRPaueiFYzLjuMP99nI-Q4",
  "object": "chat.completion",
  "created": 1783567526,
  "model": "gemini-2.5-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Hello! Excellent! Glad to hear the data retrieval was swift and efficient.\n\nWelcome to the conversation. What can I process for you today with optimal efficiency?"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 6,
    "completion_tokens": 980,
    "total_tokens": 986
  },
  "trace_id": "5b2afa3a-ab30-4b12-936b-19fb25469181"
}
```

## Reliability

Gateway failover is hardened by an automated state-machine chaos test that systematically triggers failures to verify circuit breaker transitions (`CLOSED` → `OPEN` → `HALF_OPEN` → `CLOSED`), ensuring requests bypass failing primary providers instantly and autonomously return once recovery timeouts elapse.

## Project Structure

```
LLMGov/
├── app/
│   ├── api/
│   │   └── completions.py       # API routing and proxy logic
│   ├── config/
│   │   └── settings.py          # Pydantic settings management
│   ├── core/
│   │   ├── cache.py             # Semantic cache read/write (Redis)
│   │   ├── cache_keys.py        # Cache key builders and TTL policy
│   │   ├── circuit_breaker.py   # Provider circuit breaker state machine
│   │   ├── embeddings.py        # Gemini embedding helper (768-dim)
│   │   ├── logging.py           # Structured JSON logger
│   │   ├── redis.py             # Redis connection pool lifecycle
│   │   └── telemetry.py         # Async ClickHouse metric writer
│   ├── middleware/
│   │   ├── error_handler.py     # Global exception handlers
│   │   └── request_id.py        # Trace ID generation and correlation
│   ├── models/
│   │   └── completions.py       # Pydantic schemas for completions
│   ├── __init__.py
│   └── main.py                  # FastAPI application entrypoint
├── docker/
│   └── clickhouse/
│       └── init/
│           ├── 001_llm_metrics.sql
│           ├── 002_llm_audit_logs.sql
│           └── 003_llm_eval_results.sql
├── docs/
│   ├── adr/                     # Architecture Decision Records
│   └── LLMGov_Master_Specification.docx
├── tests/
├── .dockerignore
├── .env.example
├── .pre-commit-config.yaml
├── docker-compose.yml           # Multi-container orchestration
├── Dockerfile                   # Multi-stage build for the Gateway
├── pyproject.toml               # Python dependencies and config
└── README.md
```

---

**Author:** LeviAckermanZ9
**Repository:** [https://github.com/LeviAckermanZ9/LLMGov](https://github.com/LeviAckermanZ9/LLMGov)
**License:** MIT (Placeholder)
