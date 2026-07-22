# ADR-008: LLM-as-a-Judge Evaluation Architecture for Correctness

## Status
Accepted

## Context
Automated evaluation across LLM completions requires scoring multiple dimensions (PII, Toxicity, Latency, Format Adherence, Correctness). Three of these dimensions are already captured mechanically by guardrails and telemetry. The remaining requirement is evaluating semantic correctness and helpfulness.

## Decision
We decouple evaluation responsibilities:
1. **Mechanical Schema Validator**: `validate_schema` mechanically verifies JSON syntax and Pydantic/JSON-schema compliance (`schema_valid`).
2. **Targeted LLM-as-a-Judge Grader**: `run_llm_judge` uses a dedicated judge prompt focused exclusively on **Correctness and Helpfulness** (1–5 scalar score + rationale).

## Rationale
- **Single-Axis Isolation**: Isolating the judge to correctness avoids double-penalizing model responses for toxicity or PII redaction (which are handled by dedicated guardrail layers).
- **Protected Refusals**: The judge prompt explicitly instructs the LLM not to penalize valid refusal responses triggered by safety guardrails.
- **Hand-Labeled Ground-Truth Calibration**: The judge rubric is calibrated against a dataset of 20 hand-labeled prompt/response pairs covering fact retrieval, math hallucinations, formatting failures, and safety refusals.
- **ClickHouse Integration**: Evaluation outcomes are persisted out-of-band to `default.llm_eval_results` (`trace_id`, `timestamp`, `schema_valid`, `judge_score`, `judge_rationale`, `hand_labeled`).

## Consequences
- **Judge LLM Cost**: Each evaluated completion triggers an out-of-band LLM call to the judge model.
- **API Fallback Handling**: If the judge LLM call fails, the evaluation harness logs a fallback score without interrupting response delivery.
