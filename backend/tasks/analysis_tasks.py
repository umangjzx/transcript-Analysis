"""
Background tasks for the analysis pipeline.

Each task is dispatched with `<task>.delay(record_id, payload, filename)`:
  TASK_BACKEND=cloudtasks  -> a Cloud Tasks HTTP task that calls back into
                              POST /internal/tasks/<name> (api/internal_routes.py)
  TASK_BACKEND=thread      -> a daemon thread in this process (dev / tests)

Retries: the callback endpoint answers 503 for a transient failure while retries
remain, and Cloud Tasks re-delivers with backoff per the queue's retry config.
Once the budget is spent the record is marked FAILED and the job is saved to the
dead letter queue, so nothing is silently lost.

Dead Letter Queue:
  Failed tasks (after max retries) are persisted to MongoDB collection
  'dead_letter_queue' for manual inspection and replay.
"""

import logging
import os
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# Ensure the backend root (/app in Docker) is on sys.path so that
# deferred imports like "from modules.analysis_pipeline import ..."
# resolve correctly regardless of how the process was started.
_APP_ROOT = str(Path(__file__).resolve().parent.parent)
if _APP_ROOT not in sys.path:
    sys.path.insert(0, _APP_ROOT)

import task_queue

logger = logging.getLogger(__name__)

# Redeliveries allowed after the first attempt. Keep in step with the Cloud Tasks
# queue's maxAttempts (= MAX_RETRIES + 1); see CLOUD-TASKS-MIGRATION.md.
MAX_RETRIES = int(os.getenv("TASK_MAX_RETRIES", "2"))


class TransientTaskFailure(Exception):
    """A failure worth retrying; the callback endpoint turns it into a 503."""


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
    sweep picks it up.
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


# ── Task registry ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class TaskSpec:
    """One background job. Every job takes (record_id, payload, filename)."""

    name: str
    core: Callable[[int, Any, str], None]
    dlq_args: Callable[[Any], dict]  # payload -> what to store in the DLQ entry

    def execute(self, retry_count: int, record_id: int, payload: Any, filename: str) -> dict:
        """Run the job once under the retry policy.

        Returns a result dict when the job is finished (success, or failed for
        good and recorded). Raises TransientTaskFailure when it should be
        re-delivered.
        """
        from modules.analysis_pipeline import TRANSIENT_DB_ERRORS, CriticalPersistenceError

        try:
            self.core(record_id, payload, filename)
            return {"status": "ok"}
        except (TRANSIENT_DB_ERRORS + (CriticalPersistenceError,)) as exc:
            if isinstance(exc, CriticalPersistenceError) and not exc.transient:
                logger.error(f"[#{record_id}] {self.name} failed permanently: {exc}")
                return self._give_up(record_id, filename, payload, exc, "permanent_failure")

            if retry_count < MAX_RETRIES:
                logger.warning(
                    f"[#{record_id}] {self.name} hit a transient failure "
                    f"(retry {retry_count}/{MAX_RETRIES}), letting Cloud Tasks "
                    f"re-deliver: {exc}"
                )
                raise TransientTaskFailure(str(exc)) from exc

            logger.error(
                f"[#{record_id}] {self.name} still failing after "
                f"{MAX_RETRIES + 1} attempts — giving up: {exc}"
            )
            return self._give_up(record_id, filename, payload, exc, "retries_exhausted")

    def _give_up(self, record_id, filename, payload, exc, reason) -> dict:
        _mark_record_failed(record_id, str(exc))
        _save_to_dead_letter_queue(
            self.name, record_id, filename, str(exc), self.dlq_args(payload),
        )
        return {"status": "failed", "reason": reason}


TASKS = {
    spec.name: spec
    for spec in (
        TaskSpec("run_audio_analysis", _run_audio, lambda p: {"filepath": p}),
        TaskSpec("run_video_analysis", _run_video, lambda p: {"audio_filepath": p}),
        TaskSpec("run_transcript_analysis", _run_transcript,
                 lambda p: {"transcript_length": len(p)}),
        TaskSpec("run_drive_import_analysis", _run_drive_import,
                 lambda p: {"transcript_length": len(p)}),
    )
}


class QueuedTask:
    """Callable with a Celery-style `.delay()` so call sites did not change.

    .delay() hands the job to Cloud Tasks. If that is unavailable or rejects the
    task it falls back to an in-process thread rather than dropping the job: a
    broker error here would otherwise be raised from inside a FastAPI
    BackgroundTask *after* the response was sent, leaving the record PROCESSING
    forever. Calling the object directly runs the core function synchronously.
    """

    def __init__(self, spec: TaskSpec):
        self.spec = spec
        self.__name__ = spec.name

    def delay(self, *args):
        if task_queue.use_cloud_tasks():
            try:
                return task_queue.enqueue_http_task(self.spec.name, list(args))
            except Exception as exc:
                logger.error(
                    f"[{self.spec.name}] Cloud Tasks enqueue failed ({exc}) — "
                    f"running via threading fallback instead of dropping the job.",
                    exc_info=True,
                )
        t = threading.Thread(
            target=self._run_in_thread, args=args,
            daemon=True, name=f"task-{self.spec.name}",
        )
        t.start()
        return t

    def _run_in_thread(self, *args):
        """In-process execution with no queue underneath it.

        The pipeline re-raises transient failures so a queue can retry them, but
        there is no retry here — an exception would just kill the thread and
        leave the record PROCESSING with nothing in the DLQ. Close it out
        explicitly instead.
        """
        try:
            self.spec.core(*args)
        except Exception as exc:
            record_id = args[0] if args else None
            logger.error(
                f"[#{record_id}] {self.spec.name} failed in-process "
                f"(no retry available): {exc}",
                exc_info=True,
            )
            if record_id is not None:
                _mark_record_failed(record_id, str(exc))
                _save_to_dead_letter_queue(
                    self.spec.name, record_id,
                    args[2] if len(args) > 2 else "unknown",
                    str(exc), {"via": "threading_fallback"},
                )

    def __call__(self, *args, **kwargs):
        return self.spec.core(*args, **kwargs)


run_audio_analysis = QueuedTask(TASKS["run_audio_analysis"])
run_video_analysis = QueuedTask(TASKS["run_video_analysis"])
run_transcript_analysis = QueuedTask(TASKS["run_transcript_analysis"])
run_drive_import_analysis = QueuedTask(TASKS["run_drive_import_analysis"])
