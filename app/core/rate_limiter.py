"""
LLMGov — Rate Limiting Service
"""

import logging
import time
from typing import Any, Awaitable, cast
from redis.exceptions import RedisError
from app.core.redis import get_redis

logger = logging.getLogger(__name__)


class RateLimiterUnavailableError(Exception):
    """Raised when the Redis connection fails during rate limiting checks."""
    pass


async def check_rate_limit(app_id: str, limit: int = 60, window_seconds: int = 60) -> bool:
    """
    Check if the requests for the given app_id exceed the specified limit in the current window.
    
    1. Computes the current window_start.
    2. Builds the Redis key `llmgov:ratelimit:[app_id]:[window_start]`.
    3. Atomically increments the key and sets an expiration (window_seconds * 2) via pipeline.
    4. Raises RateLimiterUnavailableError if Redis is unreachable.
    
    Returns True if allowed, False if denied (rate limit exceeded).
    """
    if not app_id:
        return False
        
    current_time = int(time.time())
    window_start = (current_time // window_seconds) * window_seconds
    redis_key = f"llmgov:ratelimit:{app_id}:{window_start}"
    
    try:
        redis_client = get_redis()
        async with redis_client.pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds * 2)
            execute_fut = pipe.execute()
            results = await cast(Awaitable[Any], execute_fut)
    except RedisError as e:
        logger.error("Redis error during rate limiting check", exc_info=True)
        raise RateLimiterUnavailableError("Rate limiter service is temporarily unavailable") from e
    except Exception as e:
        logger.error("Unexpected error during rate limiting check", exc_info=True)
        raise RateLimiterUnavailableError("Rate limiter service is temporarily unavailable") from e
        
    current_count = results[0]
    if current_count > limit:
        return False # Deny
        
    return True # Allow
