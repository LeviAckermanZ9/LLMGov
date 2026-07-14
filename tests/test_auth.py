import pytest
import hashlib
from typing import Any, Awaitable, cast
from unittest.mock import patch, MagicMock, AsyncMock
from redis.exceptions import ConnectionError

from app.core.auth import (
    authenticate_api_key,
    InvalidAPIKeyError,
    AuthServiceUnavailableError,
)
from app.core.redis import redis_lifespan, get_redis
from fastapi import FastAPI

@pytest.mark.asyncio
async def test_auth_success_mocked():
    """Verify that a valid, registered key returns the correct app_id (mocked)."""
    mock_redis = MagicMock()
    mock_redis.hget = AsyncMock(return_value="mock_app")
    
    with patch("app.core.auth.get_redis", return_value=mock_redis):
        app_id = await authenticate_api_key("llmgov_sk_test_mock")
        assert app_id == "mock_app"
        
        # Verify the lookup key was the SHA-256 hash of the raw key
        expected_hash = hashlib.sha256(b"llmgov_sk_test_mock").hexdigest()
        mock_redis.hget.assert_called_once_with(f"llmgov:auth:{expected_hash}", "app_id")

@pytest.mark.asyncio
async def test_auth_invalid_key_mocked():
    """Verify that an unregistered key raises InvalidAPIKeyError (mocked)."""
    mock_redis = MagicMock()
    mock_redis.hget = AsyncMock(return_value=None)  # Key not found
    
    with patch("app.core.auth.get_redis", return_value=mock_redis):
        with pytest.raises(InvalidAPIKeyError, match="Invalid or unregistered API key"):
            await authenticate_api_key("llmgov_sk_invalid")

@pytest.mark.asyncio
async def test_auth_empty_key():
    """Verify that an empty key raises InvalidAPIKeyError immediately without querying Redis."""
    with pytest.raises(InvalidAPIKeyError, match="API key cannot be empty"):
        await authenticate_api_key("")

@pytest.mark.asyncio
async def test_auth_connection_failure_mocked():
    """Verify that Redis connection errors propagate as AuthServiceUnavailableError (mocked)."""
    mock_redis = MagicMock()
    mock_redis.hget = AsyncMock(side_effect=ConnectionError("Connection refused"))
    
    with patch("app.core.auth.get_redis", return_value=mock_redis):
        with pytest.raises(AuthServiceUnavailableError, match="Authentication service is temporarily unavailable"):
            await authenticate_api_key("llmgov_sk_test_mock")

@pytest.mark.asyncio
@pytest.mark.integration
async def test_auth_live_redis_integration():
    """
    Live integration test against localhost Redis.
    Seeds a non-trivial random API key hash and asserts authentication behaves correctly.
    """
    app = FastAPI()
    async with redis_lifespan(app):
        redis_client = get_redis()
        
        # Test key and its hash
        raw_key = "llmgov_sk_dev_abc123"
        key_hash = "d3ac38388b2838fbaf50d382d4d88ca0d71f189a8e10f71c1f5dc278adf7aa34"
        redis_key = f"llmgov:auth:{key_hash}"
        
        # 1. Clean up potential leftover keys
        await cast(Awaitable[Any], redis_client.delete(redis_key))
        
        # 2. Assert query on unregistered key raises InvalidAPIKeyError
        with pytest.raises(InvalidAPIKeyError, match="Invalid or unregistered API key"):
            await authenticate_api_key(raw_key)
            
        # 3. Seed the key manually in Redis
        await cast(Awaitable[Any], redis_client.hset(redis_key, "app_id", "live_test_app"))
        
        try:
            # 4. Verify authenticate_api_key successfully retrieves and returns the app_id
            app_id = await authenticate_api_key(raw_key)
            assert app_id == "live_test_app"
        finally:
            # Clean up key from Redis
            await cast(Awaitable[Any], redis_client.delete(redis_key))
