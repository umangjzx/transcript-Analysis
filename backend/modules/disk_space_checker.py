"""
Disk Space Pre-Check for Uploads.

Verifies sufficient disk space is available before accepting file uploads.
Prevents the server from running out of disk space during large file processing.

Configuration via environment:
- MIN_DISK_SPACE_MB: Minimum free disk space required (default: 500 MB)
"""

import os
import shutil
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Minimum free disk space in MB (default 500 MB)
MIN_DISK_SPACE_MB = int(os.getenv("MIN_DISK_SPACE_MB", "500"))


def check_disk_space(
    target_dir: str = None,
    required_mb: int = None,
) -> Dict[str, Any]:
    """
    Check if sufficient disk space is available.

    Args:
        target_dir: Directory to check (defaults to UPLOAD_FOLDER).
        required_mb: Minimum required MB (defaults to MIN_DISK_SPACE_MB).

    Returns:
        {
            "ok": bool,
            "free_mb": float,
            "required_mb": int,
            "total_mb": float,
            "used_percent": float,
        }
    """
    if target_dir is None:
        from config import UPLOAD_FOLDER
        target_dir = UPLOAD_FOLDER

    if required_mb is None:
        required_mb = MIN_DISK_SPACE_MB

    try:
        usage = shutil.disk_usage(target_dir)
        free_mb = usage.free / (1024 * 1024)
        total_mb = usage.total / (1024 * 1024)
        used_percent = (usage.used / usage.total) * 100

        ok = free_mb >= required_mb

        if not ok:
            logger.warning(
                f"Disk space low: {free_mb:.0f} MB free, "
                f"need {required_mb} MB (used: {used_percent:.1f}%)"
            )

        return {
            "ok": ok,
            "free_mb": round(free_mb, 1),
            "required_mb": required_mb,
            "total_mb": round(total_mb, 1),
            "used_percent": round(used_percent, 1),
        }
    except Exception as e:
        logger.warning(f"Disk space check failed: {e}")
        # If we can't check, allow the upload (fail-open)
        return {
            "ok": True,
            "free_mb": None,
            "required_mb": required_mb,
            "total_mb": None,
            "used_percent": None,
            "error": str(e),
        }


def require_disk_space(file_size_bytes: int = 0, target_dir: str = None) -> None:
    """
    Raise an exception if insufficient disk space is available.

    Args:
        file_size_bytes: Expected file size (adds to minimum requirement).
        target_dir: Directory to check.

    Raises:
        IOError: If insufficient disk space.
    """
    # Add file size to minimum requirement (with 2x buffer for processing)
    extra_mb = (file_size_bytes * 2) / (1024 * 1024) if file_size_bytes else 0
    required = MIN_DISK_SPACE_MB + int(extra_mb)

    result = check_disk_space(target_dir=target_dir, required_mb=required)

    if not result["ok"]:
        raise IOError(
            f"Insufficient disk space: {result['free_mb']:.0f} MB available, "
            f"need {result['required_mb']} MB. "
            f"Disk is {result['used_percent']:.1f}% full."
        )
