"""
Authentication Routes
=====================
Prefix: /auth

Endpoints:
  POST /login   → authenticate and return JWT
  POST /logout  → clear httpOnly cookie
  GET  /me      → return current user info
"""

import os
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import authenticate_user, create_access_token, get_current_user, JWT_EXPIRE_MINUTES
from database.mongo import audit_log

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auth",
    tags=["Authentication"],
)


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login")
def login(body: LoginRequest):
    """
    Authenticate with username + password.
    Returns a signed JWT in an httpOnly cookie and in the response body.
    """
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    token = create_access_token(user["username"], user.get("role", "admin"))
    audit_log("login_success", details={"username": user["username"]})
    logger.info(f"Login: '{user['username']}' authenticated successfully.")

    response = JSONResponse(content={
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user.get("role", "admin"),
    })
    # Set JWT in httpOnly cookie — secure, not accessible via JavaScript
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        max_age=JWT_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response


@router.post("/logout")
def logout():
    """Logout — clears the httpOnly cookie and logs for audit."""
    audit_log("logout")
    response = JSONResponse(content={"message": "Logged out successfully."})
    response.delete_cookie(key="access_token", path="/")
    return response


@router.get("/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return current_user
