# LLMGov v1.0-milestone-1 Release Notes

**Release Tag:** `v1.0-milestone-1`  
**Deployment Target:** AWS EC2 (`t3.large`, `ap-south-1`) — `http://13.207.27.191:8000`  

We are excited to announce the official **Milestone 1** release of **LLMGov**, an enterprise-grade AI Gateway offering centralized governance, observability, resilience, and multi-layered safety guardrails for Large Language Model applications.

---

## Key Highlights & Features

### 1. Unified OpenAI-Compatible Proxy & Router
- **OpenAI-Compatible `/v1/chat/completions` API**: Complete request/response payload compatibility allowing seamless drop-in integration with existing OpenAI SDKs and tools.
- **Provider Abstraction**: Decoupled integration with cloud LLMs (Google Gemini 2.5 Flash via LiteLLM) and local fallback engines (Ollama `qwen2.5:0.5b`).
- **Prompt Registry & System Prompts**: YAML-based versioned prompt template rendering.

### 2. Multi-Layered Security & Safety Guardrails
- **API Key Auth & Rate Limiting**: Key-based access control with Redis-backed fixed-window rate limiting.
- **PII Detection & Redaction**: Automatic regex sanitization of sensitive data (Emails, SSNs, Credit Cards) before prompts reach upstream LLM providers.
- **Toxicity & Policy Filter**: Safety classification preventing harmful content generation.
- **Adversarial Jailbreak Detector**: Pattern matching against known jailbreak techniques, DAN prompts, and base64 bypass payloads.

### 3. Resilience & Circuit Breaker Pattern
- **Automated Circuit Breaker**: Stateful failure tracking (`CLOSED`, `OPEN`, `HALF_OPEN`) with half-open single-probe lock protection against thundering herd problems.
- **Local Fallback Execution**: Automatic routing to local Ollama container when cloud providers fail or trip circuit breakers.

### 4. Enterprise Observability & Telemetry
- **ClickHouse Analytics Engine**: Low-overhead asynchronous telemetry writing tracking execution duration (`total_duration_ms`), token usage, estimated costs, and HTTP status codes.
- **Grafana Dashboard Suite**: Pre-built live visualization dashboards for real-time latency histograms, token usage, error rates, and model breakdown.

---

## Live Environment Access

- **API Base URL:** `http://13.207.27.191:8000`
- **Grafana Dashboard:** `http://13.207.27.191:3000` (User: `admin` / Pass: `admin`)
- **Health Check Endpoint:** `http://13.207.27.191:8000/health`

---

## Infrastructure & Deployment

- **Infrastructure as Code**: Terraform configuration (`infra/main.tf`) for automated AWS EC2 instance provisioning and security group management.
- **Container Orchestration**: Multi-container `docker-compose.yml` stack incorporating FastAPI, Redis, ClickHouse, Ollama, and Grafana.

---

## Known Limitations (Phase 1)

1. **HTTP Only**: TLS/HTTPS termination is deferred to Phase 2 (Domain/SSL configuration pending).
2. **Exact-Match Semantic Cache**: Caching uses SHA-256 message history hashing; vector cosine similarity threshold scanning is deferred per ADR-002.
