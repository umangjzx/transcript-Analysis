"""
Google Drive Service
====================
Handles OAuth2 authentication and file operations for Google Drive / Docs.

Flow:
  1. GET /api/v1/google-drive/auth-url  → returns the Google OAuth consent URL
  2. User visits the URL, grants access, Google redirects to the callback URI
  3. GET /api/v1/google-drive/callback?code=...  → exchanges code for tokens,
     stores credentials in .google_credentials.json (gitignored)
  4. GET /api/v1/google-drive/files  → lists .txt / Google Docs files in Drive
  5. POST /api/v1/google-drive/import  → reads the file text and feeds it
     directly into the analysis pipeline as a transcript

Required env vars (add to .env):
  GOOGLE_CLIENT_ID
  GOOGLE_CLIENT_SECRET
  GOOGLE_REDIRECT_URI   (e.g. http://localhost:8000/api/v1/google-drive/callback)

Rate-limit protection:
  All Drive API calls use exponential back-off with jitter (up to
  DRIVE_MAX_RETRIES attempts, default 5).  The Drive API service object is
  cached per-process so googleapiclient.discovery.build() is not called on
  every request.
"""

import os
import json
import logging
import random
import time
import functools
from typing import Optional, List, Dict, Any, Callable, TypeVar

logger = logging.getLogger(__name__)

# ── Credentials file (gitignored) ─────────────────────────────────────────────
_CREDS_FILE = os.path.join(os.path.dirname(__file__), "..", ".google_credentials.json")
_CREDS_FILE = os.path.normpath(_CREDS_FILE)

# ── OAuth2 scopes ─────────────────────────────────────────────────────────────
_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/documents.readonly",
]

# ── MIME types we accept as transcript sources ────────────────────────────────
_ACCEPTED_MIME_TYPES = {
    "text/plain",                                          # .txt files
    "application/vnd.google-apps.document",               # Google Docs
}

# ── Rate-limit / retry config ─────────────────────────────────────────────────
# Maximum number of retry attempts on transient / rate-limit errors.
_MAX_RETRIES: int = int(os.getenv("DRIVE_MAX_RETRIES", "5"))
# Base delay (seconds) for exponential back-off.  Actual delay is:
#   min(BASE * 2^attempt + jitter, MAX_BACKOFF)
_BACKOFF_BASE: float = float(os.getenv("DRIVE_BACKOFF_BASE_SECONDS", "1.0"))
_MAX_BACKOFF: float  = float(os.getenv("DRIVE_MAX_BACKOFF_SECONDS", "32.0"))

# HTTP status codes that warrant a retry
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# ── Service object cache ───────────────────────────────────────────────────────
# Caches the Drive v3 service so googleapiclient.discovery.build() is only
# called once per process (or after a credential refresh).
_service_cache: Optional[Any] = None


# ── Retry decorator ────────────────────────────────────────────────────────────

F = TypeVar("F", bound=Callable[..., Any])


def _with_backoff(fn: F) -> F:
    """
    Decorator: retry *fn* up to _MAX_RETRIES times on Drive API rate-limit or
    transient errors, using exponential back-off with full jitter.
    """
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        last_exc = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as exc:
                # Detect retryable errors from googleapiclient
                status_code = _extract_status_code(exc)
                is_retryable = (
                    status_code in _RETRYABLE_STATUS_CODES
                    or "rateLimitExceeded" in str(exc)
                    or "userRateLimitExceeded" in str(exc)
                    or "Rate Limit" in str(exc)
                    or "quota" in str(exc).lower()
                    or "backendError" in str(exc)
                )
                if not is_retryable or attempt == _MAX_RETRIES:
                    raise
                last_exc = exc
                delay = min(
                    _BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 1),
                    _MAX_BACKOFF,
                )
                logger.warning(
                    f"[GoogleDrive] {fn.__name__} hit a transient error "
                    f"(HTTP {status_code or 'unknown'}): {exc}. "
                    f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{_MAX_RETRIES})."
                )
                time.sleep(delay)
        raise last_exc  # unreachable but keeps type-checker happy
    return wrapper  # type: ignore[return-value]


