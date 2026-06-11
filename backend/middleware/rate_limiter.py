"""
Redis-backed rate limiter middleware for FastAPI.

Limits:
  - login:        5 requests/minute
  - upload:       10 requests/minute
  - chat:         30 requests/minute
  - google_drive: 30 requests/minute  (only actual Drive API calls: /files, /import)
  - drive_meta:   120 requests/minute (auth-url, status, watcher control — lightweight)

Falls back to in-memory sliding window if Redis is unavailable.
"""

import os
import time
import logging
from typing import Dict, Tuple

from fastapi import Request, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Rate limit configuration: (max_requests, window_seconds)
RATE_LIMITS: Dict[str, Tuple[int, int]] = {
    "login":        (5,   60),   # 5 requests per minute
    "upload":       (10,  60),   # 10 requests per minute
    "chat":         (30,  60),   # 30 requests per minute
    "google_drive": (60,  120),  # 60 req/2min — actual Drive API calls (/files, /import)
    "drive_meta":   (120, 60),   # 120 req/min — auth-url, status, watcher control (cheap)
}

# Path → rate limit category mapping
_PATH_CATEGORIES = {
    "/auth/login":                              "login",
    "/analyze":                                 "upload",
    "/analyze/video":                           "upload",
    "/analyze/transcript":                      "upload",
    "/analyze/batch":                           "upload",
    "/api/v1/analyze":                          "upload",
    "/api/v1/analyze/video":                    "upload",
    "/api/v1/analyze/transcript":               "upload",
    "/api/v1/analyze/batch":                    "upload",
    # Actual Drive API calls — rate-limited to protect Google quota
    "/api/v1/google-drive/import":              "google_drive",
    "/api/v1/google-drive/files":               "google_drive",
    # Lightweight metadata / auth endpoints — generous limit so they never block the UI
    "/api/v1/google-drive/auth-url":            "drive_meta",
    "/api/v1/google-drive/status":              "drive_meta",
    "/api/v1/google-drive/logout":              "drive_meta",
    "/api/v1/google-drive/callback":            "drive_meta",
    "/api/v1/google-drive/watcher/start":       "drive_meta",
    "/api/v1/google-drive/watcher/stop":        "drive_meta",
    "/api/v1/google-drive/watcher/status":      "drive_meta",
    "/chat":                                    "chat",
    "/api/v1/chat":                             "chat",
}


def _get_category(path: str, method: str) -> str | None:
    """Determine rate limit category for a request path."""
    # Exact match first
    if path in _PATH_CATEGORIES:
        cat = _PATH_CATEGORIES[path]
        # Google Drive GET endpoints are also rate-limited
        if cat == "google_drive":
            return cat
        # Other categories only apply to mutating methods
        if method not in ("POST", "PUT", "PATCH"):
            return None
        return cat
    # Prefix match for paths with IDs
    for prefix, cat in _PATH_CATEGORIES.items():
        if path.startswith(prefix):
            if cat == "google_drive":
                return cat
            if method not in ("POST", "PUT", "PATCH"):
                return None
            return cat
    return None


def _get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Redis-backed rate limiter ─────────────────────────────────────────────────

_redis_client = None
_redis_checked = False


def _get_redis():
    """Lazy Redis connection for rate limiting."""
    global _redis_client, _redis_checked
    if _redis_checked:
        return _redis_client
    _redis_checked = True
    try:
        import redis
        url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
        _redis_client.ping()
        return _redis_client
    except Exception as e:
        logger.warning(f"Rate limiter: Redis unavailable, using in-memory fallback: {e}")
        _redis_client = None
        return None


def _check_rate_limit_redis(key: str, max_requests: int, window: int) -> Tuple[bool, int]:
    """
    Check rate limit using Redis sliding window counter.
    Returns (allowed: bool, remaining: int).
    """
    r = _get_redis()
    if r is None:
        return _check_rate_limit_memory(key, max_requests, window)

    try:
        redis_key = f"ratelimit:{key}"
        current = r.get(redis_key)
        if current is None:
            r.setex(redis_key, window, 1)
            return True, max_requests - 1
        count = int(current)
        if count >= max_requests:
            ttl = r.ttl(redis_key)
            return False, 0
        r.incr(redis_key)
        return True, max_requests - count - 1
    except Exception:
        return _check_rate_limit_memory(key, max_requests, window)


# ── In-memory fallback ────────────────────────────────────────────────────────

import threading
from collections import OrderedDict

_MAX_MEMORY_KEYS = 10_000  # Bound memory usage — evict oldest when full
_memory_store: OrderedDict = OrderedDict()
_memory_lock = threading.Lock()


def _check_rate_limit_memory(key: str, max_requests: int, window: int) -> Tuple[bool, int]:
    """In-memory sliding window rate limiter (fallback). Thread-safe and bounded."""
    now = time.time()
    with _memory_lock:
        # Evict oldest entries if at capacity
        while len(_memory_store) >= _MAX_MEMORY_KEYS:
            _memory_store.popitem(last=False)

        # Clean old timestamps for this key
        timestamps = _memory_store.get(key, [])
        timestamps = [t for t in timestamps if now - t < window]

        if len(timestamps) >= max_requests:
            _memory_store[key] = timestamps
            return False, 0

        timestamps.append(now)
        _memory_store[key] = timestamps
        remaining = max_requests - len(timestamps)
        return True, remaining


# ── Middleware ────────────────────────────────────────────────────────────────

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Rate limiting middleware.
    Applies per-IP limits based on the request path category.
    """

    async def dispatch(self, request: Request, call_next):
        category = _get_category(request.url.path, request.method)
        if category is None:
            return await call_next(request)

        max_requests, window = RATE_LIMITS[category]
        client_ip = _get_client_ip(request)
        key = f"{category}:{client_ip}"

        allowed, remaining = _check_rate_limit_redis(key, max_requests, window)

        if not allowed:
            logger.warning(
                f"Rate limit exceeded: {client_ip} on {category} "
                f"({max_requests}/{window}s)"
            )
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "TooManyRequests",
                    "detail": f"Rate limit exceeded for {category}. "
                              f"Maximum {max_requests} requests per {window} seconds.",
                },
                headers={
                    "Retry-After": str(window),
                    "X-RateLimit-Limit": str(max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response
