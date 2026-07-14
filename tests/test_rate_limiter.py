import pytest
import time
from typing import Any, Awaitable, cast
from unittest.mock import patch, MagicMock, AsyncMock
from redis.exceptions import ConnectionError

from app.core.rate_limiter import (
    check_rate_limit,
    RateLimiterUnavailableError,
)
from app.core.redis import redis_lifespan, get_redis
from fastapi import FastAPI

@pytest.mark.asyncio
async def test_rate_limiter_allow_mocked():
    """Verify rate limiter allows request when count is below limit (mocked)."""
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[5, True])
    mock_redis.pipeline.return_value.__aenter__.return_value = mock_pipe
    
    with patch("app.core.rate_limiter.get_redis", return_value=mock_redis):
        allowed = await check_rate_limit("app_test", limit=10, window_seconds=60)
        assert allowed is True
        mock_pipe.incr.assert_called_once()
        mock_pipe.expire.assert_called_once()

@pytest.mark.asyncio
async def test_rate_limiter_deny_mocked():
    """Verify rate limiter denies request when count exceeds limit (mocked)."""
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(return_value=[11, True])
    mock_redis.pipeline.return_value.__aenter__.return_value = mock_pipe
    
    with patch("app.core.rate_limiter.get_redis", return_value=mock_redis):
        allowed = await check_rate_limit("app_test", limit=10, window_seconds=60)
        assert allowed is False

@pytest.mark.asyncio
async def test_rate_limiter_connection_failure_mocked():
    """Verify that Redis pipeline errors propagate as RateLimiterUnavailableError (mocked)."""
    mock_redis = MagicMock()
    mock_redis.pipeline.side_effect = ConnectionError("Timeout contacting Redis")
    
    with patch("app.core.rate_limiter.get_redis", return_value=mock_redis):
        with pytest.raises(RateLimiterUnavailableError, match="Rate limiter service is temporarily unavailable"):
            await check_rate_limit("app_test", limit=10)

@pytest.mark.asyncio
async def test_rate_limiter_execute_failure_mocked():
    """Verify that Redis pipeline execution failures propagate as RateLimiterUnavailableError (mocked)."""
    mock_redis = MagicMock()
    mock_pipe = MagicMock()
    mock_pipe.execute = AsyncMock(side_effect=ConnectionError("Execute failed"))
    mock_redis.pipeline.return_value.__aenter__.return_value = mock_pipe
    
    with patch("app.core.rate_limiter.get_redis", return_value=mock_redis):
        with pytest.raises(RateLimiterUnavailableError, match="Rate limiter service is temporarily unavailable"):
            await check_rate_limit("app_test", limit=10)

@pytest.mark.asyncio
@pytest.mark.integration
async def test_rate_limiter_live_redis_integration():
    """
    Live integration test against localhost Redis.
    Verifies fixed window incrementing, limiting, and key expiration.
    """
    app = FastAPI()
    async with redis_lifespan(app):
        redis_client = get_redis()
        
        app_id = "live_limiter_app"
        window_seconds = 10  # short window for fast testing
        current_time = int(time.time())
        window_start = (current_time // window_seconds) * window_seconds
        redis_key = f"llmgov:ratelimit:{app_id}:{window_start}"
        
        # 1. Clean up key
        await cast(Awaitable[Any], redis_client.delete(redis_key))
        
        try:
            # 2. Check rate limit under limit (max 2 requests allowed)
            res1 = await check_rate_limit(app_id, limit=2, window_seconds=window_seconds)
            assert res1 is True
            
            res2 = await check_rate_limit(app_id, limit=2, window_seconds=window_seconds)
            assert res2 is True
            
            # 3. Check rate limit over limit
            res3 = await check_rate_limit(app_id, limit=2, window_seconds=window_seconds)
            assert res3 is False
            
            # 4. Check that expiration TTL was set
            ttl = await cast(Awaitable[Any], redis_client.ttl(redis_key))
            assert 0 < ttl <= window_seconds * 2
        finally:
            await cast(Awaitable[Any], redis_client.delete(redis_key))
