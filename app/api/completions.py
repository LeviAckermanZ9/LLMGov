"""
LLMGov — Chat Completions Route

POST /v1/chat/completions — single-provider path via LiteLLM.
W1-C3: Gemini (gemini/gemini-2.5-flash) hardcoded as the only
provider. No cache, no guardrails, no registry — those are later.
"""

import os
import time

import litellm
from fastapi import APIRouter

from app.config.settings import settings
from app.core.logging import get_logger
from app.middleware.request_id import get_request_id
from app.models.completions import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    UsageInfo,
)

# ── Export API keys to os.environ for litellm ──
# litellm reads keys from os.environ, not Python variables.
# pydantic-settings loads .env → Python attrs, so we bridge the gap.
if settings.gemini_api_key:
    os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["completions"])


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest) -> ChatCompletionResponse:
    """
    Proxies a chat completion request through LiteLLM to the
    configured LLM provider. Returns an OpenAI-compatible response.
    """
    trace_id = get_request_id() or "unknown"

    if request.stream:
        # Streaming will be wired in a later chunk
        raise ValueError("Streaming is not yet supported. Set stream=false.")

    logger.info(
        "Completion request received",
        extra={"model": request.model, "app_id": "default"},
    )

    start_ms = time.perf_counter() * 1000

    # ── Call LiteLLM ──
    # litellm reads GEMINI_API_KEY from the environment automatically
    # when the model string starts with "gemini/"
    response = await litellm.acompletion(
        model=request.model,
        messages=[m.model_dump() for m in request.messages],
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )

    elapsed_ms = (time.perf_counter() * 1000) - start_ms

    # ── Map LiteLLM response → our Pydantic model ──
    result = ChatCompletionResponse(
        id=response.id or f"llmgov-{trace_id}",
        created=response.created or int(time.time()),
        model=response.model or request.model,
        choices=[
            Choice(
                index=c.index,
                message=ChoiceMessage(
                    role=c.message.role,
                    content=c.message.content,
                ),
                finish_reason=c.finish_reason,
            )
            for c in response.choices
        ],
        usage=UsageInfo(
            prompt_tokens=getattr(response.usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(response.usage, "completion_tokens", 0) or 0,
            total_tokens=getattr(response.usage, "total_tokens", 0) or 0,
        ),
        trace_id=trace_id,
    )

    logger.info(
        "Completion returned",
        extra={
            "model": result.model,
            "provider": "gemini",
            "latency_ms": round(elapsed_ms, 1),
            "status_code": 200,
        },
    )

    return result
