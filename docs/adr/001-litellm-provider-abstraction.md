# ADR-001: LiteLLM for Provider Abstraction vs. Hand-rolled Adapter Layer

## Status
Accepted

## Context
LLMGov needs to route incoming requests from applications to various LLM providers (OpenAI, Anthropic, Gemini, local models) using a unified gateway interface. The challenge is standardizing the request/response schemas across these providers without building and maintaining a bespoke translation layer for each new provider API.

## Decision
We use **LiteLLM** for provider abstraction rather than building a hand-rolled adapter layer. 

## Rationale
This decision is grounded directly in the codebase:
- **Standardized Interfaces**: We currently use `litellm.acompletion` in `app/api/completions.py` and `litellm.aembedding` in `app/core/embeddings.py`. LiteLLM automatically maps our unified `ChatCompletionRequest` payloads to the underlying provider formats (e.g., Gemini) without requiring custom translation logic.
- **Zero-Cost Maintenance**: By deferring to LiteLLM, we offload the burden of tracking upstream API schema changes and mapping specific exceptions (e.g., `litellm.exceptions.Timeout`).
- **Unified Return Types**: The responses from `acompletion` conform to the standard OpenAI schema, simplifying our internal response mapping (`ChatCompletionResponse`).

## Consequences
- **Dependency coupling**: The gateway is tightly coupled to LiteLLM.
- **Feature parity**: We are constrained by what LiteLLM currently supports across providers.
