"""
Tests for authentication — JWT creation, validation, and protected routes.
"""

import pytest
from auth import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        plaintext = "MySecurePassword123!"
        hashed = hash_password(plaintext)
        assert hashed != plaintext
        assert verify_password(plaintext, hashed)

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_empty_password(self):
        hashed = hash_password("")
        assert verify_password("", hashed)
        assert not verify_password("anything", hashed)


class TestJWT:
    def test_create_and_decode(self):
        token = create_access_token("admin", "admin")
        payload = decode_access_token(token)
        assert payload["sub"] == "admin"
        assert payload["role"] == "admin"

    def test_decode_invalid_token(self):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            decode_access_token("invalid.token.value")
        assert exc_info.value.status_code == 401

    def test_token_contains_expiry(self):
        token = create_access_token("user1", "analyst")
        payload = decode_access_token(token)
        assert "exp" in payload


class TestAuthEndpoints:
    def test_login_missing_credentials(self, client):
        response = client.post("/auth/login", json={})
        assert response.status_code == 422  # Pydantic validation error

    def test_login_invalid_credentials(self, client):
        response = client.post("/auth/login", json={
            "username": "nonexistent",
            "password": "wrong"
        })
        # Should be 401 (no user) or 423 (locked) — not 500
        assert response.status_code in (401, 423)

    def test_me_without_auth(self, client):
        response = client.get("/auth/me")
        # Without token and JWT_SECRET set, should return 401
        assert response.status_code == 401

    def test_me_with_valid_token(self, client, auth_headers):
        response = client.get("/auth/me", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
        assert data["role"] == "admin"

    def test_me_with_cookie(self, client, auth_cookie):
        response = client.get("/auth/me", cookies=auth_cookie)
        assert response.status_code == 200
        data = response.json()
        assert data["username"] == "testuser"