def _extract_status_code(exc: Exception) -> Optional[int]:
    """Pull an HTTP status code out of a googleapiclient HttpError if present."""
    try:
        from googleapiclient.errors import HttpError  # type: ignore
        if isinstance(exc, HttpError):
            return int(exc.resp.status)
    except Exception:
        pass
    return None


# ── Client config ─────────────────────────────────────────────────────────────

def _get_client_config() -> Dict[str, str]:
    """Read OAuth2 client config from environment variables."""
    client_id = os.getenv("GOOGLE_CLIENT_ID", "")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET", "")
    redirect_uri = os.getenv(
        "GOOGLE_REDIRECT_URI",
        "http://localhost:8000/api/v1/google-drive/callback",
    )
    if not client_id or not client_secret:
        raise ValueError(
            "GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET must be set in .env. "
            "See .env.example for instructions."
        )
    return {
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }


# ── Auth URL ──────────────────────────────────────────────────────────────────

def get_auth_url() -> str:
    """
    Build the Google OAuth2 consent-screen URL.
    The user visits this URL, grants access, and is redirected back with a code.
    """
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
    except ImportError:
        raise RuntimeError(
            "google-auth-oauthlib is not installed. "
            "Run: pip install google-auth-oauthlib google-api-python-client"
        )

    cfg = _get_client_config()
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [cfg["redirect_uri"]],
            }
        },
        scopes=_SCOPES,
        redirect_uri=cfg["redirect_uri"],
    )
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    return auth_url


# ── Token exchange (callback) ─────────────────────────────────────────────────

def exchange_code_for_tokens(code: str) -> Dict[str, Any]:
    """
    Exchange the OAuth2 authorization code for access + refresh tokens.
    Persists credentials encrypted to disk for reuse.
    Returns a dict with token info (no raw secrets echoed to the caller).
    """
    try:
        from google_auth_oauthlib.flow import Flow  # type: ignore
    except ImportError:
        raise RuntimeError("google-auth-oauthlib is not installed.")

    from modules.credential_encryption import encrypt_credentials

    cfg = _get_client_config()
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [cfg["redirect_uri"]],
            }
        },
        scopes=_SCOPES,
        redirect_uri=cfg["redirect_uri"],
    )
    flow.fetch_token(code=code)
    creds = flow.credentials

    # Persist encrypted to disk so the user doesn't need to re-auth on every restart
    creds_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes) if creds.scopes else _SCOPES,
    }
    encrypt_credentials(creds_data, _CREDS_FILE)
    # Invalidate the service cache so the next call uses fresh credentials
    _invalidate_service_cache()
    logger.info("Google credentials saved (encrypted at rest)")

    return {"status": "authenticated", "scopes": creds_data["scopes"]}


# ── Load persisted credentials ────────────────────────────────────────────────

def _load_credentials():
    """
    Load and (if needed) refresh credentials from the persisted (encrypted) file.
    Returns a google.oauth2.credentials.Credentials object or raises.
    """
    try:
        from google.oauth2.credentials import Credentials  # type: ignore
        from google.auth.transport.requests import Request  # type: ignore
    except ImportError:
        raise RuntimeError(
            "google-auth is not installed. "
            "Run: pip install google-auth google-auth-oauthlib google-api-python-client"
        )

    from modules.credential_encryption import decrypt_credentials, encrypt_credentials

    try:
        data = decrypt_credentials(_CREDS_FILE)
    except FileNotFoundError:
        raise PermissionError(
            "Not authenticated with Google Drive. "
            "Call GET /api/v1/google-drive/auth-url first."
        )

    creds = Credentials(
        token=data.get("token"),
        refresh_token=data.get("refresh_token"),
        token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=data.get("client_id"),
        client_secret=data.get("client_secret"),
        scopes=data.get("scopes", _SCOPES),
    )

    # Refresh if expired
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        data["token"] = creds.token
        encrypt_credentials(data, _CREDS_FILE)
        # Credential changed — bust the service cache
        _invalidate_service_cache()
        logger.info("Google credentials refreshed and saved.")

    return creds


