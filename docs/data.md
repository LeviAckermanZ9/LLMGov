# LLMGov — Data & Storage Architecture

## 1. Overview & Data Sources

LLMGov operates as an enterprise AI gateway processing incoming prompt payloads, dispatching requests to upstream LLM providers, and persisting execution state, telemetry, and audit logs.

### Primary Data Sources & Providers
- **Google Gemini API (`gemini/gemini-2.5-flash`)**: Primary cloud LLM provider accessed via LiteLLM provider abstraction.
- **Ollama Local Engine (`qwen2.5:0.5b`)**: Secondary local fallback model running inside a Docker container for resilience during cloud outages.
- **Redis Cache & Limits (v7.4)**: Transient in-memory state store for API key rate limiting counters, exact request hash caching, and embedding vector storage.
- **ClickHouse Analytics Engine (v24.8)**: Columnar OLAP database for high-throughput, low-latency telemetry logging and compliance auditing.

---

## 2. ClickHouse Database Schemas

ClickHouse serves as the analytical backend for LLMGov. Initialization scripts are located under `docker/clickhouse/init/`.

### Table Schemas & Purposes

1. **`default.llm_metrics`** (`001_llm_metrics.sql`)
   - **Purpose:** Telemetry table recording per-request performance, token consumption, latency (`total_duration_ms`), costs, and status codes for analytics and Grafana dashboards.
   - **Engine:** `MergeTree()` ordered by `(app_id, provider, model_used, timestamp)`.

2. **`default.llm_audit_logs`** (`002_llm_audit_logs.sql`)
   - **Purpose:** Audit trail recording sanitized prompts, raw responses, safety scores (PII, toxicity, jailbreak), and cryptographic hash-chaining columns for compliance auditing.
   - **Engine:** `MergeTree()` ordered by `(timestamp)`.

3. **`default.llm_eval_results`** (`003_llm_eval_results.sql`)
   - **Purpose:** Evaluation table storing automated LLM-as-a-judge scores, schema validation flags, and hand-labeled ground truth for quality monitoring.
   - **Engine:** `MergeTree()` ordered by `(timestamp)`.

---

## 3. Licensing & Compliance

- **Data Licensing:** N/A  
  *(LLMGov does not redistribute proprietary datasets. All telemetry and audit records generated are private operational logs produced dynamically by client requests).*
