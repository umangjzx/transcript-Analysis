"""
Tests for the rate limiter — bounded memory, Redis fallback, and middleware behavior.
"""

import time
import pytest
from middleware.rate_limiter import (
    _check_rate_limit_memory,
    _memory_store,
    _memory_lock,
    _MAX_MEMORY_KEYS,
)


class TestInMemoryRateLimiter:
    def setup_method(self):
        """Clear the in-memory store before each test."""
        with _memory_lock:
            _memory_store.clear()

    def test_allows_within_limit(self):
        allowed, remaining = _check_rate_limit_memory("test:ip1", 5, 60)
        assert allowed is True
        assert remaining == 4

    def test_blocks_after_limit(self):
        for _ in range(5):
            _check_rate_limit_memory("test:ip2", 5, 60)
        allowed, remaining = _check_rate_limit_memory("test:ip2", 5, 60)
        assert allowed is False
        assert remaining == 0

    def test_window_expiry(self):
        # Use a 1-second window
        for _ in range(3):
            _check_rate_limit_memory("test:ip3", 3, 1)

        # Should be blocked
        allowed, _ = _check_rate_limit_memory("test:ip3", 3, 1)
        assert allowed is False

        # Wait for window to expire
        time.sleep(1.1)

        # Should be allowed again
        allowed, remaining = _check_rate_limit_memory("test:ip3", 3, 1)
        assert allowed is True
        assert remaining == 2

    def test_bounded_memory(self):
        """Ensure the store doesn't grow beyond _MAX_MEMORY_KEYS."""
        for i in range(_MAX_MEMORY_KEYS + 100):
            _check_rate_limit_memory(f"key:{i}", 10, 60)

        with _memory_lock:
            assert len(_memory_store) <= _MAX_MEMORY_KEYS

    def test_thread_safety(self):
        """Basic concurrency smoke test."""
        import threading

        results = []

        def hit():
            allowed, _ = _check_rate_limit_memory("concurrent:ip", 100, 60)
            results.append(allowed)

        threads = [threading.Thread(target=hit) for _ in range(50)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All 50 should succeed (limit is 100)
        assert all(results)
        assert len(results) == 50


class TestRateLimitMiddleware:
    def test_login_rate_limit(self, client):
        """Login endpoint should be rate-limited to 5/min."""
        for i in range(5):
            client.post("/auth/login", json={"username": "x", "password": "x"})

        response = client.post("/auth/login", json={"username": "x", "password": "x"})
        assert response.status_code == 429
        assert "TooManyRequests" in response.json()["error"]
        assert "Retry-After" in response.headers

    def test_non_rate_limited_path(self, client):
        """GET /health should not be rate-limited."""
        for _ in range(20):
            response = client.get("/health")
            assert response.status_code == 200
