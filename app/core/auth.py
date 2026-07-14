"""
LLMGov — Authentication Service
"""

import hashlib
import logging
from typing import Any, Awaitable, cast
from redis.exceptions import RedisError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class InvalidAPIKeyError(Exception):
    """Raised when the provided API key is invalid or unregistered."""
    pass


class AuthServiceUnavailableError(Exception):
    """Raised when the Redis connection fails during authentication."""
    pass


async def authenticate_api_key(raw_key: str) -> str:
    """
    Authenticate the raw API key.
    
    1. Computes the SHA-256 hash of the raw key.
    2. Queries Redis keyspace `llmgov:auth:[api_key_hash]` using HGET to retrieve 'app_id'.
    3. Raises AuthServiceUnavailableError if Redis is unreachable.
    4. Raises InvalidAPIKeyError if key is invalid or has no app_id.
    
    Returns the associated app_id (str) on success.
    """
    if not raw_key:
        raise InvalidAPIKeyError("API key cannot be empty")
        
    api_key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    redis_key = f"llmgov:auth:{api_key_hash}"
    
    try:
        redis_client = get_redis()
        # Cast the coroutine/value to Awaitable[Any] to satisfy Pyright
        app_id_fut = redis_client.hget(redis_key, "app_id")
        app_id = await cast(Awaitable[Any], app_id_fut)
    except RedisError as e:
        logger.error("Redis error during API key authentication", exc_info=True)
        raise AuthServiceUnavailableError("Authentication service is temporarily unavailable") from e
    except Exception as e:
        logger.error("Unexpected error during API key authentication", exc_info=True)
        raise AuthServiceUnavailableError("Authentication service is temporarily unavailable") from e
        
    if not app_id:
        raise InvalidAPIKeyError("Invalid or unregistered API key")
        
    return str(app_id)
