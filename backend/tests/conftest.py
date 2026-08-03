"""
Shared test fixtures for the MelodyWings Safety backend.

Uses FastAPI TestClient — no real MongoDB/Redis required.
External services are mocked where needed.

NOTE: The full requirements.txt must be installed for tests to work
because the route modules import from services/modules that depend on
ML libraries. In CI, all deps are installed via `pip install -r requirements.txt`.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock, patch

# Neutralise .env loading before anything imports it.
#
# Production modules call load_dotenv(override=True), which by design lets the
# .env file win over the process environment. That is fine in the container
# (.dockerignore keeps .env out of the image, so Cloud Run's env vars apply),
# but on a developer machine that has a real backend/.env it silently overrode
# every setting below — pointing tests at the production MongoDB and restoring
# the real API_KEY, so 11 upload tests failed locally while passing in CI.
# Tests must not depend on whether a .env happens to exist next to them.
import dotenv as _dotenv

_dotenv.load_dotenv = lambda *a, **kw: False
for _mod in ("dotenv.main",):
    if _mod in sys.modules:
        sys.modules[_mod].load_dotenv = _dotenv.load_dotenv

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

# Mock heavy optional modules that may not be installed in all environments
_OPTIONAL_MODULES = [
    "ollama",
    "faster_whisper",
    "whisper",
    "chromadb",
    "chromadb.config",
    "sentence_transformers",
    "torch",
    "torch.nn",
    "torch.nn.functional",
    "transformers",
    "transformers.pipelines",
    "av",
    "reportlab",
    "reportlab.platypus",
    "reportlab.lib",
    "reportlab.lib.styles",
    "reportlab.lib.pagesizes",
    "reportlab.lib.colors",
    "reportlab.lib.units",
    "reportlab.lib.enums",
    "reportlab.pdfgen",
    "reportlab.pdfgen.canvas",
    "pyclamd",
    "boto3",
    "google",
    "google.oauth2",
    "google.oauth2.credentials",
    "google.auth",
    "google.auth.transport",
    "google.auth.transport.requests",
    "google_auth_oauthlib",
    "google_auth_oauthlib.flow",
    "googleapiclient",
    "googleapiclient.discovery",
    "googleapiclient.http",
]

for mod_name in _OPTIONAL_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


@pytest.fixture
def client():
    """FastAPI TestClient — creates a fresh app instance per test."""
    from fastapi.testclient import TestClient
    from app import app
    return TestClient(app)


@pytest.fixture
def auth_headers(client):
    """Get valid JWT auth headers for testing protected endpoints."""
    from auth import create_access_token
    token = create_access_token("testuser", "admin")
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def auth_cookie(client):
    """Get a valid JWT as a cookie dict for httpOnly-based auth."""
    from auth import create_access_token
    token = create_access_token("testuser", "admin")
    return {"access_token": token}
