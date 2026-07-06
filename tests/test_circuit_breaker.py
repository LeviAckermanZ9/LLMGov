import pytest
from unittest.mock import patch
from app.core.circuit_breaker import CircuitBreaker, CircuitBreakerState

@pytest.fixture
def cb():
    return CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

def test_initial_state_closed(cb):
    assert cb.state == CircuitBreakerState.CLOSED
    assert cb.allow_request() is True

def test_trips_open_on_threshold(cb):
    with patch("time.monotonic", return_value=100.0):
        # 1st failure
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        
        # 2nd failure
        cb.record_failure()
        assert cb.state == CircuitBreakerState.CLOSED
        
        # 3rd failure (hits threshold = 3)
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.last_failure_time == 100.0

def test_rejects_requests_while_open(cb):
    with patch("time.monotonic", return_value=100.0):
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN

    # Just 1 second later
    with patch("time.monotonic", return_value=101.0):
        assert cb.allow_request() is False
        assert cb.state == CircuitBreakerState.OPEN

def test_transitions_to_half_open_after_timeout(cb):
    with patch("time.monotonic", return_value=100.0):
        for _ in range(3):
            cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        
    # Exactly recovery_timeout later
    with patch("time.monotonic", return_value=110.0):
        assert cb.allow_request() is True
        assert cb.state == CircuitBreakerState.HALF_OPEN

def test_half_open_success_recovers_to_closed(cb):
    with patch("time.monotonic", return_value=100.0):
        for _ in range(3):
            cb.record_failure()

    with patch("time.monotonic", return_value=110.0):
        cb.allow_request()  # Transitions to HALF_OPEN
        
        cb.record_success() # Should recover
        assert cb.state == CircuitBreakerState.CLOSED
        assert cb.failure_count == 0

def test_half_open_failure_retrips_immediately(cb):
    with patch("time.monotonic", return_value=100.0):
        for _ in range(3):
            cb.record_failure()

    with patch("time.monotonic", return_value=110.0):
        cb.allow_request()  # Transitions to HALF_OPEN
        
    # Now it fails immediately
    with patch("time.monotonic", return_value=111.0):
        cb.record_failure()
        assert cb.state == CircuitBreakerState.OPEN
        assert cb.last_failure_time == 111.0
        
        # Still open immediately after retrip
        assert cb.allow_request() is False
