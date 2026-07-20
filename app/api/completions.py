"""
LLMGov — Chat Completions Route

POST /v1/chat/completions — single-provider path via LiteLLM.
W1-C3: Gemini (gemini/gemini-2.5-flash) hardcoded as the only
provider. No cache, no guardrails, no registry — those are later.
"""

import time
import typing

import litellm
from fastapi import APIRouter, BackgroundTasks, Request
from fastapi.responses import JSONResponse
from app.core.auth import authenticate_api_key, InvalidAPIKeyError, AuthServiceUnavailableError
from app.core.rate_limiter import check_rate_limit, RateLimiterUnavailableError


import asyncio
from app.config.settings import settings
from app.core.cache import get_cached_completion, set_cached_completion, hash_embedding_stub
from app.core.circuit_breaker import CircuitBreaker
from app.core.embeddings import generate_embedding
from litellm.exceptions import Timeout, APIError, RateLimitError, ServiceUnavailableError
from app.core.logging import get_logger
from app.core.telemetry import write_metrics
from app.middleware.request_id import get_request_id
from app.core.pii import redact_pii
from app.core.toxicity import classify_toxicity
from app.models.completions import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    Choice,
    ChoiceMessage,
    UsageInfo,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/v1", tags=["completions"])

primary_breaker = CircuitBreaker()

def _extract_provider(model: str) -> str:
    """Extract provider name from litellm model string (e.g. 'gemini/gemini-2.5-flash' → 'gemini')."""
    return model.split("/")[0] if "/" in model else "unknown"


