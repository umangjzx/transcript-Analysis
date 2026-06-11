"""
Celery application configuration.

Uses Redis as both broker and result backend.
All background tasks (analysis pipeline, drive watcher, cleanup) are
defined as Celery tasks instead of raw threading.Thread calls.

FALLBACK MODE:
  If Redis/Celery is unavailable (e.g. local dev without Redis),
  set USE_CELERY=false in .env. Tasks will run synchronously in-process
  via threading (same as the old behavior). This keeps the app functional
  without any external dependencies beyond MongoDB.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv(override=True)

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)
CELERY_RESULT_BACKEND = os.getenv("CELERY_RESULT_BACKEND", REDIS_URL)

# Set USE_CELERY=false in .env to disable Celery and use threading fallback
USE_CELERY = os.getenv("USE_CELERY", "true").strip().lower() == "true"


class _CeleryStub:
    """No-op stub so @celery_app.task(...) does not crash at import time
    when Celery is disabled. The decorator simply returns the original
    function unchanged, allowing the threading fallback to call it directly."""

    def task(self, *args, **kwargs):
        def decorator(func):
            return func
        return decorator


celery_app = None

if USE_CELERY:
    try:
        from celery import Celery

        celery_app = Celery(
            "audio_safety",
            broker=CELERY_BROKER_URL,
            backend=CELERY_RESULT_BACKEND,
        )

        celery_app.conf.update(
            task_serializer="json",
            accept_content=["json"],
            result_serializer="json",
            timezone="UTC",
            enable_utc=True,
            task_track_started=True,
            task_acks_late=True,
            worker_prefetch_multiplier=1,
            broker_connection_retry_on_startup=True,
            result_expires=86400,
        )

        # Explicitly include task modules (autodiscover looks for <pkg>.tasks
        # which doesn't match our layout of tasks/analysis_tasks.py etc.)
        celery_app.conf.include = [
            "tasks.analysis_tasks",
            "tasks.maintenance_tasks",
        ]
        logger.info("Celery configured (broker=%s)", CELERY_BROKER_URL)

    except ImportError:
        logger.warning("Celery not installed \u2014 falling back to threading mode")
        USE_CELERY = False
        celery_app = _CeleryStub()
    except Exception as e:
        logger.warning(f"Celery init failed \u2014 falling back to threading mode: {e}")
        USE_CELERY = False
        celery_app = _CeleryStub()
else:
    logger.info("Celery disabled (USE_CELERY=false) \u2014 using threading fallback")
    celery_app = _CeleryStub()
