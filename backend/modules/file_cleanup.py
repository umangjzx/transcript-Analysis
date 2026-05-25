"""
File Cleanup Module.

Periodically removes uploaded audio files and temp files older than TTL.
Runs as a background thread on startup.
"""

import os
import logging
from datetime import datetime, timedelta
from pathlib import Path
import threading
import time

logger = logging.getLogger(__name__)

# TTL for uploaded files (in days)
FILE_TTL_DAYS = int(os.getenv("FILE_TTL_DAYS", "7"))

# Cleanup interval (in hours)
CLEANUP_INTERVAL_HOURS = int(os.getenv("CLEANUP_INTERVAL_HOURS", "24"))


def cleanup_old_files(upload_folder: str) -> dict:
    """
    Remove files older than FILE_TTL_DAYS from the upload folder.
    
    Returns:
        dict with keys: deleted_count, deleted_size_mb, errors
    """
    if not os.path.exists(upload_folder):
        return {"deleted_count": 0, "deleted_size_mb": 0, "errors": []}
    
    stats = {
        "deleted_count": 0,
        "deleted_size_mb": 0,
        "errors": []
    }
    
    cutoff_time = datetime.utcnow() - timedelta(days=FILE_TTL_DAYS)
    
    for root, dirs, files in os.walk(upload_folder):
        for filename in files:
            filepath = os.path.join(root, filename)
            try:
                file_stat = os.stat(filepath)
                file_mtime = datetime.utcfromtimestamp(file_stat.st_mtime)
                
                if file_mtime < cutoff_time:
                    file_size_mb = file_stat.st_size / (1024 * 1024)
                    os.remove(filepath)
                    stats["deleted_count"] += 1
                    stats["deleted_size_mb"] += file_size_mb
                    logger.info(f"Cleaned up old file: {filepath} ({file_size_mb:.2f} MB)")
            except Exception as e:
                logger.error(f"Failed to clean up {filepath}: {e}")
                stats["errors"].append(str(e))
    
    return stats


def start_cleanup_daemon(upload_folder: str) -> threading.Thread:
    """
    Start a background cleanup thread.
    
    Returns:
        The daemon thread (already started)
    """
    def cleanup_loop():
        logger.info(f"Cleanup daemon started (TTL={FILE_TTL_DAYS} days, interval={CLEANUP_INTERVAL_HOURS}h)")
        
        # Run cleanup every CLEANUP_INTERVAL_HOURS
        while True:
            try:
                time.sleep(CLEANUP_INTERVAL_HOURS * 3600)
                logger.info("Running scheduled file cleanup...")
                stats = cleanup_old_files(upload_folder)
                logger.info(
                    f"Cleanup complete: {stats['deleted_count']} files deleted, "
                    f"{stats['deleted_size_mb']:.2f} MB freed"
                )
            except Exception as e:
                logger.error(f"Cleanup cycle failed: {e}")
    
    thread = threading.Thread(target=cleanup_loop, daemon=True)
    thread.start()
    
    # Also run cleanup on startup (non-blocking)
    try:
        stats = cleanup_old_files(upload_folder)
        logger.info(
            f"Startup cleanup: {stats['deleted_count']} files deleted, "
            f"{stats['deleted_size_mb']:.2f} MB freed"
        )
    except Exception as e:
        logger.warning(f"Startup cleanup failed: {e}")
    
    return thread
