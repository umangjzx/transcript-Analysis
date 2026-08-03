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
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

# Ensure the backend root (/app in Docker) is on sys.path so that
# deferred imports like "from modules.analysis_pipeline import ..."
# resolve correctly in Celery forked worker processes.
_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

logger = logging.getLogger(__name__)


def _is_transient(exc: Exception) -> bool:
    """Whether this failure is worth another attempt rather than the DLQ."""
    from modules.analysis_pipeline import TRANSIENT_DB_ERRORS, CriticalPersistenceError

    if isinstance(exc, CriticalPersistenceError):
        return exc.transient
    return isinstance(exc, TRANSIENT_DB_ERRORS)


def _mark_record_failed(record_id: int, error: str) -> None:
    """Mark a record FAILED after retries are exhausted.

    run_analysis_pipeline() deliberately leaves transient failures PROCESSING so
    a retry can still finish the job. Once we stop retrying, someone has to
    close the record out or it stays PROCESSING until the 30-minute stuck-job
    sweep in app.py picks it up.
    """
    try:
        from database.mongo import save_processing_status, update_meeting_status
        save_processing_status(
            record_id, "FAILED", "error",
            completed_at=datetime.now(timezone.utc),
            error=error[:2000],
        )
        update_meeting_status(record_id, "FAILED")
    except Exception as exc:
        logger.error(
            f"[#{record_id}] Could not mark record FAILED after retry "
            f"exhaustion: {exc}"
        )


def _run_with_retry(task, core_fn, task_name, record_id, filename, dlq_args, *call_args):
    """Run a pipeline task, retrying transient infrastructure failures.

    Previously every task carried max_retries=2 but nothing ever called
    self.retry(), because run_analysis_pipeline() caught its own exceptions and
    returned normally — Celery never saw a failure, so the retry budget was
    dead config. The pipeline now re-raises transient errors; this is what
    actually spends that budget, with backoff so a reconnecting Atlas cluster
    isn't hammered.
    """
    from modules.analysis_pipeline import TRANSIENT_DB_ERRORS, CriticalPersistenceError

    try:
        core_fn(*call_args)
    except (TRANSIENT_DB_ERRORS + (CriticalPersistenceError,)) as exc:
        if isinstance(exc, CriticalPersistenceError) and not exc.transient:
            logger.error(f"[#{record_id}] {task_name} failed permanently: {exc}")
            _mark_record_failed(record_id, str(exc))
            _save_to_dead_letter_queue(task_name, record_id, filename, str(exc), dlq_args)
            return

        attempt = task.request.retries + 1
        countdown = min(30 * (2 ** task.request.retries), 240)  # 30s, 60s, 120s…
        try:
            logger.warning(
                f"[#{record_id}] {task_name} hit a transient failure "
                f"(attempt {attempt}/{task.max_retries + 1}), retrying in "
                f"{countdown}s: {exc}"
            )
            raise task.retry(exc=exc, countdown=countdown)
        except task.MaxRetriesExceededError:
            logger.error(
                f"[#{record_id}] {task_name} still failing after "
                f"{task.max_retries + 1} attempts — giving up: {exc}"
            )
            _mark_record_failed(record_id, str(exc))
            _save_to_dead_letter_queue(task_name, record_id, filename, str(exc), dlq_args)


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
        if _is_transient(exc):
            raise
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
        if _is_transient(exc):
            raise
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
        if _is_transient(exc):
            raise
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
        if _is_transient(exc):
            raise
        logger.error(f"[#{record_id}] Drive import analysis failed: {exc}", exc_info=True)
        _save_to_dead_letter_queue(
            "run_drive_import_analysis", record_id, filename, str(exc),
            {"transcript_length": len(transcript)},
        )


# ── Register as Celery tasks if available, otherwise provide .delay() shim ────

