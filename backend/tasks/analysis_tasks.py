"""
Celery tasks for the analysis pipeline.

Replaces threading.Thread calls in app.py and audio_analysis_routes.py.
When USE_CELERY=false, these functions run directly in a background thread.

Dead Letter Queue:
  Failed tasks (after max retries) are persisted to MongoDB collection
  'dead_letter_queue' for manual inspection and replay. No analysis is
  silently lost.
"""

import logging
import threading
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _save_to_dead_letter_queue(
    task_name: str,
    record_id: int,
    filename: str,
    error: str,
    args: dict,
) -> None:
    """
    Persist a failed task to the dead_letter_queue collection.
    Allows operators to inspect and replay failed analyses.
    """
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is None:
            logger.error(
                f"[DLQ] Cannot persist failed task (MongoDB unavailable): "
                f"task={task_name}, record_id={record_id}, error={error}"
            )
            return
        db["dead_letter_queue"].insert_one({
            "task_name": task_name,
            "record_id": record_id,
            "filename": filename,
            "error": str(error)[:2000],
            "args": args,
            "failed_at": datetime.now(timezone.utc),
            "status": "failed",
            "retry_count": 0,
        })
        logger.warning(
            f"[DLQ] Task saved to dead letter queue: "
            f"task={task_name}, record_id={record_id}, error={error[:200]}"
        )
    except Exception as dlq_err:
        logger.error(f"[DLQ] Failed to save to dead letter queue: {dlq_err}")


def _run_audio(record_id: int, filepath: str, filename: str):
    """Core logic — runs the audio analysis pipeline."""
    from modules.analysis_pipeline import run_analysis_pipeline
    try:
        run_analysis_pipeline(
            record_id=record_id,
            filename=filename,
            audio_filepath=filepath,
            upload_to_s3=True,
            source="upload",
        )
    except Exception as exc:
        logger.error(f"[#{record_id}] Audio analysis failed: {exc}", exc_info=True)
        _save_to_dead_letter_queue(
            "run_audio_analysis", record_id, filename, str(exc),
            {"filepath": filepath},
        )


def _run_video(record_id: int, audio_filepath: str, filename: str):
    """Core logic — runs the video analysis pipeline."""
    from modules.analysis_pipeline import run_analysis_pipeline
    try:
        run_analysis_pipeline(
            record_id=record_id,
            filename=filename,
            audio_filepath=audio_filepath,
            upload_to_s3=False,
            delete_audio_after_transcription=True,
            source="video",
        )
    except Exception as exc:
        logger.error(f"[#{record_id}] Video analysis failed: {exc}", exc_info=True)
        _save_to_dead_letter_queue(
            "run_video_analysis", record_id, filename, str(exc),
            {"audio_filepath": audio_filepath},
        )


def _run_transcript(record_id: int, transcript: str, filename: str):
    """Core logic — runs the transcript analysis pipeline."""
    from modules.analysis_pipeline import run_analysis_pipeline
    try:
        run_analysis_pipeline(
            record_id=record_id,
            filename=filename,
            transcript=transcript,
            source="transcript",
        )
    except Exception as exc:
        logger.error(f"[#{record_id}] Transcript analysis failed: {exc}", exc_info=True)
        _save_to_dead_letter_queue(
            "run_transcript_analysis", record_id, filename, str(exc),
            {"transcript_length": len(transcript)},
        )


def _run_drive_import(record_id: int, transcript: str, filename: str):
    """Core logic — runs the drive import analysis pipeline."""
    from modules.analysis_pipeline import run_analysis_pipeline
    try:
        run_analysis_pipeline(
            record_id=record_id,
            filename=filename,
            transcript=transcript,
            source="google_drive",
        )
    except Exception as exc:
        logger.error(f"[#{record_id}] Drive import analysis failed: {exc}", exc_info=True)
        _save_to_dead_letter_queue(
            "run_drive_import_analysis", record_id, filename, str(exc),
            {"transcript_length": len(transcript)},
        )


# ── Register as Celery tasks if available, otherwise provide .delay() shim ────

try:
    from celery_app import celery_app, USE_CELERY

    if USE_CELERY and celery_app is not None:
        # Wrap as proper Celery tasks
        run_audio_analysis = celery_app.task(
            bind=True, name="tasks.run_audio_analysis", max_retries=2
        )(lambda self, *a, **kw: _run_audio(*a, **kw))

        run_video_analysis = celery_app.task(
            bind=True, name="tasks.run_video_analysis", max_retries=2
        )(lambda self, *a, **kw: _run_video(*a, **kw))

        run_transcript_analysis = celery_app.task(
            bind=True, name="tasks.run_transcript_analysis", max_retries=2
        )(lambda self, *a, **kw: _run_transcript(*a, **kw))

        run_drive_import_analysis = celery_app.task(
            bind=True, name="tasks.run_drive_import_analysis", max_retries=2
        )(lambda self, *a, **kw: _run_drive_import(*a, **kw))

    else:
        raise ImportError("Celery disabled")

except (ImportError, Exception):
    # Fallback: .delay() spawns a daemon thread (same as old behavior)
    class _ThreadTask:
        """Shim that mimics celery_task.delay() using threading."""
        def __init__(self, func):
            self._func = func
            self.__name__ = func.__name__

        def delay(self, *args, **kwargs):
            t = threading.Thread(
                target=self._func, args=args, kwargs=kwargs,
                daemon=True, name=f"task-{self._func.__name__}",
            )
            t.start()
            return t

        def __call__(self, *args, **kwargs):
            return self._func(*args, **kwargs)

    run_audio_analysis = _ThreadTask(_run_audio)
    run_video_analysis = _ThreadTask(_run_video)
    run_transcript_analysis = _ThreadTask(_run_transcript)
    run_drive_import_analysis = _ThreadTask(_run_drive_import)
    logger.info("Tasks using threading fallback (Celery unavailable)")
