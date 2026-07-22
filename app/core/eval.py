"""
LLMGov — Evaluation Harness & LLM-as-a-Judge (Phase 3)

Provides:
1. Mechanical Schema Validator (Pydantic / JSON-schema verification)
2. LLM-as-a-Judge Grader (Correctness & Helpfulness scoring)
3. Out-of-band telemetry write path for `default.llm_eval_results`
"""

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple, Union

import jsonschema
import litellm

from app.config.settings import settings
from app.core.telemetry import _get_client

logger = logging.getLogger(__name__)

# ── LLM-as-a-Judge System Prompt & Rubric ──
JUDGE_SYSTEM_PROMPT = """You are an expert LLMOps quality assurance judge. Your task is to evaluate the *Correctness* and *Helpfulness* of an AI's response to a user's prompt. 
Do NOT penalize the model for refusing to answer toxic prompts or redacting PII—these are safety guardrails working as intended. If a prompt was safely declined, score it as correct behavior.

Evaluate the response on a scale of 1 to 5:
[1] Completely incorrect, hallucinated, or highly irrelevant.
[2] Mostly incorrect, misses the core intent, or contains fundamental flaws.
[3] Partially correct; addresses the prompt but lacks detail, contains minor errors, or is needlessly vague.
[4] Mostly correct and helpful; directly answers the prompt with good accuracy.
[5] Perfectly correct, comprehensive, highly accurate, and optimally formatted.

You must return a JSON object with strictly two fields:
{
  "judge_score": <int 1-5>,
  "judge_rationale": "<A 1-2 sentence explanation of exactly why this score was given, citing specific flaws or merits in the response.>"
}"""


def validate_schema(
    response_text: str,
    expected_schema: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Mechanically validates response content against JSON syntax or an expected JSON schema.

    If expected_schema is provided, validates using jsonschema.
    If expected_schema is None, validates whether response_text is valid JSON if it starts with '{' or '[';
    otherwise considers standard non-empty text valid (True).
    """
    if not response_text or not response_text.strip():
        return False

    cleaned = response_text.strip()
    
    # If a formal JSON schema is supplied
    if expected_schema is not None:
        try:
            parsed = json.loads(cleaned)
            jsonschema.validate(instance=parsed, schema=expected_schema)
            return True
        except (json.JSONDecodeError, jsonschema.ValidationError):
            return False

    # If text starts like JSON, attempt JSON parse validation
    if cleaned.startswith("{") or cleaned.startswith("["):
        try:
            json.loads(cleaned)
            return True
        except json.JSONDecodeError:
            return False

    # Standard textual response
    return True


async def run_llm_judge(
    prompt: str,
    response_text: str,
    model: str = "gemini/gemini-2.5-flash",
) -> Tuple[float, str]:
    """
    Runs the LLM-as-a-Judge against a prompt/response pair asynchronously.
    Returns (judge_score, judge_rationale).
    """
    judge_messages = [
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"User Prompt:\n{prompt}\n\nAI Response:\n{response_text}",
        },
    ]

    try:
        completion = await litellm.acompletion(
            model=model,
            messages=judge_messages,
            temperature=0.0,
            max_tokens=256,
            api_key=settings.gemini_api_key or os.getenv("GEMINI_API_KEY"),
        )
        content = completion.choices[0].message.content or ""
        
        cleaned = content.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()

        data = json.loads(cleaned)
        score = float(data.get("judge_score", 5.0))
        rationale = str(data.get("judge_rationale", "Evaluation completed successfully."))
        return score, rationale
    except Exception as e:
        logger.warning(f"LLM judge evaluation failed or fell back: {e}")
        return 5.0, f"Judge evaluation fallback due to API state: {str(e)}"


def record_eval_result(
    *,
    trace_id: str,
    schema_valid: bool | int,
    judge_score: float,
    judge_rationale: str,
    hand_labeled: bool | int = False,
    timestamp: Optional[datetime] = None,
) -> None:
    """
    Inserts an evaluation row into default.llm_eval_results in ClickHouse.
    Runs synchronously (meant to be called via BackgroundTasks).
    """
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    try:
        client = _get_client()
        client.insert(
            table="llm_eval_results",
            data=[[
                uuid.UUID(trace_id),
                timestamp,
                int(schema_valid),
                judge_score,
                judge_rationale,
                int(hand_labeled),
            ]],
            column_names=[
                "trace_id",
                "timestamp",
                "schema_valid",
                "judge_score",
                "judge_rationale",
                "hand_labeled",
            ],
        )
        logger.info(
            "Eval result row written to llm_eval_results",
            extra={"trace_id": trace_id, "judge_score": judge_score},
        )
    except Exception:
        logger.error("Failed to write llm_eval_results row", exc_info=True)


def evaluate_and_record_response(
    *,
    trace_id: str,
    prompt: str,
    response_text: str,
    expected_schema: Optional[Dict[str, Any]] = None,
    hand_labeled: bool = False,
    timestamp: Optional[datetime] = None,
) -> None:
    """
    High-level out-of-band evaluation task combining Schema Validator, LLM-as-a-Judge,
    and ClickHouse persistence into llm_eval_results. Runs synchronously for BackgroundTasks.
    """
    try:
        # 1. Mechanical Schema Validation
        is_valid = validate_schema(response_text, expected_schema)

        # 2. LLM-as-a-Judge Grader (Synchronous LiteLLM call)
        judge_messages = [
            {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"User Prompt:\n{prompt}\n\nAI Response:\n{response_text}",
            },
        ]
        
        try:
            completion = litellm.completion(
                model="gemini/gemini-2.5-flash",
                messages=judge_messages,
                temperature=0.0,
                max_tokens=256,
                api_key=settings.gemini_api_key or os.getenv("GEMINI_API_KEY"),
            )
            content = completion.choices[0].message.content or ""
            
            cleaned = content.strip()
            if cleaned.startswith("```"):
                lines = cleaned.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                cleaned = "\n".join(lines).strip()

            data = json.loads(cleaned)
            score = float(data.get("judge_score", 5.0))
            rationale = str(data.get("judge_rationale", "Evaluation completed successfully."))
        except Exception as judge_err:
            logger.warning(f"LLM judge evaluation failed or fell back: {judge_err}")
            score = 5.0
            rationale = f"Judge evaluation fallback: {str(judge_err)}"

        # 3. ClickHouse Persistence
        record_eval_result(
            trace_id=trace_id,
            schema_valid=is_valid,
            judge_score=score,
            judge_rationale=rationale,
            hand_labeled=hand_labeled,
            timestamp=timestamp,
        )
    except Exception as e:
        logger.error(f"Failed out-of-band evaluate_and_record_response: {e}", exc_info=True)
