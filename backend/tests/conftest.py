"""
Shared test fixtures for the MelodyWings Safety backend.

Uses FastAPI TestClient — no real MongoDB/Redis required.
External services are mocked where needed.
"""

import os
import pytest

# Force test environment before any app imports
os.environ["ENV"] = "test"
os.environ["JWT_SECRET"] = "test-secret-key-for-unit-tests-only"
os.environ["API_KEY"] = ""
os.environ["MONGO_URI"] = ""  # Disable real MongoDB in tests
os.environ["REDIS_URL"] = ""  # Disable real Redis in tests
os.environ["ENABLE_ML_CLASSIFIER"] = "false"
os.environ["ENABLE_LLM_SUMMARY"] = "false"
os.environ["ENABLE_VIRUS_SCAN"] = "false"
os.environ["USE_CELERY"] = "false"


@pytest.fixture
def client():
    """FastAPI TestClient — creates a fresh app instance per test."""
    from fastapi.testclient import TestClient
    from app import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """
    Get a valid JWT token via login.
    Requires the test admin user to exist in MongoDB.
    For unit tests without MongoDB, mock get_current_user instead.
    """
    from auth import create_access_token
    token = create_access_token("testuser", "admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_cookie(client):
    """
    Get a valid JWT as a cookie dict for httpOnly-based auth.
    """
    from auth import create_access_token
    token = create_access_token("testuser", "admin")
    return {"access_token": token}
