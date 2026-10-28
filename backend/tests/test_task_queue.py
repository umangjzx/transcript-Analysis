"""
Tests for the Cloud Tasks job dispatch that replaced Celery + Redis.

Covers: building/sending the Cloud Tasks HTTP task, the never-drop-a-job thread
fallback, the OIDC-protected /internal callbacks, and the retry policy (503 while
retries remain, FAILED + dead letter queue once they are spent).
"""

import json
import threading
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import task_queue
from api import internal_routes
from tasks import analysis_tasks
from tasks.analysis_tasks import QueuedTask, TaskSpec, TransientTaskFailure

SA = "tasks-invoker@proj.iam.gserviceaccount.com"
URL = "https://audio-safety.example.run.app"


@pytest.fixture
def cloudtasks_env(monkeypatch):
    for k, v in {
        "TASK_BACKEND": "cloudtasks",
        "TASKS_PROJECT": "proj",
        "TASKS_LOCATION": "us-central1",
        "TASKS_QUEUE": "rmsi-analysis",
        "TASKS_TARGET_URL": URL + "/",  # trailing slash must be tolerated
        "TASKS_INVOKER_SA": SA,
    }.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def fake_client(monkeypatch):
    client = MagicMock()
    created = MagicMock()
    created.name = "projects/proj/locations/us-central1/queues/rmsi-analysis/tasks/1"
    client.create_task.return_value = created
    monkeypatch.setattr(task_queue, "_client", client)
    return client


def _spec(core):
    return TaskSpec("run_audio_analysis", core, lambda p: {"filepath": p})


# ── Cloud Tasks dispatch ──────────────────────────────────────────────────────

class TestEnqueue:
    def test_task_targets_internal_endpoint_with_oidc(self, cloudtasks_env, fake_client):
        name = task_queue.enqueue_http_task("run_audio_analysis", [7, "/u/a.wav", "a.wav"])

        assert name.endswith("/tasks/1")
        req = fake_client.create_task.call_args.kwargs["request"]
        assert req["parent"] == "projects/proj/locations/us-central1/queues/rmsi-analysis"
        http = req["task"]["http_request"]
        assert http["url"] == f"{URL}/internal/tasks/run_audio_analysis"
        assert http["http_method"] == "POST"
        assert http["oidc_token"] == {"service_account_email": SA, "audience": URL}
        assert json.loads(http["body"]) == {"args": [7, "/u/a.wav", "a.wav"]}
        assert req["task"]["dispatch_deadline"] == {"seconds": 900}

    def test_oversized_payload_is_rejected(self, cloudtasks_env):
        with pytest.raises(ValueError):
            task_queue.build_task("run_transcript_analysis", [1, "x" * 1_000_000, "t.txt"])

    def test_missing_config_names_the_variable(self, cloudtasks_env, monkeypatch):
        monkeypatch.delenv("TASKS_QUEUE")
        with pytest.raises(RuntimeError, match="TASKS_QUEUE"):
            task_queue.enqueue_http_task("run_audio_analysis", [1, "p", "f"])


