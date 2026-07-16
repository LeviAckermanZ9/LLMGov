import pytest
import hashlib
from unittest.mock import patch, AsyncMock
import redis
from app.config.settings import settings

@pytest.fixture
def mock_auth_and_rate_limit_globally(request):
    # If the test is in test_auth_rate_limit_wiring.py, skip global mocking
    # so that the test-level patches have full control without interference.
    if "test_auth_rate_limit_wiring" in request.module.__name__:
        yield
        return

    with patch("app.api.completions.authenticate_api_key", AsyncMock(return_value="default")), \
         patch("app.api.completions.check_rate_limit", AsyncMock(return_value=True)):
        yield

@pytest.fixture
def auth_headers():
    """
    Test helper fixture that seeds a valid API key in the live Redis instance,
    and returns the Authorization header dictionary to use in HTTP requests.
    Exercises the actual auth and rate limit paths.
    """
    raw_key = "llmgov_sk_test_fixture_key"
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    redis_key = f"llmgov:auth:{key_hash}"
    app_id = "test_app_fixture"
    
    # Establish connection to live Redis and seed the key
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    redis_client.hset(redis_key, "app_id", app_id)
    
    # Clean up any potential leftover rate-limit keys for this app_id
    for rkey in redis_client.scan_iter(f"llmgov:ratelimit:{app_id}:*"):
        redis_client.delete(rkey)
        
    try:
        yield {"Authorization": f"Bearer {raw_key}"}
    finally:
        # Teardown: clear the auth hash key
        redis_client.delete(redis_key)
        # Teardown: scan and clear all rate-limit counter keys for this app_id
        for rkey in redis_client.scan_iter(f"llmgov:ratelimit:{app_id}:*"):
            redis_client.delete(rkey)
        redis_client.close()

