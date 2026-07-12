"""
LLMGov — Application Settings

Centralized configuration via pydantic-settings.
All values are overridable through environment variables or a .env file.
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Gateway configuration, loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # ── Gateway ──
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    log_level: str = "info"

    # ── Infrastructure ──
    redis_url: str = "redis://localhost:6379"
    clickhouse_url: str = "http://localhost:8123"
    clickhouse_password: str = "llmgov_dev"

    # ── LLM Provider Keys ──
    gemini_api_key: str = ""
    openai_api_key: str = ""
    anthropic_api_key: str = ""

    # ── Default Model (single-provider path, W1-C3) ──
    default_model: str = "gemini/gemini-2.5-flash"


settings = Settings()

# ── Export API keys to os.environ for litellm ──
# litellm reads keys from os.environ, not Python variables.
# pydantic-settings loads .env → Python attrs, so we bridge the gap here
# at module-load time (when settings is first imported), ensuring every
# module that uses litellm sees the key regardless of import order.
if settings.gemini_api_key:
    os.environ.setdefault("GEMINI_API_KEY", settings.gemini_api_key)
