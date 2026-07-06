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

    def allow_request(self) -> bool:
        if self.state == CircuitBreakerState.CLOSED:
            return True

        if self.state == CircuitBreakerState.OPEN:
            # Check if recovery timeout has elapsed using monotonic time
            if time.monotonic() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitBreakerState.HALF_OPEN
                return True
            return False

        if self.state == CircuitBreakerState.HALF_OPEN:
            return True
            
        return False

    def record_failure(self) -> None:
        if self.state == CircuitBreakerState.HALF_OPEN:
            # Any failure during half-open immediately trips the breaker again
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
            self.state = CircuitBreakerState.CLOSED
        
        if self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0
