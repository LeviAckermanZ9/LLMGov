import pytest
from fastapi import FastAPI
from redis.asyncio import Redis

from app.core.redis import get_redis, redis_lifespan

# Mark this as an integration test requiring a live Redis container
pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_redis_lifespan_initializes_and_closes_connection():
    """
    Integration test for the Redis lifespan context manager.
    Verifies that it connects to the live Redis instance, allows
    commands (ping), and cleans up the connection afterwards.
    """
    app = FastAPI()

    # Before lifespan, get_redis should raise RuntimeError
    with pytest.raises(RuntimeError, match="Redis client is not initialized"):
        get_redis()

    # Enter lifespan context
    async with redis_lifespan(app):
        client = get_redis()
        assert isinstance(client, Redis)
        
        # Verify the connection is viable by pinging the live Redis instance
        response = await client.ping()
        assert response is True

    # After lifespan, the client should be cleaned up (None) and raise again
    with pytest.raises(RuntimeError, match="Redis client is not initialized"):
        get_redis()
