import hashlib
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.telemetry import (
    GENESIS_HASH,
    compute_row_hash,
    record_audit_log,
    serialize_audit_row,
)
from app.main import app


def test_genesis_hash_constant():
    assert GENESIS_HASH == "0000000000000000000000000000000000000000000000000000000000000000"
    assert len(GENESIS_HASH) == 64


def test_serialize_audit_row_determinism():
    now = datetime(2026, 7, 22, 12, 0, 0, tzinfo=timezone.utc)
    trace_id = str(uuid.uuid4())

    serialized_1 = serialize_audit_row(
        trace_id=trace_id,
        timestamp=now,
        sanitized_prompt='[{"role":"user","content":"hello"}]',
        raw_response="hello response",
        has_pii_redacted=True,
        toxicity_score=0.05,
        jailbreak_score=0.01,
    )

    serialized_2 = serialize_audit_row(
        trace_id=trace_id,
        timestamp=now,
        sanitized_prompt='[{"role":"user","content":"hello"}]',
        raw_response="hello response",
        has_pii_redacted=1,
        toxicity_score=0.05,
        jailbreak_score=0.01,
    )

    assert serialized_1 == serialized_2

    parsed = json.loads(serialized_1)
    keys = list(parsed.keys())
    assert keys == sorted(keys)


def test_compute_row_hash():
    prev_hash = GENESIS_HASH
    serialized_row = '{"has_pii_redacted":0,"jailbreak_score":0.0,"raw_response":"test","sanitized_prompt":"test","timestamp":"2026-07-22T12:00:00+00:00","toxicity_score":0.0,"trace_id":"1234"}'
    
    expected_hash = hashlib.sha256(f"{prev_hash}{serialized_row}".encode("utf-8")).hexdigest()
    computed = compute_row_hash(prev_hash, serialized_row)

    assert computed == expected_hash


@pytest.mark.asyncio
async def test_record_audit_log_without_redis():
    mock_ch_client = MagicMock()

    with patch("app.core.telemetry._get_client", return_value=mock_ch_client), \
         patch("app.core.telemetry.get_redis", side_effect=RuntimeError("Redis uninitialized")):
        
        trace_id = str(uuid.uuid4())
        await record_audit_log(
            trace_id=trace_id,
            sanitized_prompt='[{"role":"user","content":"hello"}]',
            raw_response="world",
            has_pii_redacted=False,
            toxicity_score=0.0,
            jailbreak_score=0.0,
        )

        mock_ch_client.insert.assert_called_once()
        call_kwargs = mock_ch_client.insert.call_args.kwargs
        assert call_kwargs["table"] == "llm_audit_logs"
        inserted_data = call_kwargs["data"][0]
        # prev_hash should be GENESIS_HASH
        assert inserted_data[7] == GENESIS_HASH


@pytest.mark.asyncio
async def test_audit_log_integration_route(auth_headers):
    mock_response = MagicMock()
    mock_response.id = "mock-id"
    mock_response.created = 1234567890
    mock_response.model = "gemini/gemini-2.5-flash"
    mock_choice = MagicMock()
    mock_choice.index = 0
    mock_choice.message.role = "assistant"
    mock_choice.message.content = "mock response content"
    mock_choice.finish_reason = "stop"
    mock_response.choices = [mock_choice]
    mock_response.usage.prompt_tokens = 10
    mock_response.usage.completion_tokens = 20

    mock_ch_client = MagicMock()

    with patch("app.api.completions.litellm.acompletion", return_value=mock_response), \
         patch("app.core.telemetry._get_client", return_value=mock_ch_client):
        
        with TestClient(app) as client:
            response = client.post(
                "/v1/chat/completions",
                headers=auth_headers,
                json={
                    "model": "gemini/gemini-2.5-flash",
                    "messages": [{"role": "user", "content": "test audit chain"}],
                }
            )

        assert response.status_code == 200
        assert response.json()["choices"][0]["message"]["content"] == "mock response content"
