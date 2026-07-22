# Incident & Technical Postmortem — LLMGov Development

> **Document Purpose:** High-credit technical postmortem documenting real engineering incidents, root causes, diagnostic investigations, and permanent mitigations established during LLMGov gateway development.

---

## Postmortem 1: Background Task Mock Pollution in Integration Test Suite

### Summary
During Phase 3 implementation, adding an out-of-band LLM-as-a-Judge background task (`evaluate_and_record_response`) caused 7 previously passing integration test suites to fail with `AssertionError: Expected 'acompletion' to have been called once. Called 2 times.`

### Impact
Blocked CI test pipeline execution; 7 test modules (`test_auth_rate_limit_wiring`, `test_cache_wiring`, `test_circuit_breaker_integration`, `test_pii_wiring`, `test_toxicity_wiring`, `test_telemetry_failure`) failed.

### Root Cause
1. In `app/api/completions.py`, `evaluate_and_record_response` was added to `BackgroundTasks` on every completion request.
2. In `app/core/eval.py`, `evaluate_and_record_response` invokes `run_llm_judge`, which makes an internal call to `litellm.acompletion`.
3. In unit tests for completion routes, test cases patched `litellm.acompletion` expecting a single call for the user's completion. The background execution triggered a second call to `litellm.acompletion`, doubling the call count.
4. Additionally, mock prompt completion responses returned strings like `"mock content"`, which caused `run_llm_judge` to log a `json.JSONDecodeError` when attempting to parse non-JSON responses as judge outputs.

### Resolution & Mitigation
- **Global Test Isolation Fixture**: Authored `mock_eval_globally` in `tests/conftest.py` which mocks `app.api.completions.evaluate_and_record_response` across all completion route integration tests while allowing `tests/test_eval.py` to test judge logic directly.
- **Result**: Restored 100% test pass rate across all 88 test cases.

---

## Postmortem 2: LiteLLM Vertex AI Model Prefix 500 Internal Server Error

### Summary
During live EC2 instance verification (Phase 1), curl requests sending `"model": "gemini-2.5-flash"` returned `500 Internal Server Error` from LiteLLM instead of calling Google AI Studio.

### Impact
Prevented live production verification on AWS EC2 instance (`13.207.27.191`).

### Root Cause
1. LiteLLM defaults bare `gemini-2.5-flash` model names to Google Cloud Vertex AI integration, which requires Vertex credentials and project settings.
2. The environment was configured with `GEMINI_API_KEY` for Google AI Studio (native API key authentication).

### Resolution & Mitigation
- **Explicit Provider Prefixing**: Enforced `"model": "gemini/gemini-2.5-flash"` prefix in curl request payloads and application default configurations.
- **Documentation Enforcement**: Updated `README.md` and cURL examples to explicitly document the `gemini/` prefix constraint.
- **Result**: Successfully routed live traffic to Google AI Studio returning `200 OK`.

---

## Postmortem 3: Python 3.13 Redis Mock Async Context Manager Protocol Exception

### Summary
Running `pytest` under Python 3.13 generated `TypeError: 'coroutine' object does not support the asynchronous context manager protocol` when `set_cached_completion` executed `async with redis_client.pipeline(transaction=True) as pipe:`.

### Impact
Generated unhandled exception warnings and potential pipeline failure in test environments.

### Root Cause
In `tests/test_cache_wiring.py`, `mock_redis` was created as a generic `AsyncMock()`. Under Python 3.13, calling `mock.pipeline(...)` on an `AsyncMock` returns a coroutine object rather than an object implementing `__aenter__` and `__aexit__`.

### Resolution & Mitigation
- **Explicit Async Context Manager Mocking**: Refactored `mock_redis` fixture in `test_cache_wiring.py` to use `MagicMock()` for client methods while configuring `pipe.__aenter__` and `pipe.__aexit__` explicitly as `AsyncMock()` return values.
- **Result**: Clean pipeline context manager execution without warnings or runtime errors.
