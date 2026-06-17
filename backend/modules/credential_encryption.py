"""
Credential storage for Google OAuth tokens.

Strategy
--------
- PRIMARY: Store credentials in MongoDB (persistent across container restarts)
- FALLBACK: Local filesystem (for local development without MongoDB)

The credentials are encrypted with Fernet (AES-128-CBC) using the
CREDENTIAL_ENCRYPTION_KEY from .env before being stored in either location.

If CREDENTIAL_ENCRYPTION_KEY is not set, credentials are stored in plaintext
(backward-compatible, local dev only).
"""

import os
import json
import base64
import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENCRYPTED_SUFFIX = ".enc"
_MONGO_COLLECTION = "google_credentials"
_MONGO_DOC_ID = "google_drive_oauth"


def _get_fernet() -> Optional[Fernet]:
    """
    Derive a Fernet key from the CREDENTIAL_ENCRYPTION_KEY env var.
    Returns None if the env var is not set (encryption disabled).
    """
    raw_key = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")
    if not raw_key:
        return None
    derived = hashlib.sha256(raw_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


def _get_credentials_collection():
    """Get the MongoDB collection for storing credentials."""
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is not None:
            return db[_MONGO_COLLECTION]
    except Exception as e:
        logger.debug(f"MongoDB unavailable for credential storage: {e}")
    return None


# ── Public API ────────────────────────────────────────────────────────────────


def encrypt_credentials(data: Dict[str, Any], filepath: str) -> None:
    """
    Save credentials. Tries MongoDB first (persistent), falls back to disk.
    If CREDENTIAL_ENCRYPTION_KEY is set, the data is encrypted before storage.
    """
    json_bytes = json.dumps(data, indent=2).encode("utf-8")
    fernet = _get_fernet()

    # Encrypt if key is available
    if fernet is not None:
        stored_value = fernet.encrypt(json_bytes).decode("utf-8")
        is_encrypted = True
    else:
        stored_value = json_bytes.decode("utf-8")
        is_encrypted = False

    # Try MongoDB first (persistent across container restarts)
    col = _get_credentials_collection()
    if col is not None:
        try:
            col.update_one(
                {"_id": _MONGO_DOC_ID},
                {
                    "$set": {
                        "credentials": stored_value,
                        "encrypted": is_encrypted,
                        "updated_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )
            logger.info("Google credentials saved to MongoDB (persistent)")
            # Also save to disk as a local cache
            _save_to_disk(data, filepath, fernet)
            return
        except Exception as e:
            logger.warning(f"Failed to save credentials to MongoDB: {e}")

    # Fallback: save to disk only
    _save_to_disk(data, filepath, fernet)


def decrypt_credentials(filepath: str) -> Dict[str, Any]:
    """
    Load credentials. Tries MongoDB first, falls back to disk.

    Raises FileNotFoundError if credentials are not found in either location.
    """
    fernet = _get_fernet()

    # Try MongoDB first
    col = _get_credentials_collection()
    if col is not None:
        try:
            doc = col.find_one({"_id": _MONGO_DOC_ID})
            if doc and "credentials" in doc:
                stored_value = doc["credentials"]
                is_encrypted = doc.get("encrypted", False)

                if is_encrypted:
                    if fernet is None:
                        raise RuntimeError(
                            "Encrypted credentials found in MongoDB but "
                            "CREDENTIAL_ENCRYPTION_KEY is not set."
                        )
                    try:
                        decrypted = fernet.decrypt(stored_value.encode("utf-8"))
                        data = json.loads(decrypted.decode("utf-8"))
                    except InvalidToken:
                        raise RuntimeError(
                            "Failed to decrypt credentials from MongoDB. "
                            "The CREDENTIAL_ENCRYPTION_KEY may have changed."
                        )
                else:
                    data = json.loads(stored_value)

                logger.debug("Google credentials loaded from MongoDB")
                return data
        except (RuntimeError, json.JSONDecodeError):
            raise
        except Exception as e:
            logger.warning(f"Failed to read credentials from MongoDB: {e}")

    # Fallback: try disk
    return _load_from_disk(filepath, fernet)


def delete_credentials(filepath: str) -> None:
    """Delete credentials from both MongoDB and disk."""
    # Delete from MongoDB
    col = _get_credentials_collection()
    if col is not None:
        try:
            result = col.delete_one({"_id": _MONGO_DOC_ID})
            if result.deleted_count:
                logger.info("Google credentials deleted from MongoDB")
        except Exception as e:
            logger.warning(f"Failed to delete credentials from MongoDB: {e}")

    # Delete from disk
    for path in [filepath, filepath + _ENCRYPTED_SUFFIX]:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Deleted credentials file: {path}")


# ── Private helpers ───────────────────────────────────────────────────────────


def _save_to_disk(data: Dict[str, Any], filepath: str, fernet: Optional[Fernet]) -> None:
    """Save credentials to the local filesystem."""
    try:
        json_bytes = json.dumps(data, indent=2).encode("utf-8")
        if fernet is not None:
            encrypted = fernet.encrypt(json_bytes)
            enc_path = filepath + _ENCRYPTED_SUFFIX
            with open(enc_path, "wb") as f:
                f.write(encrypted)
            if os.path.exists(filepath):
                os.remove(filepath)
            logger.info(f"Credentials saved (encrypted) to {enc_path}")
        else:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            enc_path = filepath + _ENCRYPTED_SUFFIX
            if os.path.exists(enc_path):
                os.remove(enc_path)
            logger.info(f"Credentials saved (plaintext) to {filepath}")
    except Exception as e:
        logger.debug(f"Could not save credentials to disk: {e}")


def _load_from_disk(filepath: str, fernet: Optional[Fernet]) -> Dict[str, Any]:
    """Load credentials from the local filesystem."""
    enc_path = filepath + _ENCRYPTED_SUFFIX

    # Try encrypted file first
    if os.path.exists(enc_path):
        if fernet is None:
            raise RuntimeError(
                "Encrypted credentials file found but CREDENTIAL_ENCRYPTION_KEY "
                "is not set in .env. Cannot decrypt."
            )
        try:
            with open(enc_path, "rb") as f:
                encrypted = f.read()
            decrypted = fernet.decrypt(encrypted)
            return json.loads(decrypted.decode("utf-8"))
        except InvalidToken:
            raise RuntimeError(
                "Failed to decrypt credentials. The CREDENTIAL_ENCRYPTION_KEY "
                "may have changed. Delete the .enc file and re-authenticate."
            )

    # Fall back to plaintext
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        # If encryption is now enabled, migrate to encrypted format
        if fernet is not None:
            logger.info("Migrating plaintext credentials to encrypted format...")
            encrypt_credentials(data, filepath)
        return data

    raise FileNotFoundError(
        f"No credentials found in MongoDB or at {filepath}"
    )