@router.post("/chat/completions", response_model=ChatCompletionResponse)
async def chat_completions(
    request: ChatCompletionRequest,
    http_request: Request,
    background_tasks: BackgroundTasks,
) -> typing.Union[ChatCompletionResponse, JSONResponse]:
    """
    Proxies a chat completion request through LiteLLM to the
    configured LLM provider. Returns an OpenAI-compatible response.
    """
    trace_id = get_request_id() or "unknown"

    # ── 0. Authenticate & Check Rate Limits ──
    # Extract API key from Authorization header or X-API-Key
    auth_header = http_request.headers.get("Authorization")
    raw_key = ""
    if auth_header and auth_header.startswith("Bearer "):
        raw_key = auth_header[7:]
    else:
        raw_key = http_request.headers.get("X-API-Key", "")

    # Auth check
    try:
        app_id = await authenticate_api_key(raw_key)
    except InvalidAPIKeyError as e:
        logger.warning(f"API key authentication failed: {str(e)}", extra={"trace_id": trace_id})
        return JSONResponse(
            status_code=401,
            content={
                "error": {
                    "type": "invalid_api_key",
                    "message": "Unauthorized: Invalid API key",
                    "trace_id": trace_id
                }
            }
        )
    except AuthServiceUnavailableError as e:
        logger.error("Authentication service unavailable due to Redis failure", exc_info=True, extra={"trace_id": trace_id})
        return JSONResponse(
            status_code=503,
            content={
                "error": {
                    "type": "service_unavailable",
                    "message": "Service Unavailable: Authentication service is temporarily unavailable",
                    "trace_id": trace_id
                }
            }
        )

    # Rate limit check (using 60 requests per 60 seconds as default limit)
    try:
        allowed = await check_rate_limit(app_id, limit=60, window_seconds=60)
        if not allowed:
            logger.warning(f"Rate limit exceeded for app_id: {app_id}", extra={"trace_id": trace_id})
            return JSONResponse(
                status_code=429,
                content={
                    "error": {
                        "type": "rate_limit_exceeded",
                        "message": "Too Many Requests: Rate limit exceeded",
                        "trace_id": trace_id
                    }
                }
            )
    except RateLimiterUnavailableError as e:
        # Fails open: log loudly, but proceed with request
        logger.error(
            f"Rate limiter service unavailable for app_id: {app_id}. Failing open.",
            exc_info=True,
            extra={"trace_id": trace_id}
        )

    if request.stream:
        # Streaming will be wired in a later chunk
        raise ValueError("Streaming is not yet supported. Set stream=false.")

    logger.info(
        "Completion request received",
        extra={"model": request.model, "app_id": app_id},
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
    # Run PII redaction on all messages before they are sent to the model or embedding API
    redacted_messages_dicts = []
    has_pii_redacted_any = False
    for msg in messages_dicts:
        content = msg.get("content", "")
        if isinstance(content, str):
            redacted_content, redacted_flag = redact_pii(content)
            if redacted_flag:
                has_pii_redacted_any = True
            msg_copy = dict(msg)
            msg_copy["content"] = redacted_content
            redacted_messages_dicts.append(msg_copy)
        else:
            redacted_messages_dicts.append(msg)

    latest_user_content = next(
        (m["content"] for m in reversed(redacted_messages_dicts) if m.get("role") == "user"),
        redacted_messages_dicts[-1]["content"] if redacted_messages_dicts else ""
    )
    logger.info(f"Extracted embedding input: {latest_user_content}")
    embedding_task = asyncio.create_task(generate_embedding(latest_user_content))
    
    fallback_used = False
    completion_result = None

    if primary_breaker.allow_request():
        try:
            completion_result = await litellm.acompletion(
                model=request.model,
                messages=redacted_messages_dicts,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
            )
            primary_breaker.record_success()
        except Exception as e:
            if isinstance(e, (Timeout, APIError, RateLimitError, ServiceUnavailableError, litellm.exceptions.NotFoundError)):
                primary_breaker.record_failure()
                logger.warning(f"Primary provider failed: {str(e)}. Falling back to Ollama.", extra={"trace_id": trace_id})
                fallback_used = True
            else:
                logger.error(f"Unexpected error in primary call: {str(e)}")
                raise e
        finally:
            primary_breaker.release_half_open_probe()
    else:
        logger.warning("Circuit breaker OPEN. Routing directly to Ollama fallback.", extra={"trace_id": trace_id})
        fallback_used = True

    if fallback_used:
        completion_result = await litellm.acompletion(
            model="ollama/qwen2.5:0.5b",
            api_base="http://ollama:11434",
            messages=redacted_messages_dicts,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )

    import typing
    response = typing.cast(litellm.ModelResponse, completion_result)

    try:
        vector = await embedding_task
    except BaseException as embedding_result:
        # If the embedding fails (including CancelledError), we log it and continue without vector
        logger.error("Embedding generation failed, vector will not be cached", exc_info=embedding_result)
        vector = []

    elapsed_ms = (time.perf_counter() * 1000) - start_ms
    provider = "ollama" if fallback_used else _extract_provider(request.model)

    # ── Map LiteLLM response → our Pydantic model ──
    usage_obj = getattr(response, "usage", None)
    
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
            prompt_tokens=getattr(usage_obj, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage_obj, "completion_tokens", 0) or 0,
            total_tokens=getattr(usage_obj, "total_tokens", 0) or 0,
        ),
        trace_id=trace_id,
    )

    # Classify toxicity on the generated response content
    response_content = " ".join([c.message.content for c in result.choices if c.message and c.message.content])
    toxicity_score, is_toxic = classify_toxicity(response_content)

    logger.info(
        "Completion returned",
        extra={
            "model": result.model,
            "provider": provider,
            "latency_ms": round(elapsed_ms, 1),
            "status_code": 200,
            "has_pii_redacted": has_pii_redacted_any,
            "toxicity_score": toxicity_score,
            "is_toxic": is_toxic,
        },
    )

    # ── W1-C4: Write telemetry row to ClickHouse ──
    # Uses the same trace_id from X-Request-ID — no second UUID.
    await write_metrics(
        trace_id=trace_id,
        app_id=app_id,
        model_requested=request.model,
        model_used=result.model,
        provider=provider,
        total_duration_ms=round(elapsed_ms, 1),
        status_code=200,
        prompt_tokens=result.usage.prompt_tokens,
        completion_tokens=result.usage.completion_tokens,
    )

    # ── Cache Write Path ──
    # Skip cache write entirely for fallback responses. 
    # Fallback models are degraded by nature; we don't want to serve
    # their outputs long after the primary provider has recovered.
    if not fallback_used:
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

