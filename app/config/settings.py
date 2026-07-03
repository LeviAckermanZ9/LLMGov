"""
LLMGov — Application Settings

Centralized configuration via pydantic-settings.
All values are overridable through environment variables or a .env file.
"""

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

    # ── LLM Provider Keys (wired in W1-C3) ──
    openai_api_key: str = ""
    anthropic_api_key: str = ""


settings = Settings()
