import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

@pytest.mark.asyncio
async def test_telemetry_write_failure_does_not_break_response(caplog):
    # Setup mock litellm response
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

    # Create a mock ClickHouse client where insert() fails
    mock_ch_client = MagicMock()
    mock_ch_client.insert.side_effect = Exception("Simulated ClickHouse timeout")

    with patch("app.api.completions.litellm.acompletion", return_value=mock_response), \
         patch("app.core.telemetry._get_client", return_value=mock_ch_client):
        
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "gemini/gemini-2.5-flash",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": False
            }
        )

        # 1. Assert response is still 200 OK
        assert response.status_code == 200
        
        # 2. Assert response contains the correct payload
        data = response.json()
        assert data["model"] == "gemini/gemini-2.5-flash"
        assert data["choices"][0]["message"]["content"] == "mock content"

        # 3. Assert ClickHouse insert was actually attempted
        mock_ch_client.insert.assert_called_once()
        
        # 4. Assert telemetry failure was logged
        assert "Failed to write telemetry row" in caplog.text
        assert "Simulated ClickHouse timeout" in caplog.text
