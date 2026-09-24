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
    # Close out anything that's been PROCESSING for >30 min. Previously the
    # only sweep for this ran once at container cold-start (app.py); this
    # catches jobs that stall on a long-lived instance too.
    "reap-stuck-processing-jobs": {
        "task": "tasks.reap_stuck_processing_jobs",
        "schedule": 600.0,  # every 10 minutes
    },
}

# Cleanup old uploads every hour — only if a TTL is actually configured.
# ("enabled": False as a dict key is NOT a thing Celery's ScheduleEntry
# understands — it raised `TypeError: unexpected keyword argument 'enabled'`
# and crash-looped beat the moment this schedule was ever actually loaded.)
if _upload_ttl > 0:
    beat_schedule["cleanup-old-uploads"] = {
        "task": "tasks.cleanup_old_uploads",
        "schedule": 3600.0,  # every hour
    }

# Add Drive polling only if auto-watch is enabled
if _auto_watch:
    beat_schedule["poll-google-drive"] = {
        "task": "tasks.poll_google_drive",
        "schedule": float(_drive_poll),
    }

celery_app.conf.beat_schedule = beat_schedule
