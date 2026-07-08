"""
LLMGov — Chat Completions Route

POST /v1/chat/completions — single-provider path via LiteLLM.
W1-C3: Gemini (gemini/gemini-2.5-flash) hardcoded as the only
provider. No cache, no guardrails, no registry — those are later.
"""

import os
import time

import litellm
from fastapi import APIRouter, BackgroundTasks

import asyncio
from app.config.settings import settings
from app.core.cache import get_cached_completion, set_cached_completion, hash_embedding_stub
from app.core.embeddings import generate_embedding
from app.core.logging import get_logger
from app.core.telemetry import write_metrics
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


def _extract_provider(model: str) -> str:
    """Extract provider name from litellm model string (e.g. 'gemini/gemini-2.5-flash' → 'gemini')."""
    return model.split("/")[0] if "/" in model else "unknown"


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(request: ChatCompletionRequest, background_tasks: BackgroundTasks) -> ChatCompletionResponse:
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
    prompt_version = "v1" # Hardcoded for now per spec chunks

    # ── 1. Cache Read Path (Stubbed Hash) ──
    # Fast exact-match hash before any external API calls
    messages_dicts = [m.model_dump() for m in request.messages]
    prompt_hash = hash_embedding_stub(messages_dicts)
    
    cached_payload = await get_cached_completion(
        prompt_version=prompt_version, 
        model=request.model, 
        prompt_hash=prompt_hash
    )
    
    if cached_payload:
        logger.info(
            "Semantic cache hit",
            extra={"model": request.model, "hash": prompt_hash}
        )
        # Parse and return cached payload
        return ChatCompletionResponse(**cached_payload)
        
    logger.info("Semantic cache miss", extra={"model": request.model, "hash": prompt_hash})

    # ── 2. Cache Miss Path: Call LLM and Compute Embedding ──
    
    # We fire both the completion and the embedding concurrently
    # The real semantic match logic later will require embeddings on the read path, 
    # but for now we only compute it on a miss to store it for future.
    completion_task = litellm.acompletion(
        model=request.model,
        messages=messages_dicts,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
    
    # Semantic caching compares the user's explicit question, not the system prompt.
    # Therefore, we embed only the latest user message to capture the true intent.
    # Find the last message with role 'user'. If none exists, default to the last message.
    latest_user_content = next(
        (m.content for m in reversed(request.messages) if m.role == "user"),
        request.messages[-1].content if request.messages else ""
    )
    embedding_task = generate_embedding(latest_user_content)
    
    results = await asyncio.gather(completion_task, embedding_task, return_exceptions=True)
    
    completion_result = results[0]
    embedding_result = results[1]

    if isinstance(completion_result, Exception):
        # If the completion fails, we must bubble it up (500)
        raise completion_result
        
    import typing
    response = typing.cast(litellm.ModelResponse, completion_result)
    
    if isinstance(embedding_result, Exception):
        # If the embedding fails, we log it and continue without vector
        logger.error("Embedding generation failed, vector will not be cached", exc_info=embedding_result)
        vector: list[float] = []
    else:
        vector = embedding_result

    elapsed_ms = (time.perf_counter() * 1000) - start_ms
    provider = _extract_provider(request.model)

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
            "provider": provider,
            "latency_ms": round(elapsed_ms, 1),
            "status_code": 200,
        },
    )

    # ── W1-C4: Write telemetry row to ClickHouse ──
    # Uses the same trace_id from X-Request-ID — no second UUID.
    await write_metrics(
        trace_id=trace_id,
        model_requested=request.model,
        model_used=result.model,
        provider=provider,
        total_duration_ms=round(elapsed_ms, 1),
        status_code=200,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
    )

    # ── Cache Write Path ──
    # Fire and forget cache update using FastAPI BackgroundTasks
    background_tasks.add_task(
        set_cached_completion,
        prompt_version=prompt_version,
        model=request.model,
        prompt_hash=prompt_hash,
        payload=result.model_dump(),
        vector=vector
    )

    return result

