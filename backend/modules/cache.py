"""
Redis-backed TTL cache shared across modules.

Falls back to in-memory TTL cache if Redis is unavailable.

Three named caches are exported:
  history_cache  — for /api/v1/history responses
  report_cache   — for /api/v1/report/{id} responses
  evidence_cache — for /api/v1/report/{id}/evidence responses

All caches use a 60-second TTL by default.
"""

import json
import logging
import os
import time
import threading
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_DEFAULT_TTL = 60  # seconds

# ── Redis connection ──────────────────────────────────────────────────────────

_redis_client = None
_redis_available = False


def _get_redis():
    """Lazy Redis connection — returns None if unavailable."""
    global _redis_client, _redis_available
    if _redis_client is not None:
        return _redis_client if _redis_available else None
    try:
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        _redis_available = True
        logger.info(f"Redis cache connected: {url}")
        return _redis_client
    except Exception as e:
        logger.warning(f"Redis unavailable, falling back to in-memory cache: {e}")
        _redis_available = False
        return None


# ── TTL Cache (Redis-backed with in-memory fallback) ──────────────────────────

class TTLCache:
    """Thread-safe TTL cache backed by Redis, with in-memory fallback."""

    def __init__(self, ttl: int = _DEFAULT_TTL, name: str = "cache"):
        self._ttl = ttl
        self._name = name
        # In-memory fallback store
        self._store: Dict[str, Any] = {}
        self._ts: Dict[str, float] = {}
        self._lock = threading.Lock()

    def _redis_key(self, key: str) -> str:
        return f"cache:{self._name}:{key}"

    def get(self, key: str) -> Optional[Any]:
        r = _get_redis()
        if r is not None:
            try:
                raw = r.get(self._redis_key(key))
                if raw is not None:
                    return json.loads(raw)
                return None
            except Exception:
                pass  # fall through to in-memory

        with self._lock:
            if key in self._store and (time.monotonic() - self._ts[key]) < self._ttl:
                return self._store[key]
            return None

    def set(self, key: str, value: Any) -> None:
        r = _get_redis()
        if r is not None:
            try:
                r.setex(self._redis_key(key), self._ttl, json.dumps(value, default=str))
                return
            except Exception:
                pass  # fall through to in-memory

        with self._lock:
            self._store[key] = value
            self._ts[key] = time.monotonic()

    def invalidate(self, key: str = None) -> None:
        r = _get_redis()
        if r is not None:
            try:
                if key:
                    r.delete(self._redis_key(key))
                else:
                    # Delete all keys for this cache namespace
                    pattern = f"cache:{self._name}:*"
                    cursor = 0
                    while True:
                        cursor, keys = r.scan(cursor, match=pattern, count=100)
                        if keys:
                            r.delete(*keys)
                        if cursor == 0:
                            break
                return
            except Exception:
                pass  # fall through to in-memory

        with self._lock:
            if key:
                self._store.pop(key, None)
                self._ts.pop(key, None)
            else:
                self._store.clear()
                self._ts.clear()

    def __repr__(self) -> str:
        return f"TTLCache(name={self._name!r}, ttl={self._ttl}s, redis={_redis_available})"


# Named singletons used by audio_analysis_routes.py and app.py
history_cache  = TTLCache(ttl=60,  name="history")
report_cache   = TTLCache(ttl=120, name="report")
evidence_cache = TTLCache(ttl=120, name="evidence")
