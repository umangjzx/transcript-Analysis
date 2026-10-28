"""
Background-job dispatch: Cloud Tasks in production, in-process threads locally.

Replaces the Celery + Redis broker. A job is a Cloud Tasks HTTP task that calls
back into this same Cloud Run service at /internal/tasks/<name> (see
api/internal_routes.py), authenticated with a Google-signed OIDC token. Cloud
Tasks owns queueing, retries and backoff, so nothing here needs a long-lived
worker process or an always-allocated CPU.

TASK_BACKEND selects the dispatcher:
  cloudtasks  production. Needs the TASKS_* variables below.
  thread      (default) run the job in a daemon thread of this process. Used by
              local development and the test suite.

Cloud Tasks variables:
  TASKS_PROJECT       GCP project id
  TASKS_LOCATION      queue region, e.g. us-central1
  TASKS_QUEUE         queue name
  TASKS_TARGET_URL    this service's own https URL, no trailing slash. It is also
                      the OIDC audience the callback endpoint verifies.
  TASKS_INVOKER_SA    service account Cloud Tasks signs the OIDC token as; the
                      callback endpoint accepts only this identity.
  TASKS_DISPATCH_DEADLINE_SECONDS  per-attempt deadline (default 900)
"""

import json
import logging
import os
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# Cloud Tasks caps an HTTP task at 1 MiB; stay clear of it so the failure mode
# is a clean fallback here rather than an opaque API error.
MAX_BODY_BYTES = 900_000

# Cloud Tasks accepts 15s-30min for HTTP targets; 15 min sits above the longest
# pipeline run (the old Celery hard limit for audio was 11 min).
DEFAULT_DISPATCH_DEADLINE_SECONDS = 900

_client = None  # lazily created CloudTasksClient; tests inject a fake


def use_cloud_tasks() -> bool:
    return os.getenv("TASK_BACKEND", "thread").strip().lower() == "cloudtasks"


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is not set (required when TASK_BACKEND=cloudtasks)")
    return value


def _get_client():
    global _client
    if _client is None:
        from google.cloud import tasks_v2  # lazy: not needed in thread mode

        _client = tasks_v2.CloudTasksClient()
    return _client


def build_task(task_name: str, args: List[Any]) -> dict:
    """The Cloud Tasks task for one job. Pure, so it can be unit-tested."""
    target = _required("TASKS_TARGET_URL").rstrip("/")
    body = json.dumps({"args": args}).encode("utf-8")
    if len(body) > MAX_BODY_BYTES:
        raise ValueError(
            f"{task_name} payload is {len(body)} bytes, over the "
            f"{MAX_BODY_BYTES}-byte Cloud Tasks limit"
        )
    deadline = int(
        os.getenv("TASKS_DISPATCH_DEADLINE_SECONDS", DEFAULT_DISPATCH_DEADLINE_SECONDS)
    )
    return {
        "http_request": {
            "http_method": "POST",
            "url": f"{target}/internal/tasks/{task_name}",
            "headers": {"Content-Type": "application/json"},
            "body": body,
            "oidc_token": {
                "service_account_email": _required("TASKS_INVOKER_SA"),
                "audience": target,
            },
        },
        "dispatch_deadline": {"seconds": deadline},
    }


def enqueue_http_task(task_name: str, args: List[Any]) -> str:
    """Create the Cloud Tasks task and return its server-assigned name."""
    parent = "projects/{}/locations/{}/queues/{}".format(
        _required("TASKS_PROJECT"),
        _required("TASKS_LOCATION"),
        _required("TASKS_QUEUE"),
    )
    created = _get_client().create_task(
        request={"parent": parent, "task": build_task(task_name, args)}
    )
    return getattr(created, "name", "") or ""
