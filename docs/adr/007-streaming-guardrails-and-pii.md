# ADR-007: Pre-Call PII Redaction & Post-Call Toxicity Classification Guardrails

## Status
Accepted

## Context
Enterprise governance mandates protecting sensitive user data (PII) before transmission to external cloud providers, while also continuously screening model outputs for toxic content and jailbreak attempts.

## Decision
We enforce a dual-stage guardrail architecture:
1. **Pre-Call PII Redaction**: Incoming prompt text is screened using regex-based redaction patterns (Email, Phone Numbers, Credit Cards with Luhn validation, SSNs, IPv4 addresses) **before** messages are passed to LiteLLM or embedding models.
2. **Post-Call Toxicity & Jailbreak Screening**: Model response outputs are evaluated post-completion for toxicity using a keyword-based classifier, while prompt embeddings are cross-referenced via cosine similarity against known jailbreak vector references.

## Rationale
- **Privacy Assurance**: Sensitive user PII (SSNs, Credit Cards, Phones) is redacted at the gateway edge (`[REDACTED_...]`) so unencrypted PII never touches external cloud APIs.
- **Non-Blocking Safety Logging**: Toxicity scores and jailbreak metrics are calculated and logged into ClickHouse telemetry without blocking or dropping legitimate requests unless explicitly configured.
- **Embedding Reuse**: Vector embeddings generated during the semantic cache lookup are reused directly for jailbreak cosine similarity calculation, eliminating redundant model calls.

## Consequences
- **Regex Limitations**: Regex PII redaction may miss highly unconventional PII formats or produce rare false positives.
- **Token Overhead**: Redacted string replacement slightly alters prompt token length.
