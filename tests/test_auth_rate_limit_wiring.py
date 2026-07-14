import pytest
import hashlib
from typing import Any, Awaitable, cast
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from redis.exceptions import ConnectionError

from app.main import app
from app.core.redis import redis_lifespan, get_redis
from app.core.auth import InvalidAPIKeyError, AuthServiceUnavailableError
from app.core.rate_limiter import RateLimiterUnavailableError

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

@pytest.fixture
def mock_telemetry():
    with patch("app.api.completions.write_metrics") as p:
        yield p

@pytest.fixture
def mock_redis_client():
    mock = MagicMock()
    # Cache get/set stubs
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    yield mock

@pytest.mark.asyncio
async def test_wiring_success_valid_key(mock_litellm, mock_embedding, mock_telemetry, mock_redis_client):
    """Test 1: Request with a valid, registered key succeeds with 200 OK."""
    with patch("app.api.completions.authenticate_api_key", AsyncMock(return_value="dev_app")) as mock_auth, \
         patch("app.api.completions.check_rate_limit", AsyncMock(return_value=True)) as mock_limit, \
         patch("app.core.cache.get_redis", return_value=mock_redis_client):
         
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer llmgov_sk_valid_key"},
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}]
            }
        )
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "mock content"
        mock_auth.assert_called_once_with("llmgov_sk_valid_key")
        mock_limit.assert_called_once_with("dev_app", limit=60, window_seconds=60)
        mock_telemetry.assert_called_once()
        assert mock_telemetry.call_args[1]["app_id"] == "dev_app"

@pytest.mark.asyncio
async def test_wiring_invalid_key(mock_litellm, mock_embedding, mock_telemetry, mock_redis_client):
    """Test 2: Request with an invalid key returns 401 Unauthorized."""
    with patch("app.api.completions.authenticate_api_key", AsyncMock(side_effect=InvalidAPIKeyError("Invalid API key"))), \
         patch("app.core.cache.get_redis", return_value=mock_redis_client):
         
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer llmgov_sk_invalid_key"},
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}]
            }
        )
        assert response.status_code == 401
        assert "Unauthorized" in response.json()["error"]["message"]
        assert response.json()["error"]["type"] == "invalid_api_key"
        mock_litellm.assert_not_called()

@pytest.mark.asyncio
async def test_wiring_missing_key(mock_litellm, mock_embedding, mock_telemetry, mock_redis_client):
    """Test 3: Request with missing or empty Authorization header returns 401 Unauthorized."""
    with patch("app.api.completions.authenticate_api_key", AsyncMock(side_effect=InvalidAPIKeyError("API key cannot be empty"))), \
         patch("app.core.cache.get_redis", return_value=mock_redis_client):
         
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            headers={},
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}]
            }
        )
        assert response.status_code == 401
        assert response.json()["error"]["type"] == "invalid_api_key"
        mock_litellm.assert_not_called()

@pytest.mark.asyncio
async def test_wiring_auth_redis_unavailable(mock_litellm, mock_embedding, mock_telemetry, mock_redis_client):
    """Test 4: Request with Redis down during auth returns 503 Service Unavailable."""
    with patch("app.api.completions.authenticate_api_key", AsyncMock(side_effect=AuthServiceUnavailableError("Redis error"))), \
         patch("app.core.cache.get_redis", return_value=mock_redis_client):
         
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer llmgov_sk_any_key"},
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}]
            }
        )
        assert response.status_code == 503
        assert "Service Unavailable" in response.json()["error"]["message"]
        assert response.json()["error"]["type"] == "service_unavailable"
        mock_litellm.assert_not_called()

@pytest.mark.asyncio
async def test_wiring_rate_limit_exceeded(mock_litellm, mock_embedding, mock_telemetry, mock_redis_client):
    """Test 5: Request exceeding the rate limit returns 429 Too Many Requests."""
    with patch("app.api.completions.authenticate_api_key", AsyncMock(return_value="dev_app")), \
         patch("app.api.completions.check_rate_limit", AsyncMock(return_value=False)), \
         patch("app.core.cache.get_redis", return_value=mock_redis_client):
         
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer llmgov_sk_valid_key"},
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}]
            }
        )
        assert response.status_code == 429
        assert "Too Many Requests" in response.json()["error"]["message"]
        assert response.json()["error"]["type"] == "rate_limit_exceeded"
        mock_litellm.assert_not_called()

@pytest.mark.asyncio
async def test_wiring_rate_limit_redis_unavailable_fails_open(mock_litellm, mock_embedding, mock_telemetry, mock_redis_client):
    """Test 6: Request with Redis down during rate limiting check succeeds (fails open, returns 200 OK)."""
    with patch("app.api.completions.authenticate_api_key", AsyncMock(return_value="dev_app")), \
         patch("app.api.completions.check_rate_limit", AsyncMock(side_effect=RateLimiterUnavailableError("Redis error"))), \
         patch("app.core.cache.get_redis", return_value=mock_redis_client):
         
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            headers={"Authorization": "Bearer llmgov_sk_valid_key"},
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hi"}]
            }
        )
        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "mock content"
        mock_litellm.assert_called_once()
        mock_telemetry.assert_called_once()
        assert mock_telemetry.call_args[1]["app_id"] == "dev_app"
