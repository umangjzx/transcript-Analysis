"""
Celery tasks for maintenance operations.

Replaces the threading-based cleanup daemon and drive watcher loop.
Schedule these with Celery Beat or call them periodically.
"""

import os
import sys
import time
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path

# Ensure the backend root (/app in Docker) is on sys.path so that
# deferred imports resolve correctly in Celery forked worker processes.
_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

from celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="tasks.cleanup_old_uploads")
def cleanup_old_uploads():
    """
    Delete uploaded audio files older than UPLOAD_TTL_HOURS.
    Schedule this with Celery Beat (e.g. every hour).
    """
    from config import UPLOAD_FOLDER

    ttl_hours = int(os.getenv("UPLOAD_TTL_HOURS", "24"))
    if ttl_hours <= 0:
        return {"deleted": 0, "message": "Cleanup disabled (TTL=0)"}

    cutoff_ts = time.time() - ttl_hours * 3600
    deleted = 0

    if os.path.isdir(UPLOAD_FOLDER):
        for fname in os.listdir(UPLOAD_FOLDER):
            fpath = os.path.join(UPLOAD_FOLDER, fname)
            try:
                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff_ts:
                    os.remove(fpath)
                    deleted += 1
            except Exception:
                pass

    if deleted:
        logger.info(f"Upload cleanup: removed {deleted} file(s) older than {ttl_hours}h")

    return {"deleted": deleted, "ttl_hours": ttl_hours}


@celery_app.task(name="tasks.poll_google_drive")
def poll_google_drive():
    """
    Single poll cycle for Google Drive auto-import.
    Schedule this with Celery Beat at DRIVE_POLL_INTERVAL_SECONDS.
    """
    from services.google_drive_service import list_drive_files, read_drive_file, is_authenticated
    from database.mongo import next_meeting_id, save_meeting_metadata

    if not is_authenticated():
        logger.debug("[DriveWatcher] Not authenticated — skipping poll.")
        return {"status": "skipped", "reason": "not_authenticated"}

    poll_interval = int(os.getenv("DRIVE_POLL_INTERVAL_SECONDS", "120"))
    lookback_seconds = poll_interval * 2
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=lookback_seconds)
    cutoff_str = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")

    mime_filter = (
        "(mimeType='text/plain' or mimeType='application/vnd.google-apps.document')"
    )
    query = f"{mime_filter} and trashed=false and modifiedTime > '{cutoff_str}'"

    watch_folder = os.getenv("DRIVE_WATCH_FOLDER_ID", "")
    if watch_folder:
        query += f" and '{watch_folder}' in parents"

    try:
        files = list_drive_files(page_size=50, query=query)
    except Exception as e:
        logger.warning(f"[DriveWatcher] Drive list failed: {e}")
        return {"status": "error", "error": str(e)}

    # Check which files are already seen
    from database.mongo import get_mongo_db
    db = get_mongo_db()
    new_files = []
    for f in files:
        if db is not None:
            seen = db["drive_watcher_seen"].find_one({"file_id": f["id"]})
            if seen:
                continue
        new_files.append(f)

    if not new_files:
        return {"status": "ok", "new_files": 0}

    logger.info(f"[DriveWatcher] Found {len(new_files)} new file(s) to process.")
    processed = 0

    for file in new_files:
        file_id = file["id"]
        filename = file.get("name", f"drive_{file_id}.txt")
        mime_type = file.get("mimeType", "text/plain")

        try:
            transcript_text = read_drive_file(file_id, mime_type)
            if not transcript_text or not transcript_text.strip():
                # Mark as seen even if empty
                if db is not None:
                    db["drive_watcher_seen"].update_one(
                        {"file_id": file_id},
                        {"$set": {"file_id": file_id, "filename": filename,
                                  "seen_at": datetime.now(timezone.utc)}},
                        upsert=True,
                    )
                continue

            record_id = next_meeting_id()
            save_meeting_metadata(
                meeting_id=record_id,
                filename=filename,
                file_size_bytes=len(transcript_text.encode("utf-8")),
                status="PROCESSING",
            )

            # Dispatch as a Celery task instead of a thread
            from tasks.analysis_tasks import run_drive_import_analysis
            run_drive_import_analysis.delay(record_id, transcript_text, filename)

            # Mark as seen
            if db is not None:
                db["drive_watcher_seen"].update_one(
                    {"file_id": file_id},
                    {"$set": {"file_id": file_id, "filename": filename,
                              "seen_at": datetime.now(timezone.utc)}},
                    upsert=True,
                )
            processed += 1

        except Exception as e:
            logger.error(f"[DriveWatcher] Failed to import '{filename}': {e}", exc_info=True)

    return {"status": "ok", "new_files": processed}
