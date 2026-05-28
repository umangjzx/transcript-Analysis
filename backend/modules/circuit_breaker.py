"""
Circuit Breaker for external service calls (Ollama, S3, etc.).

Implements the circuit breaker pattern to prevent cascading failures
when external services are unavailable.

States:
- CLOSED:    Normal operation, requests pass through.
- OPEN:      Service is down, requests fail immediately without calling the service.
- HALF_OPEN: After cooldown, allow one test request to check if service recovered.

Configuration via environment:
- CIRCUIT_BREAKER_FAILURE_THRESHOLD: failures before opening (default: 5)
- CIRCUIT_BREAKER_RECOVERY_TIMEOUT: seconds before half-open (default: 60)
- CIRCUIT_BREAKER_SUCCESS_THRESHOLD: successes in half-open to close (default: 2)
"""

import time
import logging
import threading
from enum import Enum
from typing import Callable, Any, Optional, Dict
from functools import wraps

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Raised when the circuit is open and the call is rejected."""

    def __init__(self, service_name: str, time_until_retry: float):
        self.service_name = service_name
        self.time_until_retry = time_until_retry
        super().__init__(
            f"Circuit breaker OPEN for '{service_name}'. "
            f"Retry in {time_until_retry:.0f}s."
        )


class CircuitBreaker:
    """
    Thread-safe circuit breaker for external service calls.

    Usage:
        ollama_breaker = CircuitBreaker("ollama", failure_threshold=3, recovery_timeout=30)

        try:
            result = ollama_breaker.call(lambda: ollama.chat(...))
        except CircuitBreakerError:
            # Service is down, use fallback
            result = fallback_value
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        success_threshold: int = 2,
        excluded_exceptions: tuple = (),
    ):
        """
        Args:
            name: Service name for logging.
            failure_threshold: Number of failures before opening the circuit.
            recovery_timeout: Seconds to wait before trying half-open.
            success_threshold: Successes needed in half-open to close circuit.
            excluded_exceptions: Exception types that don't count as failures
                                 (e.g., validation errors from the caller).
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold
        self.excluded_exceptions = excluded_exceptions

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                elapsed = time.time() - self._last_failure_time
                if elapsed >= self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._success_count = 0
                    logger.info(
                        f"Circuit breaker '{self.name}': OPEN → HALF_OPEN "
                        f"(recovery timeout elapsed)"
                    )
            return self._state

    def call(self, func: Callable[[], Any], *args, **kwargs) -> Any:
        """
        Execute func through the circuit breaker.

        Args:
            func: Callable to execute (should be a zero-arg lambda or partial).

        Returns:
            Result of func() on success.

        Raises:
            CircuitBreakerError: If circuit is OPEN.
            Exception: Original exception from func if circuit is CLOSED/HALF_OPEN.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            time_until_retry = self.recovery_timeout - (time.time() - self._last_failure_time)
            raise CircuitBreakerError(self.name, max(0, time_until_retry))

        try:
            result = func()
            self._on_success()
            return result
        except Exception as e:
            if isinstance(e, self.excluded_exceptions):
                # Don't count excluded exceptions as failures
                raise
            self._on_failure(e)
            raise

    def _on_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._success_count = 0
                    logger.info(
                        f"Circuit breaker '{self.name}': HALF_OPEN → CLOSED "
                        f"(service recovered)"
                    )
            else:
                # Reset failure count on success in CLOSED state
                self._failure_count = 0

    def _on_failure(self, error: Exception):
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately re-opens
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}': HALF_OPEN → OPEN "
                    f"(test request failed: {error})"
                )
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker '{self.name}': CLOSED → OPEN "
                    f"(threshold {self.failure_threshold} reached: {error})"
                )

    def reset(self):
        """Manually reset the circuit breaker to CLOSED state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            logger.info(f"Circuit breaker '{self.name}': manually reset to CLOSED")

    def get_status(self) -> Dict[str, Any]:
        """Return current circuit breaker status for health checks."""
        with self._lock:
            return {
                "name": self.name,
                "state": self._state.value,
                "failure_count": self._failure_count,
                "failure_threshold": self.failure_threshold,
                "recovery_timeout": self.recovery_timeout,
                "last_failure": self._last_failure_time,
            }


# ── Global circuit breaker instances ──────────────────────────────────────────

import os

_failure_threshold = int(os.getenv("CIRCUIT_BREAKER_FAILURE_THRESHOLD", "5"))
_recovery_timeout = float(os.getenv("CIRCUIT_BREAKER_RECOVERY_TIMEOUT", "60"))
_success_threshold = int(os.getenv("CIRCUIT_BREAKER_SUCCESS_THRESHOLD", "2"))

ollama_breaker = CircuitBreaker(
    name="ollama",
    failure_threshold=_failure_threshold,
    recovery_timeout=_recovery_timeout,
    success_threshold=_success_threshold,
)

s3_breaker = CircuitBreaker(
    name="s3",
    failure_threshold=_failure_threshold,
    recovery_timeout=_recovery_timeout * 2,  # S3 gets longer recovery
    success_threshold=_success_threshold,
)


def circuit_breaker_decorator(breaker: CircuitBreaker):
    """Decorator to wrap a function with a circuit breaker."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(lambda: func(*args, **kwargs))
        wrapper.circuit_breaker = breaker
        return wrapper
    return decorator
