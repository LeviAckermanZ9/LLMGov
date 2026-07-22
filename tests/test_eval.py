"""
LLMGov — Phase 3 Evaluation Harness Unit Tests

Tests:
1. Mechanical Schema Validator (validate_schema)
2. LLM-as-a-Judge parser & fallback execution (run_llm_judge)
3. ClickHouse persistence to llm_eval_results (record_eval_result)
4. Out-of-band completion route background task wiring
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.core.eval import evaluate_and_record_response, record_eval_result, run_llm_judge, validate_schema


def test_validate_schema_plain_text():
    """Validates that plain text non-JSON is considered valid schema by default."""
    assert validate_schema("The capital of France is Paris.") is True
    assert validate_schema("") is False
    assert validate_schema("   ") is False


def test_validate_schema_json():
    """Validates valid JSON parsing and invalid JSON syntax detection."""
    assert validate_schema('{"status": "ok", "count": 1}') is True
    assert validate_schema('{"status": "ok", "count":') is False
    assert validate_schema('[1, 2, 3]') is True
    assert validate_schema('[1, 2,') is False


def test_validate_schema_with_json_schema():
    """Validates mechanical Pydantic / JSON-schema enforcement."""
    schema = {
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "age": {"type": "integer"},
        },
        "required": ["name", "age"],
    }

    valid_payload = '{"name": "Alice", "age": 30}'
    invalid_payload_type = '{"name": "Alice", "age": "thirty"}'
    invalid_payload_missing = '{"name": "Alice"}'

    assert validate_schema(valid_payload, expected_schema=schema) is True
    assert validate_schema(invalid_payload_type, expected_schema=schema) is False
    assert validate_schema(invalid_payload_missing, expected_schema=schema) is False


@pytest.mark.asyncio
async def test_run_llm_judge_success():
    """Tests successful LLM judge execution and JSON score/rationale extraction."""
    mock_response = MagicMock()
    mock_response.choices = [
        MagicMock(message=MagicMock(content='```json\n{"judge_score": 5, "judge_rationale": "Perfect response."}\n```'))
    ]

    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_litellm:
        mock_litellm.return_value = mock_response

        score, rationale = await run_llm_judge(
            prompt="What is the capital of France?",
            response_text="The capital of France is Paris.",
        )

        assert score == 5.0
        assert rationale == "Perfect response."
        mock_litellm.assert_called_once()


@pytest.mark.asyncio
async def test_run_llm_judge_fallback_on_error():
    """Tests that LLM judge returns graceful fallback score on API failure."""
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_litellm:
        mock_litellm.side_effect = Exception("API connection timed out")

        score, rationale = await run_llm_judge(
            prompt="What is the capital of France?",
            response_text="The capital of France is Paris.",
        )

        assert score == 5.0
        assert "fallback" in rationale.lower()


def test_record_eval_result_clickhouse():
    """Tests ClickHouse insertion logic into default.llm_eval_results."""
    mock_ch_client = MagicMock()
    trace_id = str(uuid.uuid4())

    with patch("app.core.eval._get_client", return_value=mock_ch_client):
        record_eval_result(
            trace_id=trace_id,
            schema_valid=True,
            judge_score=4.5,
            judge_rationale="Solid response.",
            hand_labeled=False,
        )

        mock_ch_client.insert.assert_called_once()
        call_kwargs = mock_ch_client.insert.call_args.kwargs
        assert call_kwargs["table"] == "llm_eval_results"
        assert call_kwargs["data"][0][0] == uuid.UUID(trace_id)
        assert call_kwargs["data"][0][2] == 1  # schema_valid int
        assert call_kwargs["data"][0][3] == 4.5  # judge_score float
        assert call_kwargs["data"][0][4] == "Solid response."
        assert call_kwargs["data"][0][5] == 0  # hand_labeled int


def test_evaluate_and_record_response_flow():
    """Tests high-level evaluate_and_record_response task combining validation, judge, and DB insert."""
    mock_ch_client = MagicMock()
    mock_judge_response = MagicMock()
    mock_judge_response.choices = [
        MagicMock(message=MagicMock(content='{"judge_score": 4, "judge_rationale": "Mostly correct."}'))
    ]

    with patch("app.core.eval._get_client", return_value=mock_ch_client), \
         patch("litellm.completion") as mock_litellm:
        mock_litellm.return_value = mock_judge_response

        trace_id = str(uuid.uuid4())
        evaluate_and_record_response(
            trace_id=trace_id,
            prompt="Explain quantum computing.",
            response_text="Quantum computing uses qubits in superposition.",
        )

        mock_ch_client.insert.assert_called_once()
        inserted_data = mock_ch_client.insert.call_args.kwargs["data"][0]
        assert inserted_data[0] == uuid.UUID(trace_id)
        assert inserted_data[2] == 1  # schema_valid
        assert inserted_data[3] == 4.0  # judge_score
        assert inserted_data[4] == "Mostly correct."
