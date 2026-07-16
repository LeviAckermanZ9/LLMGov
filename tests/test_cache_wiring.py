import pytest
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.models.completions import ChatCompletionResponse
from app.core.redis import _redis_client

@pytest.fixture
def mock_redis():
    mock = AsyncMock()
    # default to miss
    mock.get.return_value = None
    
    # We must patch get_redis instead of _redis_client because it's required by the cache functions
    with patch("app.core.cache.get_redis", return_value=mock):
        yield mock

@pytest.fixture
def mock_litellm():
    mock_response = MagicMock()
    mock_response.id = "mock-id"
    mock_response.created = 1234567890
    mock_response.model = "gemini/gemini-2.5-flash"
    mock_choice = MagicMock()
    mock_choice.index = 0
    mock_choice.message.role = "assistant"
    mock_choice.message.content = "mock content"
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20
    mock_response.usage.total_tokens = 30
    
    with patch("app.api.completions.litellm.acompletion", return_value=mock_response) as p:
        yield p

@pytest.fixture
def mock_embedding():
    with patch("app.api.completions.generate_embedding", return_value=[0.1, 0.2, 0.3]) as p:
        yield p

def test_cache_miss_writes_to_redis(mock_redis, mock_litellm, mock_embedding, auth_headers):
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello cache miss"}],
                "stream": False
            }
        )
        assert response.status_code == 200
        mock_redis.get.assert_called_once()
        mock_litellm.assert_called_once()
        mock_embedding.assert_called_once()
        mock_redis.pipeline.assert_called_once()

def test_cache_hit_returns_immediately(mock_redis, mock_litellm, mock_embedding, auth_headers):
    import json
    
    # Simulate a hit
    mock_redis.get.return_value = json.dumps({
        "id": "cached-id",
        "created": 12345,
        "model": "gemini/gemini-2.5-flash",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": "cached response"},
            "finish_reason": "stop"
        }],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        "trace_id": "test-trace"
    })
    
    with TestClient(app) as client:
        response = client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello cache hit"}],
                "stream": False
            }
        )
        
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "cached response"
        
        # Assert hit returned immediately
        mock_redis.get.assert_called_once()
        mock_litellm.assert_not_called()
        mock_embedding.assert_not_called()
        mock_redis.pipeline.assert_not_called()

def test_embedding_base_exception_handled(mock_redis, mock_litellm, auth_headers):
    # Simulate embedding throwing asyncio.CancelledError
    mock_cancelled_embedding = AsyncMock(side_effect=asyncio.CancelledError("Embedding cancelled"))
    
    with patch("app.api.completions.generate_embedding", new=mock_cancelled_embedding):
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                headers=auth_headers,
                json={
                    "model": "gemini/gemini-2.5-flash",
                    "messages": [{"role": "user", "content": "embedding fail"}],
                    "stream": False
                }
            )
            assert response.status_code == 200
            mock_redis.get.assert_called_once()
            mock_litellm.assert_called_once()
            
            # Assert pipeline was still called (since cache writes proceed even without vector)
            mock_redis.pipeline.assert_called_once()

    
    # Extract the kwargs of the set_cached_completion call sent to BackgroundTasks
    # It's difficult to assert directly on the background task since it fires async,
    # but the API response indicates no crash and the vector was defaulted to [].
