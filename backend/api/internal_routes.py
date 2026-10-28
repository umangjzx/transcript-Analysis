"""
Internal endpoints called by Google Cloud, never by browsers or API clients.

  POST /internal/tasks/<name>         Cloud Tasks delivering a background job
  POST /internal/maintenance/<job>    Cloud Scheduler triggering a periodic job

Both are authenticated by a Google-signed OIDC token: Cloud Tasks / Scheduler
sign it as TASKS_INVOKER_SA with the service URL (TASKS_TARGET_URL) as audience,
and this module checks the signature, the audience and the service account.
If either variable is unset the endpoints refuse every request (fail closed).

The handlers are plain `def` so Starlette runs them in its thread pool: a job
can run for minutes and must not block the event loop. They answer 200 for a
finished job (success or failed-for-good), and a non-2xx for a transient failure
so Cloud Tasks re-delivers it with backoff.
"""

import logging
import os
from typing import Any, List

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal", tags=["internal"], include_in_schema=False)


class TaskBody(BaseModel):
    args: List[Any] = Field(default_factory=list)


def _verify_oidc(token: str, audience: str) -> dict:
    """Validate a Google-signed ID token and return its claims. Raises on any problem."""
    from google.auth.transport import requests as google_requests
    from google.oauth2 import id_token

    return id_token.verify_oauth2_token(token, google_requests.Request(), audience=audience)


def require_cloud_caller(authorization: str = Header(default="")) -> dict:
    invoker = os.getenv("TASKS_INVOKER_SA", "").strip()
    audience = os.getenv("TASKS_TARGET_URL", "").strip().rstrip("/")
    if not invoker or not audience:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Internal task endpoints are not configured.",
        )

    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token.")

    try:
        claims = _verify_oidc(token.strip(), audience)
    except Exception as exc:
        logger.warning("Internal call rejected: bad OIDC token (%s)", exc)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token.")

    if claims.get("email") != invoker or not claims.get("email_verified", False):
        logger.warning("Internal call rejected: unexpected caller %s", claims.get("email"))
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Caller not allowed.")
    return claims


def _retry_count(request: Request) -> int:
    """How many times Cloud Tasks has already retried this task (0 on first delivery)."""
    try:
        return max(0, int(request.headers.get("X-CloudTasks-TaskRetryCount", "0")))
    except ValueError:
        return 0


@router.post("/tasks/{task_name}")
def run_task(
    task_name: str,
    body: TaskBody,
    request: Request,
    _caller: dict = Depends(require_cloud_caller),
):
    from tasks.analysis_tasks import TASKS, TransientTaskFailure

    spec = TASKS.get(task_name)
    if spec is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown task.")
    if len(body.args) != 3:
        # Not retryable: a malformed task will never become valid.
        raise HTTPException(
            422,
            "Expected args: [record_id, payload, filename].",
        )

    record_id, payload, filename = body.args
    try:
        return spec.execute(_retry_count(request), record_id, payload, filename)
    except TransientTaskFailure as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)[:500])


def _maintenance_jobs() -> dict:
    from tasks.maintenance_tasks import (
        cleanup_old_uploads,
        poll_google_drive,
        reap_stuck_processing_jobs,
    )

    return {
        "reap-stuck-processing-jobs": reap_stuck_processing_jobs,
        "cleanup-old-uploads": cleanup_old_uploads,
        "poll-google-drive": poll_google_drive,
    }


@router.post("/maintenance/{job}")
def run_maintenance(job: str, _caller: dict = Depends(require_cloud_caller)):
    fn = _maintenance_jobs().get(job)
    if fn is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown job.")
    return fn()
