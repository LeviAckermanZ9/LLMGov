import pytest
pytestmark = pytest.mark.usefixtures('mock_jailbreak_globally', 'mock_eval_globally')
from unittest.mock import patch, MagicMock, AsyncMock
from fastapi.testclient import TestClient
from app.main import app

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
    mock.get = AsyncMock(return_value=None)
    mock.set = AsyncMock(return_value=True)
    yield mock

def test_pii_redacted_before_sending_to_gemini(mock_litellm, mock_embedding, mock_telemetry, mock_redis_client, auth_headers):
    with patch("app.api.completions.authenticate_api_key", AsyncMock(return_value="dev_app")), \
         patch("app.api.completions.check_rate_limit", AsyncMock(return_value=True)), \
         patch("app.core.cache.get_redis", return_value=mock_redis_client):
         
        client = TestClient(app)
        response = client.post(
            "/v1/chat/completions",
            headers=auth_headers,
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "My email is test@example.com."}],
                "stream": False
            }
        )
        assert response.status_code == 200
        
        # Verify litellm was called with the redacted messages
        mock_litellm.assert_called_once()
        called_args, called_kwargs = mock_litellm.call_args
        
        # The messages passed to litellm should be redacted
        messages = called_kwargs["messages"]
        assert messages[0]["content"] == "My email is [EMAIL]."
        
        # Verify the embedding was also generated on redacted text
        mock_embedding.assert_called_once_with("My email is [EMAIL].")