class TestQueuedTaskDelay:
    def test_cloudtasks_backend_enqueues_instead_of_running(self, cloudtasks_env, fake_client):
        ran = threading.Event()
        task = QueuedTask(_spec(lambda *a: ran.set()))

        task.delay(1, "p", "f")

        assert fake_client.create_task.call_count == 1
        assert not ran.wait(0.2), "job must not also run in-process"

    def test_enqueue_failure_falls_back_to_thread_not_dropped(self, cloudtasks_env, fake_client):
        fake_client.create_task.side_effect = ConnectionError("tasks API down")
        done = threading.Event()
        calls = []

        def core(record_id, payload, filename):
            calls.append((record_id, payload, filename))
            done.set()

        QueuedTask(_spec(core)).delay(42, "p", "meeting.wav")

        assert done.wait(2), "fallback thread never ran the job"
        assert calls == [(42, "p", "meeting.wav")]

    def test_thread_backend_runs_in_process(self, monkeypatch):
        monkeypatch.setenv("TASK_BACKEND", "thread")
        done = threading.Event()
        QueuedTask(_spec(lambda *a: done.set())).delay(1, "p", "f")
        assert done.wait(2)

    def test_thread_failure_marks_failed_and_saves_to_dlq(self, monkeypatch):
        monkeypatch.setenv("TASK_BACKEND", "thread")
        finished = threading.Event()

        def boom(*a):
            raise RuntimeError("disk full")

        with patch.object(analysis_tasks, "_mark_record_failed",
                          side_effect=lambda *a: None) as failed, \
             patch.object(analysis_tasks, "_save_to_dead_letter_queue",
                          side_effect=lambda *a, **k: finished.set()) as dlq:
            QueuedTask(_spec(boom)).delay(5, "p", "f.wav")
            assert finished.wait(2)

        failed.assert_called_once()
        assert failed.call_args.args[0] == 5
        dlq.assert_called_once()

    def test_direct_call_runs_core_synchronously(self):
        assert QueuedTask(_spec(lambda x: x * 2))(21) == 42


# ── Retry policy ──────────────────────────────────────────────────────────────

class TestRetryPolicy:
    def _transient(self):
        from modules.analysis_pipeline import TRANSIENT_DB_ERRORS
        return TRANSIENT_DB_ERRORS[0]("db blip")

    def test_success(self):
        assert _spec(lambda *a: None).execute(0, 1, "p", "f") == {"status": "ok"}

    def test_transient_failure_with_retries_left_asks_for_redelivery(self):
        def core(*a):
            raise self._transient()

        with pytest.raises(TransientTaskFailure):
            _spec(core).execute(0, 1, "p", "f")

    def test_transient_failure_after_last_retry_fails_for_good(self):
        def core(*a):
            raise self._transient()

        with patch.object(analysis_tasks, "_mark_record_failed") as failed, \
             patch.object(analysis_tasks, "_save_to_dead_letter_queue") as dlq:
            result = _spec(core).execute(analysis_tasks.MAX_RETRIES, 9, "/u/x.wav", "x.wav")

        assert result == {"status": "failed", "reason": "retries_exhausted"}
        failed.assert_called_once()
        assert dlq.call_args.args[:3] == ("run_audio_analysis", 9, "x.wav")
        assert dlq.call_args.args[4] == {"filepath": "/u/x.wav"}

    def test_permanent_persistence_error_is_not_retried(self):
        from modules.analysis_pipeline import CriticalPersistenceError

        def core(*a):
            raise CriticalPersistenceError("cannot save", transient=False)

        with patch.object(analysis_tasks, "_mark_record_failed") as failed, \
             patch.object(analysis_tasks, "_save_to_dead_letter_queue"):
            result = _spec(core).execute(0, 3, "p", "f")

        assert result["reason"] == "permanent_failure"
        failed.assert_called_once()


# ── /internal callbacks ───────────────────────────────────────────────────────

@pytest.fixture
def internal_client(cloudtasks_env):
    app = FastAPI()
    app.include_router(internal_routes.router)
    return TestClient(app)


def _auth(claims=None):
    """Patch OIDC verification to accept a token carrying `claims`."""
    claims = {"email": SA, "email_verified": True} if claims is None else claims
    return patch.object(internal_routes, "_verify_oidc", return_value=claims)


BEARER = {"Authorization": "Bearer signed.by.google"}


