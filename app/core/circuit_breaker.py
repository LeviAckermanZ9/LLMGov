import time
from enum import Enum

class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

class CircuitBreaker:
    """
    Standalone Circuit Breaker for handling provider failure cascading.
    State machine: CLOSED -> (failures > threshold) -> OPEN -> (timeout) -> HALF_OPEN
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 30.0):
        self.state: CircuitBreakerState = CircuitBreakerState.CLOSED
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: float = 0.0
        self._half_open_probe_in_flight: bool = False

    def allow_request(self) -> bool:
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has elapsed using monotonic time
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                self._half_open_probe_in_flight = True
                return True
            return False

        if self.state == CircuitBreakerState.HALF_OPEN:
            if self._half_open_probe_in_flight:
                # A probe is already in-flight — route this request to fallback
                return False
            self._half_open_probe_in_flight = True
            return True
            
        return False

    def record_failure(self) -> None:
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Any failure during half-open immediately trips the breaker again
            self._half_open_probe_in_flight = False
            self.state = CircuitBreakerState.OPEN
            self.last_failure_time = time.monotonic()
            return

        if self.state == CircuitBreakerState.CLOSED:
            self.failure_count += 1
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                self.last_failure_time = time.monotonic()

    def record_success(self) -> None:
        if self.state == CircuitBreakerState.HALF_OPEN:
            self._half_open_probe_in_flight = False
            self.state = CircuitBreakerState.CLOSED
        
        if self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def release_half_open_probe(self) -> None:
        """Safety net: reset the probe-in-flight flag without changing breaker state.

        Called from a finally block in the request path so that an unexpected
        exception (one not caught by record_failure) can't permanently lock
        the breaker into rejecting all HALF_OPEN probes.

        Idempotent — safe to call even if record_success/record_failure
        already reset the flag.
        """
        self._half_open_probe_in_flight = False