# ── Service cache ─────────────────────────────────────────────────────────────

def _invalidate_service_cache() -> None:
    """Bust the cached Drive service (e.g. after a credential refresh)."""
    global _service_cache
    _service_cache = None


def _get_drive_service():
    """
    Return a cached Drive v3 service object.

    googleapiclient.discovery.build() makes a network call to fetch the
    discovery document on first use; caching it avoids that overhead (and one
    extra network round-trip that counts against quotas) on every request.
    """
    global _service_cache
    if _service_cache is not None:
        return _service_cache

    try:
        from googleapiclient.discovery import build  # type: ignore
    except ImportError:
        raise RuntimeError("google-api-python-client is not installed.")

    creds = _load_credentials()
    _service_cache = build("drive", "v3", credentials=creds, cache_discovery=False)
    logger.debug("[GoogleDrive] Drive service object created and cached.")
    return _service_cache


# ── List files ────────────────────────────────────────────────────────────────

@_with_backoff
def list_drive_files(
    page_size: int = 50,
    query: Optional[str] = None,
) -> List[Dict[str, str]]:
    """
    List files in Google Drive that can be used as transcripts.
    Returns a list of dicts: {id, name, mimeType, modifiedTime, webViewLink}

    By default lists .txt files and Google Docs.
    Pass a custom `query` to override (uses Drive API query syntax).

    Retries automatically on rate-limit / transient errors (see _with_backoff).
    """
    service = _get_drive_service()

    if query is None:
        mime_filter = " or ".join(
            f"mimeType='{m}'" for m in _ACCEPTED_MIME_TYPES
        )
        query = f"({mime_filter}) and trashed=false"

    results = (
        service.files()
        .list(
            q=query,
            pageSize=min(page_size, 100),
            fields="files(id, name, mimeType, modifiedTime, webViewLink)",
            orderBy="modifiedTime desc",
        )
        .execute()
    )

    files = results.get("files", [])
    logger.info(f"[GoogleDrive] Found {len(files)} file(s)")
    return files


# ── Read file content ─────────────────────────────────────────────────────────

@_with_backoff
def read_drive_file(file_id: str, mime_type: str) -> str:
    """
    Download and return the plain-text content of a Drive file.

    - Google Docs  → exported as text/plain via the export API
    - .txt files   → downloaded directly via the media download API

    Retries automatically on rate-limit / transient errors (see _with_backoff).
    """
    try:
        from googleapiclient.http import MediaIoBaseDownload  # type: ignore
    except ImportError:
        raise RuntimeError("google-api-python-client is not installed.")

    import io

    service = _get_drive_service()

    if mime_type == "application/vnd.google-apps.document":
        # Export Google Doc as plain text
        response = (
            service.files()
            .export(fileId=file_id, mimeType="text/plain")
            .execute()
        )
        if isinstance(response, bytes):
            return response.decode("utf-8", errors="replace")
        return str(response)

    else:
        # Download raw file (e.g. .txt)
        request = service.files().get_media(fileId=file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buffer.getvalue().decode("utf-8", errors="replace")


# ── Auth status ───────────────────────────────────────────────────────────────

def is_authenticated() -> bool:
    """Return True if valid credentials are stored on disk."""
    try:
        _load_credentials()
        return True
    except Exception:
        return False


def revoke_credentials() -> None:
    """Delete stored credentials (logout)."""
    from modules.credential_encryption import delete_credentials
    _invalidate_service_cache()
    delete_credentials(_CREDS_FILE)
    logger.info("Google credentials revoked and deleted.")
