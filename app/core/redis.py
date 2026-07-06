"""
LLMGov — Redis Connection Management
"""

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

import redis.asyncio as redis
from fastapi import FastAPI

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Global Redis client instance
_redis_client: Optional[redis.Redis] = None


def get_redis() -> redis.Redis:
    """
    Retrieve the active Redis client.
    Raises RuntimeError if the client has not been initialized.
    """
    if _redis_client is None:
        raise RuntimeError("Redis client is not initialized. Ensure lifespan is active.")
    return _redis_client


@asynccontextmanager
async def redis_lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Standalone FastAPI lifespan hook for Redis.
    Initializes the async connection pool on startup and closes it on shutdown.
    Not yet wired into the main application.
    """
    global _redis_client

    logger.info("Initializing Redis connection pool")
    # Initialize from the URL configured in settings
    # decode_responses=True ensures we get str instead of bytes
    _redis_client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
    )
    
    try:
        # Ping to ensure connection is actually viable during startup
        await _redis_client.ping()
        logger.info("Redis connection established successfully")
        yield
    finally:
        logger.info("Closing Redis connection pool")
        if _redis_client:
            await _redis_client.aclose()
            _redis_client = None
