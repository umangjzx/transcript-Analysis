"""
Credential encryption at rest using Fernet (AES-128-CBC).

Encrypts/decrypts the Google OAuth credentials file (.google_credentials.json)
so tokens are never stored in plaintext on disk.

The encryption key is derived from CREDENTIAL_ENCRYPTION_KEY in .env.
If the key is not set, credentials are stored in plaintext (backward-compatible).
"""

import os
import json
import base64
import hashlib
import logging
from typing import Optional, Dict, Any

from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)

_ENCRYPTED_SUFFIX = ".enc"


def _get_fernet() -> Optional[Fernet]:
    """
    Derive a Fernet key from the CREDENTIAL_ENCRYPTION_KEY env var.
    Returns None if the env var is not set (encryption disabled).
    """
    raw_key = os.getenv("CREDENTIAL_ENCRYPTION_KEY", "")
    if not raw_key:
        return None
    # Derive a 32-byte key from the user-provided secret using SHA-256,
    # then base64-encode it for Fernet (which requires a URL-safe base64 key).
    derived = hashlib.sha256(raw_key.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(derived)
    return Fernet(fernet_key)


def encrypt_credentials(data: Dict[str, Any], filepath: str) -> None:
    """
    Save credentials to disk. If CREDENTIAL_ENCRYPTION_KEY is set,
    the file is encrypted with Fernet. Otherwise, stored as plain JSON.
    """
    json_bytes = json.dumps(data, indent=2).encode("utf-8")
    fernet = _get_fernet()

    if fernet is not None:
        encrypted = fernet.encrypt(json_bytes)
        enc_path = filepath + _ENCRYPTED_SUFFIX
        with open(enc_path, "wb") as f:
            f.write(encrypted)
        # Remove plaintext file if it exists
        if os.path.exists(filepath):
            os.remove(filepath)
        logger.info(f"Credentials encrypted and saved to {enc_path}")
    else:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        # Remove encrypted file if it exists (key was removed)
        enc_path = filepath + _ENCRYPTED_SUFFIX
        if os.path.exists(enc_path):
            os.remove(enc_path)
        logger.info(f"Credentials saved (plaintext) to {filepath}")


def decrypt_credentials(filepath: str) -> Dict[str, Any]:
    """
    Load credentials from disk. Tries encrypted file first,
    falls back to plaintext for backward compatibility.

    Raises FileNotFoundError if neither file exists.
    """
    fernet = _get_fernet()
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
        f"No credentials file found at {filepath} or {enc_path}"
    )


def delete_credentials(filepath: str) -> None:
    """Delete both plaintext and encrypted credential files."""
    for path in [filepath, filepath + _ENCRYPTED_SUFFIX]:
        if os.path.exists(path):
            os.remove(path)
            logger.info(f"Deleted credentials file: {path}")
