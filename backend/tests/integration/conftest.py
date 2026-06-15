"""
Integration test fixtures.

These tests exercise multi-component flows (API → pipeline → WebSocket)
with real Redis (when available) but mocked MongoDB/ML services.
"""

import os
import sys
import pytest
from unittest.mock import MagicMock

# Force test environment
os.environ.setdefault("ENV", "test")
os.environ.setdefault("JWT_SECRET", "integration-test-secret")
os.environ.setdefault("API_KEY", "")
os.environ.setdefault("MONGO_URI", "")
os.environ.setdefault("ENABLE_ML_CLASSIFIER", "false")
os.environ.setdefault("ENABLE_LLM_SUMMARY", "false")
os.environ.setdefault("ENABLE_VIRUS_SCAN", "false")
os.environ.setdefault("USE_CELERY", "false")

# Mock heavy optional modules
_OPTIONAL_MODULES = [
    "ollama", "faster_whisper", "whisper", "chromadb", "chromadb.config",
    "sentence_transformers", "torch", "torch.nn", "torch.nn.functional",
    "transformers", "transformers.pipelines", "av",
    "reportlab", "reportlab.platypus", "reportlab.lib", "reportlab.lib.styles",
    "reportlab.lib.pagesizes", "reportlab.lib.colors", "reportlab.lib.units",
    "reportlab.lib.enums", "reportlab.pdfgen", "reportlab.pdfgen.canvas",
    "pyclamd", "boto3",
    "google", "google.oauth2", "google.oauth2.credentials",
    "google.auth", "google.auth.transport", "google.auth.transport.requests",
    "google_auth_oauthlib", "google_auth_oauthlib.flow",
    "googleapiclient", "googleapiclient.discovery", "googleapiclient.http",
]

for mod_name in _OPTIONAL_MODULES:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()


@pytest.fixture
def client():
    """FastAPI TestClient for integration tests."""
    from fastapi.testclient import TestClient
    from app import app
    return TestClient(app)


@pytest.fixture
def auth_token():
    """Generate a valid JWT for authenticated requests."""
    from auth import create_access_token
    return create_access_token("integration-user", "admin")


@pytest.fixture
def auth_headers(auth_token):
    """Authorization headers with Bearer token."""
    return {"Authorization": f"Bearer {auth_token}"}