class TestInternalAuth:
    def test_no_token_is_401(self, internal_client):
        r = internal_client.post("/internal/tasks/run_audio_analysis", json={"args": [1, "p", "f"]})
        assert r.status_code == 401

    def test_bad_signature_is_401(self, internal_client):
        with patch.object(internal_routes, "_verify_oidc", side_effect=ValueError("bad")):
            r = internal_client.post("/internal/tasks/run_audio_analysis",
                                     json={"args": [1, "p", "f"]}, headers=BEARER)
        assert r.status_code == 401

    def test_other_service_account_is_403(self, internal_client):
        with _auth({"email": "someone-else@proj.iam.gserviceaccount.com", "email_verified": True}):
            r = internal_client.post("/internal/maintenance/reap-stuck-processing-jobs", headers=BEARER)
        assert r.status_code == 403

    def test_unverified_email_is_403(self, internal_client):
        with _auth({"email": SA, "email_verified": False}):
            r = internal_client.post("/internal/maintenance/reap-stuck-processing-jobs", headers=BEARER)
        assert r.status_code == 403

    def test_unconfigured_service_fails_closed(self, internal_client, monkeypatch):
        monkeypatch.delenv("TASKS_INVOKER_SA")
        with _auth():
            r = internal_client.post("/internal/maintenance/reap-stuck-processing-jobs", headers=BEARER)
        assert r.status_code == 503


class TestInternalTasks:
    def test_runs_the_registered_task(self, internal_client):
        spec = MagicMock()
        spec.execute.return_value = {"status": "ok"}
        with _auth(), patch.dict(analysis_tasks.TASKS, {"run_audio_analysis": spec}):
            r = internal_client.post(
                "/internal/tasks/run_audio_analysis",
                json={"args": [11, "/u/a.wav", "a.wav"]},
                headers={**BEARER, "X-CloudTasks-TaskRetryCount": "1"},
            )

        assert r.status_code == 200 and r.json() == {"status": "ok"}
        spec.execute.assert_called_once_with(1, 11, "/u/a.wav", "a.wav")

    def test_transient_failure_returns_503_so_cloud_tasks_retries(self, internal_client):
        spec = MagicMock()
        spec.execute.side_effect = TransientTaskFailure("db blip")
        with _auth(), patch.dict(analysis_tasks.TASKS, {"run_audio_analysis": spec}):
            r = internal_client.post("/internal/tasks/run_audio_analysis",
                                     json={"args": [1, "p", "f"]}, headers=BEARER)
        assert r.status_code == 503

    def test_unknown_task_is_404(self, internal_client):
        with _auth():
            r = internal_client.post("/internal/tasks/nope", json={"args": [1, "p", "f"]}, headers=BEARER)
        assert r.status_code == 404

    def test_wrong_arity_is_422_not_retried(self, internal_client):
        with _auth():
            r = internal_client.post("/internal/tasks/run_audio_analysis",
                                     json={"args": [1]}, headers=BEARER)
        assert r.status_code == 422

    def test_garbage_retry_header_counts_as_first_delivery(self, internal_client):
        spec = MagicMock()
        spec.execute.return_value = {"status": "ok"}
        with _auth(), patch.dict(analysis_tasks.TASKS, {"run_audio_analysis": spec}):
            internal_client.post("/internal/tasks/run_audio_analysis",
                                 json={"args": [1, "p", "f"]},
                                 headers={**BEARER, "X-CloudTasks-TaskRetryCount": "abc"})
        assert spec.execute.call_args.args[0] == 0


class TestInternalMaintenance:
    @pytest.mark.parametrize("job", ["reap-stuck-processing-jobs", "cleanup-old-uploads", "poll-google-drive"])
    def test_each_scheduler_job_is_routed(self, internal_client, job):
        fn = MagicMock(return_value={"ran": job})
        with _auth(), patch.object(internal_routes, "_maintenance_jobs", return_value={job: fn}):
            r = internal_client.post(f"/internal/maintenance/{job}", headers=BEARER)
        assert r.status_code == 200 and r.json() == {"ran": job}
        fn.assert_called_once_with()

    def test_unknown_job_is_404(self, internal_client):
        with _auth():
            r = internal_client.post("/internal/maintenance/format-disk", headers=BEARER)
        assert r.status_code == 404

    def test_real_job_table_has_all_three(self):
        assert set(internal_routes._maintenance_jobs()) == {
            "reap-stuck-processing-jobs", "cleanup-old-uploads", "poll-google-drive",
        }
