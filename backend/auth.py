"""
Authentication for Melody Wings Safety.

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
import jwt
from jwt.exceptions import PyJWTError
from fastapi import Depends, HTTPException, status, Request
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
    except PyJWTError as exc:
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


# ── Account Lockout ───────────────────────────────────────────────────────────

# Max failed login attempts before lockout
LOCKOUT_MAX_ATTEMPTS = int(os.getenv("LOCKOUT_MAX_ATTEMPTS", "5"))
# Lockout duration in minutes
LOCKOUT_DURATION_MINUTES = int(os.getenv("LOCKOUT_DURATION_MINUTES", "15"))


def _get_failed_attempts(username: str) -> dict:
    """Get the failed login attempts record for a user."""
    col = _users_col()
    if col is None:
        return {"attempts": 0, "locked_until": None}
    try:
        record = col.find_one(
            {"username": username},
            {"failed_attempts": 1, "locked_until": 1, "_id": 0}
        )
        if not record:
            return {"attempts": 0, "locked_until": None}
        return {
            "attempts": record.get("failed_attempts", 0),
            "locked_until": record.get("locked_until"),
        }
    except Exception:
        return {"attempts": 0, "locked_until": None}


def _record_failed_attempt(username: str) -> int:
    """Increment failed login attempts. Returns new count."""
    col = _users_col()
    if col is None:
        return 0
    try:
        result = col.find_one_and_update(
            {"username": username},
            {
                "$inc": {"failed_attempts": 1},
                "$set": {"last_failed_at": datetime.now(timezone.utc)},
            },
            return_document=True,
        )
        new_count = result.get("failed_attempts", 1) if result else 1
        # Lock the account if threshold exceeded
        if new_count >= LOCKOUT_MAX_ATTEMPTS:
            lock_until = datetime.now(timezone.utc) + timedelta(minutes=LOCKOUT_DURATION_MINUTES)
            col.update_one(
                {"username": username},
                {"$set": {"locked_until": lock_until}},
            )
            logger.warning(
                f"Account '{username}' locked for {LOCKOUT_DURATION_MINUTES} min "
                f"after {new_count} failed attempts"
            )
        return new_count
    except Exception as e:
        logger.warning(f"Failed to record login attempt: {e}")
        return 0


def _reset_failed_attempts(username: str) -> None:
    """Reset failed login attempts on successful login."""
    col = _users_col()
    if col is None:
        return
    try:
        col.update_one(
            {"username": username},
            {"$set": {"failed_attempts": 0, "locked_until": None}},
        )
    except Exception:
        pass


def authenticate_user(username: str, password: str) -> Optional[dict]:
    """
    Verify credentials against MongoDB with account lockout protection.
    Returns the user document on success, None on failure.
    Raises HTTPException 423 if the account is locked.
    """
    # Check lockout status
    lockout_info = _get_failed_attempts(username)
    locked_until = lockout_info.get("locked_until")
    if locked_until and isinstance(locked_until, datetime):
        if datetime.now(timezone.utc) < locked_until:
            remaining = int((locked_until - datetime.now(timezone.utc)).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=423,
                detail=f"Account locked due to too many failed attempts. "
                       f"Try again in {remaining} minute(s).",
            )
        else:
            # Lockout expired — reset
            _reset_failed_attempts(username)

    user = get_user(username)
    if not user:
        # Still record attempt to prevent username enumeration timing attacks
        _record_failed_attempt(username)
        return None
    if not verify_password(password, user.get("password_hash", "")):
        _record_failed_attempt(username)
        return None

    # Success — reset failed attempts
    _reset_failed_attempts(username)
    return user


# ── FastAPI dependency ────────────────────────────────────────────────────────

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
    request: Request = None,
):
    """
    FastAPI dependency — validates the Bearer JWT on every protected route.

    Token resolution order:
    1. Authorization: Bearer <token> header
    2. access_token httpOnly cookie

    Falls back gracefully:
    - If JWT_SECRET is not set, auth is disabled (dev mode).
    - If the token is missing/invalid, raises 401.
    """
    from fastapi import Request as _Request

    # Dev mode: no JWT_SECRET configured → skip auth entirely
    if not JWT_SECRET:
        return {"username": "dev", "role": "admin"}

    token = None

    # Try Bearer header first
    if credentials and credentials.credentials:
        token = credentials.credentials

    # Fall back to httpOnly cookie
    if not token and request is not None:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    payload = decode_access_token(token)
    return {"username": payload["sub"], "role": payload.get("role", "admin")}
