"""
Authentication helpers for AuraSafety.

API key authentication — controlled by the API_KEY environment variable.

Usage
-----
Set API_KEY in .env to enable authentication:
    API_KEY=your-strong-random-key

Leave API_KEY blank (or unset) to disable auth — useful during local dev.

When enabled, every request to a protected endpoint must include:
    X-API-Key: <your-key>

The FastAPI dependency `get_current_user` is used in route handlers:
    @router.get("/protected")
    async def protected(user = Depends(get_current_user)):
        ...

When auth is disabled, `get_current_user` is a no-op that always succeeds.
"""

import os
from fastapi import Header, HTTPException, status

# Read once at import time — same value used by app.py middleware
API_KEY: str = os.getenv("API_KEY", "")
AUTH_ENABLED: bool = bool(API_KEY)


async def get_current_user(x_api_key: str = Header(default="")):
    """
    FastAPI dependency that validates the X-API-Key header.

    - If API_KEY is not set, auth is disabled and this is a no-op.
    - If API_KEY is set and the header is missing/wrong, raises 401.
    """
    if not AUTH_ENABLED:
        return None  # auth disabled — allow all requests

    if x_api_key != API_KEY:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid X-API-Key header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )
    return {"authenticated": True}
