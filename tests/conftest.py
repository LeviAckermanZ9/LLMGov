import pytest
from unittest.mock import patch, AsyncMock

@pytest.fixture(autouse=True)
def mock_auth_and_rate_limit_globally(request):
    # If the test is in test_auth_rate_limit_wiring.py, skip global mocking
    # so that the test-level patches have full control without interference.
    if "test_auth_rate_limit_wiring" in request.module.__name__:
        yield
        return

    with patch("app.api.completions.authenticate_api_key", AsyncMock(return_value="default")), \
         patch("app.api.completions.check_rate_limit", AsyncMock(return_value=True)):
        yield
