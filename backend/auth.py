"""
Authentication for AuraSafety.

Strategy
--------
- Admin credentials are stored in MongoDB (collection: users).
- Passwords are hashed with bcrypt — plaintext is never stored.
- On successful login the server issues a signed JWT (HS256).
- Every protected endpoint validates the JWT via the `get_current_user`
  FastAPI dependency.
- The legacy X-API-Key middleware in app.py is kept for backward-compat
  with direct API / script access; JWT auth is used by the frontend.

JWT payload
-----------
    { "sub": "<username>", "role": "admin", "exp": <unix timestamp> }

Environment variables (add to .env)
------------------------------------
    JWT_SECRET=<long random string>   # required — used to sign tokens
    JWT_EXPIRE_MINUTES=480            # optional — default 8 hours
"""

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

JWT_SECRET: str = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES: int = int(os.getenv("JWT_EXPIRE_MINUTES", "480"))  # 8 hours

_bearer = HTTPBearer(auto_error=False)

# ── Password helpers ──────────────────────────────────────────────────────────

def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash of the plaintext password."""
    return bcrypt.hashpw(plaintext.encode(), bcrypt.gensalt(rounds=12)).decode()


def verify_password(plaintext: str, hashed: str) -> bool:
    """Return True if plaintext matches the stored bcrypt hash."""
    try:
        return bcrypt.checkpw(plaintext.encode(), hashed.encode())
    except Exception:
        return False


# ── JWT helpers ───────────────────────────────────────────────────────────────

def create_access_token(username: str, role: str = "admin") -> str:
    """Issue a signed JWT for the given user."""
    if not JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is not set. Add JWT_SECRET=<random-string> to backend/.env"
        )
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": username, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """
    Decode and validate a JWT.
    Raises HTTPException 401 on any failure.
    """
    if not JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is not configured on this server (JWT_SECRET missing).",
        )
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        username: str = payload.get("sub", "")
        if not username:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload.",
            )
        return payload
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token invalid or expired: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── MongoDB user helpers ──────────────────────────────────────────────────────

def _users_col():
    """Return the MongoDB 'users' collection, or None if unavailable."""
    from database.mongo import get_mongo_db
    db = get_mongo_db()
    return db["users"] if db is not None else None


def get_user(username: str) -> Optional[dict]:
    """Fetch a user document by username. Returns None if not found."""
    col = _users_col()
    if col is None:
        return None
    try:
        return col.find_one({"username": username}, {"_id": 0})
    except Exception as exc:
        logger.warning(f"get_user failed: {exc}")
        return None


def create_user(username: str, plaintext_password: str, role: str = "admin") -> bool:
    """
    Insert a new user with a bcrypt-hashed password.
    Returns True on success, False if the username already exists.
    """
    col = _users_col()
    if col is None:
        raise RuntimeError("MongoDB is unavailable — cannot create user.")
    if col.find_one({"username": username}):
        return False  # already exists
    col.insert_one({
        "username": username,
        "password_hash": hash_password(plaintext_password),
        "role": role,
        "created_at": datetime.now(timezone.utc),
    })
    logger.info(f"User '{username}' created with role '{role}'.")
    return True


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Verify credentials against MongoDB.
    Returns the user document on success, None on failure.
    """
    user = get_user(username)
    if not user:
        return None
    if not verify_password(password, user.get("password_hash", "")):
        return None
    return user


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
):
    """
    FastAPI dependency — validates the Bearer JWT on every protected route.

    Falls back gracefully:
    - If JWT_SECRET is not set, auth is disabled (dev mode).
    - If the token is missing/invalid, raises 401.
    """
    # Dev mode: no JWT_SECRET configured → skip auth entirely
    if not JWT_SECRET:
        return {"username": "dev", "role": "admin"}

    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(credentials.credentials)
    return {"username": payload["sub"], "role": payload.get("role", "admin")}
