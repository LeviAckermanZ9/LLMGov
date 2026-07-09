import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.core.circuit_breaker import CircuitBreakerState
import app.api.completions as completions_module
from litellm.exceptions import ServiceUnavailableError

@pytest.fixture(autouse=True)
def reset_breaker():
    # Reset the global breaker before each test
    completions_module.primary_breaker.state = CircuitBreakerState.CLOSED
    completions_module.primary_breaker.failure_count = 0
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

def test_circuit_breaker_fallback_on_failure(mock_redis, mock_embedding):
    client = TestClient(app)
    
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

    with patch("app.api.completions.litellm.acompletion", new_callable=AsyncMock, side_effect=mock_acompletion) as mock_llm:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello"}],
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

def test_circuit_breaker_open_skips_primary(mock_redis, mock_embedding):
    client = TestClient(app)
    
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

    with patch("app.api.completions.litellm.acompletion", new_callable=AsyncMock, return_value=mock_response) as mock_llm:
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "fallback content"
        
        # Verify that acompletion was called exactly once, directly for fallback
        assert mock_llm.call_count == 1
        assert mock_llm.call_args_list[0].kwargs["model"] == "ollama/qwen2.5:0.5b"
