import pytest
import asyncio
import time
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.circuit_breaker import CircuitBreakerState
import app.api.completions as completions_module
from litellm.exceptions import ServiceUnavailableError

@pytest.fixture(autouse=True)
def reset_breaker():
    # Reset the global breaker before each test
    completions_module.primary_breaker.state = CircuitBreakerState.CLOSED
    completions_module.primary_breaker.failure_count = 0
    completions_module.primary_breaker._half_open_probe_in_flight = False
    yield

@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    mock.get.return_value = None
    with patch("app.core.cache.get_redis", return_value=mock):
        yield mock

@pytest.fixture
def mock_embedding():
    with patch("app.api.completions.generate_embedding", return_value=[0.1, 0.2, 0.3]) as p:
        yield p

@pytest.fixture(autouse=True)
def mock_telemetry():
    with patch("app.api.completions.write_metrics") as p:
        yield p

def test_circuit_breaker_fallback_on_failure(mock_redis, mock_embedding, auth_headers):
    # Mock litellm to fail on the first call (primary) and succeed on the second (fallback)
    mock_response = MagicMock()
    mock_response.id = "fallback-id"
    mock_response.created = 1234567890
    mock_response.model = "qwen2.5:0.5b"
    mock_choice = MagicMock()
    mock_choice.index = 0
    mock_choice.message.role = "assistant"
    mock_choice.message.content = "fallback content"
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_response.usage.total_tokens = 30

    def mock_acompletion(*args, **kwargs):
        if kwargs.get("model") == "gemini/gemini-2.5-flash":
            raise ServiceUnavailableError("Gemini is down", llm_provider="gemini", model="gemini-2.5-flash")
        elif kwargs.get("model") == "ollama/qwen2.5:0.5b":
            return mock_response
        else:
            raise ValueError(f"Unexpected model: {kwargs.get('model')}")

    import uuid
    unique_content = f"hello {uuid.uuid4()}"
    with patch("app.api.completions.litellm.acompletion", new_callable=AsyncMock, side_effect=mock_acompletion) as mock_llm:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                headers=auth_headers,
                json={
                    "model": "gemini/gemini-2.5-flash",
                    "messages": [{"role": "user", "content": unique_content}],
                    "stream": False
                }
            )
            
            assert response.status_code == 200
            assert response.json()["choices"][0]["message"]["content"] == "fallback content"
            assert completions_module.primary_breaker.failure_count == 1
            
            # Verify that acompletion was called twice: once for primary, once for fallback
            assert mock_llm.call_count == 2
            calls = mock_llm.call_args_list
            assert calls[0].kwargs["model"] == "gemini/gemini-2.5-flash"
            assert calls[1].kwargs["model"] == "ollama/qwen2.5:0.5b"
            assert calls[1].kwargs["api_base"] == "http://ollama:11434"

def test_circuit_breaker_open_skips_primary(mock_redis, mock_embedding, auth_headers):
    # Trip the breaker manually and recently
    import time
    completions_module.primary_breaker.state = CircuitBreakerState.OPEN
    completions_module.primary_breaker.last_failure_time = time.monotonic()
    
    mock_response = MagicMock()
    mock_response.id = "fallback-id"
    mock_response.created = 1234567890
    mock_response.model = "qwen2.5:0.5b"
    mock_choice = MagicMock()
    mock_choice.index = 0
    mock_choice.message.role = "assistant"
    mock_choice.message.content = "fallback content"
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_response.usage.total_tokens = 30

    import uuid
    unique_content = f"hello {uuid.uuid4()}"
    with patch("app.api.completions.litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_llm:
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                headers=auth_headers,
                json={
                    "model": "gemini/gemini-2.5-flash",
                    "messages": [{"role": "user", "content": unique_content}],
                    "stream": False
                }
            )
            
            assert response.status_code == 200
            assert response.json()["choices"][0]["message"]["content"] == "fallback content"
            
            # Verify that acompletion was called exactly once, directly for fallback
            assert mock_llm.call_count == 1
            assert mock_llm.call_args_list[0].kwargs["model"] == "ollama/qwen2.5:0.5b"



