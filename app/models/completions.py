"""
LLMGov — Chat Completion Request / Response Models

OpenAI-compatible Pydantic v2 models for the /v1/chat/completions
endpoint. These validate the gateway's HTTP contract — they do NOT
validate downstream LLM output (tool-call schema adherence, etc.),
which is a separate concern handled by the eval harness (§5.7).
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────
# Request
# ──────────────────────────────────────────────

class ChatMessage(BaseModel):
    """A single message in the conversation."""
    role: str = Field(..., description="One of: system, user, assistant, tool")
    content: str = Field(..., description="The text content of the message")


class ChatCompletionRequest(BaseModel):
    """OpenAI-compatible chat completion request body."""
    model: str = Field(
        ...,
        description="LiteLLM model identifier (e.g. 'gemini/gemini-2.5-flash')",
    )
    messages: list[ChatMessage] = Field(
        ...,
        min_length=1,
        description="Conversation history — at least one message required",
    )
    temperature: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=2.0,
        description="Sampling temperature (0.0–2.0)",
    )
    max_tokens: Optional[int] = Field(
        default=None,
        gt=0,
        description="Maximum tokens in the completion",
    )
    stream: bool = Field(
        default=False,
        description="Streaming not yet supported — must be false",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "model": "gemini/gemini-2.5-flash",
                    "messages": [
                        {"role": "user", "content": "Say hello in one sentence."}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 100,
                    "stream": False,
                }
            ]
        }
    }


# ──────────────────────────────────────────────
# Response
# ──────────────────────────────────────────────

class UsageInfo(BaseModel):
    """Token usage statistics."""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class ChoiceMessage(BaseModel):
    """The assistant's reply in a choice."""
    role: str = "assistant"
    content: Optional[str] = None


class Choice(BaseModel):
    """A single completion choice."""
    index: int = 0
    message: ChoiceMessage
    finish_reason: Optional[str] = None


class ChatCompletionResponse(BaseModel):
    """OpenAI-compatible chat completion response."""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: list[Choice]
    usage: UsageInfo
    # LLMGov extension: trace_id for end-to-end correlation
    trace_id: Optional[str] = None