class _CeleryTaskWithFallback:
    """Wraps a Celery task's .delay(), falling back to an in-process background
    thread if the broker rejects the enqueue (e.g. Redis is over its memory or
    connection limit). Without this, a broker error at enqueue time is raised
    from inside a FastAPI BackgroundTask *after* the response has already been
    sent — the client sees "PROCESSING" but the job was never queued and the
    record is stuck forever. Falling back keeps analysis working even when
    Redis is unavailable, the same way the rate limiter and cache already do."""

    def __init__(self, celery_task, func):
        self._task = celery_task
        self._func = func
        self.__name__ = func.__name__

    def delay(self, *args, **kwargs):
        try:
            return self._task.delay(*args, **kwargs)
        except Exception as exc:
            logger.error(
                f"[{self._func.__name__}] Celery enqueue failed ({exc}) — "
                f"running via threading fallback instead of dropping the job.",
                exc_info=True,
            )
            t = threading.Thread(
                target=self._run_in_thread, args=args, kwargs=kwargs,
                daemon=True, name=f"task-fallback-{self._func.__name__}",
            )
            t.start()
            return t

    def _run_in_thread(self, *args, **kwargs):
        """Fallback execution with no Celery underneath it.

        The pipeline re-raises transient failures so Celery can retry them, but
        there is no retry here — an exception would just kill the thread and
        leave the record PROCESSING with nothing in the DLQ. Close it out
        explicitly instead.
        """
        try:
            self._func(*args, **kwargs)
        except Exception as exc:
            record_id = args[0] if args else None
            logger.error(
                f"[#{record_id}] {self._func.__name__} failed in threading "
                f"fallback (no retry available): {exc}",
                exc_info=True,
            )
            if record_id is not None:
                _mark_record_failed(record_id, str(exc))
                _save_to_dead_letter_queue(
                    self._func.__name__, record_id,
                    args[2] if len(args) > 2 else "unknown",
                    str(exc), {"via": "threading_fallback"},
                )

    def __call__(self, *args, **kwargs):
        return self._func(*args, **kwargs)


try:
    from celery_app import celery_app, USE_CELERY

    if USE_CELERY and celery_app is not None:
        # Wrap as proper Celery tasks (using named functions instead of lambdas
        # to avoid Celery's head_from_fun SyntaxError with bound tasks)
        @celery_app.task(bind=True, name="tasks.run_audio_analysis", max_retries=2,
                         soft_time_limit=600, time_limit=660)
        def run_audio_analysis(self, record_id, filepath, filename):
            return _run_with_retry(
                self, _run_audio, "run_audio_analysis", record_id, filename,
                {"filepath": filepath},
                record_id, filepath, filename,
            )

        @celery_app.task(bind=True, name="tasks.run_video_analysis", max_retries=2,
                         soft_time_limit=600, time_limit=660)
        def run_video_analysis(self, record_id, audio_filepath, filename):
            return _run_with_retry(
                self, _run_video, "run_video_analysis", record_id, filename,
                {"audio_filepath": audio_filepath},
                record_id, audio_filepath, filename,
            )

        @celery_app.task(bind=True, name="tasks.run_transcript_analysis", max_retries=2,
                         soft_time_limit=300, time_limit=360)
        def run_transcript_analysis(self, record_id, transcript, filename):
            return _run_with_retry(
                self, _run_transcript, "run_transcript_analysis", record_id, filename,
                {"transcript_length": len(transcript)},
                record_id, transcript, filename,
            )

        @celery_app.task(bind=True, name="tasks.run_drive_import_analysis", max_retries=2,
                         soft_time_limit=300, time_limit=360)
        def run_drive_import_analysis(self, record_id, transcript, filename):
            return _run_with_retry(
                self, _run_drive_import, "run_drive_import_analysis", record_id, filename,
                {"transcript_length": len(transcript)},
                record_id, transcript, filename,
            )

        run_audio_analysis = _CeleryTaskWithFallback(run_audio_analysis, _run_audio)
        run_video_analysis = _CeleryTaskWithFallback(run_video_analysis, _run_video)
        run_transcript_analysis = _CeleryTaskWithFallback(run_transcript_analysis, _run_transcript)
        run_drive_import_analysis = _CeleryTaskWithFallback(run_drive_import_analysis, _run_drive_import)

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
