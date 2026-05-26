"""
drive_watcher.py
================
Background polling watcher for Google Drive.

Every DRIVE_POLL_INTERVAL_SECONDS (default 120) it:
  1. Lists .txt / Google Docs files modified after the last successful check
  2. Skips files already seen (tracked in MongoDB `drive_watcher_seen` collection)
  3. Downloads each new file's text content
  4. Feeds it straight into the transcript analysis pipeline

Config (add to .env):
  DRIVE_POLL_INTERVAL_SECONDS=120   # how often to poll (default 2 min)
  DRIVE_WATCH_FOLDER_ID=            # optional: limit to a specific Drive folder ID
  DRIVE_AUTO_WATCH=true             # set to false to disable on startup
"""

import os
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
POLL_INTERVAL: int = int(os.getenv("DRIVE_POLL_INTERVAL_SECONDS", "120"))
WATCH_FOLDER_ID: str = os.getenv("DRIVE_WATCH_FOLDER_ID", "")
AUTO_WATCH: bool = os.getenv("DRIVE_AUTO_WATCH", "false").lower() == "true"

# ── State ─────────────────────────────────────────────────────────────────────
_watcher_thread: Optional[threading.Thread] = None
_stop_event = threading.Event()
_watcher_lock = threading.Lock()

# Watcher status exposed to the API
watcher_status = {
    "running": False,
    "last_checked": None,
    "files_processed": 0,
    "errors": 0,
    "poll_interval_seconds": POLL_INTERVAL,
}


# ── Seen-file tracking (MongoDB) ──────────────────────────────────────────────

def _mark_seen(file_id: str, filename: str) -> None:
    """Record a Drive file ID so we never process it twice."""
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is not None:
            db["drive_watcher_seen"].update_one(
                {"file_id": file_id},
                {"$set": {"file_id": file_id, "filename": filename,
                           "seen_at": datetime.utcnow()}},
                upsert=True,
            )
    except Exception as e:
        logger.warning(f"[DriveWatcher] Could not mark file as seen: {e}")


def _is_seen(file_id: str) -> bool:
    """Return True if this Drive file has already been processed."""
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is not None:
            return db["drive_watcher_seen"].find_one({"file_id": file_id}) is not None
    except Exception as e:
        logger.warning(f"[DriveWatcher] Could not check seen status: {e}")
    return False


# ── Core poll logic ───────────────────────────────────────────────────────────

def _poll_once() -> None:
    """
    Single poll cycle:
    - Query Drive for files modified in the last POLL_INTERVAL * 2 seconds
      (double the interval to avoid missing files on slow polls)
    - Skip already-seen files
    - Import new ones into the analysis pipeline
    """
    from services.google_drive_service import list_drive_files, read_drive_file, is_authenticated
    from database.mongo import next_meeting_id, save_meeting_metadata

    if not is_authenticated():
        logger.debug("[DriveWatcher] Not authenticated — skipping poll.")
        return

    # Build query: files modified recently, correct MIME types, not trashed
    lookback_seconds = POLL_INTERVAL * 2
    cutoff = datetime.now(timezone.utc)
    # RFC 3339 format required by Drive API
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%S")

    mime_filter = (
        "(mimeType='text/plain' or mimeType='application/vnd.google-apps.document')"
    )
    query = f"{mime_filter} and trashed=false and modifiedTime > '{cutoff_str}'"

    # Optionally restrict to a specific folder
    if WATCH_FOLDER_ID:
        query += f" and '{WATCH_FOLDER_ID}' in parents"

    try:
        files = list_drive_files(page_size=50, query=query)
    except Exception as e:
        logger.warning(f"[DriveWatcher] Drive list failed: {e}")
        watcher_status["errors"] += 1
        return

    new_files = [f for f in files if not _is_seen(f["id"])]

    if not new_files:
        logger.debug(f"[DriveWatcher] Poll complete — no new files.")
        return

    logger.info(f"[DriveWatcher] Found {len(new_files)} new file(s) to process.")

    for file in new_files:
        file_id = file["id"]
        filename = file.get("name", f"drive_{file_id}.txt")
        mime_type = file.get("mimeType", "text/plain")

        try:
            logger.info(f"[DriveWatcher] Importing: '{filename}' ({file_id})")
            transcript_text = read_drive_file(file_id, mime_type)

            if not transcript_text or not transcript_text.strip():
                logger.warning(f"[DriveWatcher] '{filename}' is empty — skipping.")
                _mark_seen(file_id, filename)
                continue

            # Allocate a meeting record
            record_id = next_meeting_id()
            save_meeting_metadata(
                meeting_id=record_id,
                filename=filename,
                file_size_bytes=len(transcript_text.encode("utf-8")),
                status="PROCESSING",
            )

            # Run analysis in its own thread so the watcher isn't blocked
            threading.Thread(
                target=_run_pipeline,
                args=(record_id, transcript_text, filename),
                daemon=True,
            ).start()

            _mark_seen(file_id, filename)
            watcher_status["files_processed"] += 1
            logger.info(f"[DriveWatcher] Queued analysis #{record_id} for '{filename}'")

        except Exception as e:
            logger.error(f"[DriveWatcher] Failed to import '{filename}': {e}", exc_info=True)
            watcher_status["errors"] += 1


def _run_pipeline(record_id: int, transcript: str, filename: str) -> None:
    """Thin wrapper — delegates to the same pipeline used by the manual import."""
    try:
        from api.google_drive_routes import _run_transcript_pipeline
        _run_transcript_pipeline(record_id, transcript, filename)
    except Exception as e:
        logger.error(f"[DriveWatcher] Pipeline failed for #{record_id}: {e}", exc_info=True)


# ── Watcher thread ────────────────────────────────────────────────────────────

def _watcher_loop() -> None:
    logger.info(
        f"[DriveWatcher] Started — polling every {POLL_INTERVAL}s"
        + (f", folder={WATCH_FOLDER_ID}" if WATCH_FOLDER_ID else ", all Drive files")
    )
    watcher_status["running"] = True

    while not _stop_event.is_set():
        try:
            _poll_once()
        except Exception as e:
            logger.error(f"[DriveWatcher] Unexpected error in poll loop: {e}", exc_info=True)
            watcher_status["errors"] += 1

        watcher_status["last_checked"] = datetime.utcnow().isoformat()
        _stop_event.wait(timeout=POLL_INTERVAL)

    watcher_status["running"] = False
    logger.info("[DriveWatcher] Stopped.")


# ── Public API ────────────────────────────────────────────────────────────────

def start_watcher() -> bool:
    """
    Start the background polling thread.
    Returns True if started, False if already running.
    """
    global _watcher_thread
    with _watcher_lock:
        if _watcher_thread and _watcher_thread.is_alive():
            logger.info("[DriveWatcher] Already running.")
            return False
        _stop_event.clear()
        _watcher_thread = threading.Thread(
            target=_watcher_loop, daemon=True, name="DriveWatcher"
        )
        _watcher_thread.start()
        return True


def stop_watcher() -> bool:
    """
    Signal the watcher to stop after the current poll finishes.
    Returns True if a running watcher was stopped.
    """
    global _watcher_thread
    with _watcher_lock:
        if not _watcher_thread or not _watcher_thread.is_alive():
            return False
        _stop_event.set()
        _watcher_thread.join(timeout=10)
        return True


def get_status() -> dict:
    """Return current watcher status dict (safe to serialise as JSON)."""
    return {**watcher_status, "poll_interval_seconds": POLL_INTERVAL}
