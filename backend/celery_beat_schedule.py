"""
Celery Beat schedule configuration.

Run with:
  celery -A celery_app beat --loglevel=info

Or combined worker + beat:
  celery -A celery_app worker --beat --loglevel=info
"""

import os
from celery.schedules import crontab
from celery_app import celery_app

# Read intervals from environment
_upload_ttl = int(os.getenv("UPLOAD_TTL_HOURS", "24"))
_drive_poll = int(os.getenv("DRIVE_POLL_INTERVAL_SECONDS", "120"))
_auto_watch = os.getenv("DRIVE_AUTO_WATCH", "false").lower() == "true"

beat_schedule = {
    # Cleanup old uploads every hour
    "cleanup-old-uploads": {
        "task": "tasks.cleanup_old_uploads",
        "schedule": 3600.0,  # every hour
        "enabled": _upload_ttl > 0,
    },
}

# Add Drive polling only if auto-watch is enabled
if _auto_watch:
    beat_schedule["poll-google-drive"] = {
        "task": "tasks.poll_google_drive",
        "schedule": float(_drive_poll),
    }

celery_app.conf.beat_schedule = beat_schedule