def _make_mock_response(model_name: str) -> MagicMock:
    """Helper: build a MagicMock shaped like litellm.ModelResponse."""
    mock = MagicMock()
    mock.id = f"test-{model_name}"
    mock.created = 1234567890
    mock.model = model_name
    choice = MagicMock()
    choice.index = 0
    choice.message.role = "assistant"
    choice.message.content = f"response from {model_name}"
    choice.finish_reason = "stop"
    mock.choices = [choice]
    mock.usage.prompt_tokens = 10
    mock.usage.completion_tokens = 20
    mock.usage.total_tokens = 30
    return mock


@pytest.mark.asyncio
async def test_half_open_concurrent_requests_only_one_probes(reset_breaker, auth_headers):
    """Two requests via asyncio.gather while HALF_OPEN: first gets the probe,
    second is rejected and routed to fallback. The probe flag survives until
    the first request genuinely completes — not reset prematurely."""

    # Put the breaker into a state where the next allow_request() transitions
    # OPEN → HALF_OPEN (last failure was long ago, recovery_timeout elapsed).
    completions_module.primary_breaker.state = CircuitBreakerState.OPEN
    completions_module.primary_breaker.last_failure_time = time.monotonic() - 999
    completions_module.primary_breaker.failure_count = 5

    # Gate: the primary probe blocks on this event so we can interleave.
    probe_release = asyncio.Event()
    # Signal: set when the primary probe has started (allow_request returned True
    # and the acompletion mock entered), so we know it's safe to fire the second request.
    probe_started = asyncio.Event()

    async def mock_acompletion(*args, **kwargs):
        model = kwargs.get("model", "")
        if "ollama" in model:
            # Fallback path — return immediately
            return _make_mock_response("ollama-fallback")
        # Primary probe path — signal start, then block until released
        probe_started.set()
        await probe_release.wait()
        return _make_mock_response("gemini-probe")

    with patch("app.api.completions.litellm.acompletion", side_effect=mock_acompletion):
        with patch("app.core.cache.get_redis") as mock_get_redis:
            mock_redis = AsyncMock()
            mock_redis.get.return_value = None  # cache miss
            mock_get_redis.return_value = mock_redis

            with patch("app.api.completions.generate_embedding", return_value=[0.1]):
                with patch("app.api.completions.write_metrics"):
                    from app.core.redis import redis_lifespan
                    async with redis_lifespan(app), AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:

                        import uuid
                        unique_content = f"concurrent half-open test {uuid.uuid4()}"
                        payload = {
                            "model": "gemini/gemini-2.5-flash",
                            "messages": [{"role": "user", "content": unique_content}],
                            "stream": False
                        }

                        # Fire request 1 (the probe)
                        task1 = asyncio.create_task(client.post("/v1/chat/completions", headers=auth_headers, json=payload))

                        # Wait until the probe has entered the slow primary mock
                        await asyncio.wait_for(probe_started.wait(), timeout=5.0)

                        # At this point: breaker is HALF_OPEN, probe flag is True.
                        assert completions_module.primary_breaker._half_open_probe_in_flight

                        # Fire request 2 — should be rejected by allow_request()
                        task2 = asyncio.create_task(client.post("/v1/chat/completions", headers=auth_headers, json=payload))

                        # Let task2 reach allow_request() and get routed to fallback.
                        # The fallback mock returns instantly, so task2 will complete.
                        # Give it a moment to run.
                        await asyncio.sleep(0.05)

                        # Probe flag must STILL be True — task2 didn't reset it
                        assert completions_module.primary_breaker._half_open_probe_in_flight

                        # Now release the probe so task1 can finish
                        probe_release.set()

                        resp1, resp2 = await asyncio.gather(task1, task2)

    # After both complete, the probe flag should be cleared by the finally block
    assert not completions_module.primary_breaker._half_open_probe_in_flight

    # One response came from the primary probe, one from the fallback
    models = {resp1.json()["model"], resp2.json()["model"]}
    assert "gemini-probe" in models, f"Expected gemini-probe in {models}"
    assert "ollama-fallback" in models, f"Expected ollama-fallback in {models}"




