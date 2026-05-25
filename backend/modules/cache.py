"""
Simple TTL in-memory cache shared across modules.

Three named caches are exported:
  history_cache  — for /api/v1/history responses
  report_cache   — for /api/v1/report/{id} responses
  evidence_cache — for /api/v1/report/{id}/evidence responses

All caches use a 60-second TTL by default.
"""

import time
import threading
from typing import Any, Dict, Optional

_DEFAULT_TTL = 60  # seconds


class TTLCache:
    """Minimal thread-safe TTL cache."""

    def __init__(self, ttl: int = _DEFAULT_TTL, name: str = "cache"):
        self._ttl = ttl
        self._name = name
        self._store: Dict[str, Any] = {}
        self._ts: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._store and (time.monotonic() - self._ts[key]) < self._ttl:
                return self._store[key]
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._store[key] = value
            self._ts[key] = time.monotonic()

    def invalidate(self, key: str = None) -> None:
        with self._lock:
            if key:
                self._store.pop(key, None)
                self._ts.pop(key, None)
            else:
                self._store.clear()
                self._ts.clear()

    def __repr__(self) -> str:
        return f"TTLCache(name={self._name!r}, ttl={self._ttl}s, entries={len(self._store)})"


# Named singletons used by audio_analysis_routes.py
history_cache  = TTLCache(ttl=60,  name="history")
report_cache   = TTLCache(ttl=120, name="report")
evidence_cache = TTLCache(ttl=120, name="evidence")
