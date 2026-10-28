# Replacing Celery + Redis with Cloud Tasks + Cloud Scheduler

Branch: `feat/cloud-tasks-replace-celery`. **Not deployed.** Nothing in GCP has been
created or changed; this document is the runbook for doing that.

## Why

On 17 Oct 2026 the Upstash Redis plan hit its 500,000-request limit
(`max requests limit exceeded. Limit: 500000, Usage: 500000`). From then on the
Celery worker could not connect (it crash-looped, 500+ `exit(1)` restarts that day) and
Celery beat could not publish, so analyses could not be queued. Celery workers poll
the broker constantly (roughly one `BRPOP` per second, about 86,000 a day), which is
why a small Redis plan runs out, and why the worker also needed an always-on CPU
(about $63/month) just to wait for jobs.

## What changed

| Before | After |
|---|---|
| Celery worker thread pool + Redis broker | Cloud Tasks queue. Each job is an HTTP task that calls back into this service at `POST /internal/tasks/<name>` |
| Celery beat (reaper, cleanup, Drive poll) | Cloud Scheduler jobs that call `POST /internal/maintenance/<job>` |
| `start.sh` ran worker + beat + API and a watchdog loop | `start.sh` runs just the API |
| Retries via `self.retry()` | The endpoint answers 503 for a transient failure; Cloud Tasks re-delivers with the queue's backoff. After the last attempt the record is marked FAILED and the job goes to the `dead_letter_queue` collection (unchanged behavior) |
| Redis cache + rate limiter | Optional. With `REDIS_URL` unset both are in-memory (the service is one instance, so this is exact) |

Call sites are unchanged: `run_audio_analysis.delay(record_id, path, filename)` etc.
`delay()` now enqueues a Cloud Task, and if Cloud Tasks rejects the enqueue it falls
back to an in-process thread rather than dropping the job (same safety net as before).

New files: `backend/task_queue.py`, `backend/api/internal_routes.py`,
`backend/tests/test_task_queue.py`. Removed: `celery_app.py`, `celery_beat_schedule.py`,
`worker_start.sh`, `beat_start.sh`, `health_port.py`, `tests/test_celery_fallback.py`, the
`redis` / `celery-worker` / `celery-beat` services in `docker-compose.yml`, and `celery` /
`redis` from `requirements.txt` (added `google-cloud-tasks==2.20.0`). `purge_celery_queue.py`
is untracked and was left alone; it has no use once Redis is gone.

Tests: unit suite 214 passed / 3 skipped (was 190 / 3; +27 new, -3 deleted), integration 10 passed / 1 skipped.
Verified against the real app: `/internal/*` rejects a missing token and a forged token
with 401 (real `google-auth` verification), and `/health` still works.
The task payload was also checked against the real `google-cloud-tasks==2.20.0` request
types (nothing was sent). **Not verified:** a real Cloud Tasks round trip, which needs the
GCP resources below.

## Configuration

| Variable | Value |
|---|---|
| `TASK_BACKEND` | `cloudtasks` in production. `thread` (the default) runs jobs in-process, for local dev and tests |
| `TASKS_PROJECT` | GCP project id |
| `TASKS_LOCATION` | queue region, `us-central1` |
| `TASKS_QUEUE` | `rmsi-analysis` |
| `TASKS_TARGET_URL` | this service's own URL (also the OIDC audience), no trailing slash |
| `TASKS_INVOKER_SA` | service account Cloud Tasks/Scheduler sign tokens as; the endpoints accept only this identity |
| `TASKS_DISPATCH_DEADLINE_SECONDS` | optional, default 900 |
| `TASK_MAX_RETRIES` | optional, default 2. Keep equal to the queue's `max-attempts` minus 1 |

If `TASKS_INVOKER_SA` or `TASKS_TARGET_URL` is unset, every `/internal/*` request is refused (fail closed).
Remove `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `USE_CELERY` from
`backend/env.yaml` (harmless if left, but they no longer do anything).

## One-time GCP setup

These are the commands to run. **Review the project and service names first.**

```bash
PROJECT=melodywings
REGION=us-central1
SERVICE=audio-safety-backend
SA_NAME=rmsi-tasks-invoker
SA_EMAIL=$SA_NAME@$PROJECT.iam.gserviceaccount.com

gcloud services enable cloudtasks.googleapis.com cloudscheduler.googleapis.com --project $PROJECT

# Identity that Cloud Tasks / Cloud Scheduler sign their calls as
gcloud iam service-accounts create $SA_NAME --project $PROJECT \
  --display-name "RMSI Cloud Tasks and Scheduler invoker"

# The service's own runtime identity creates tasks and acts as the invoker SA
RUNTIME_SA=$(gcloud run services describe $SERVICE --region $REGION --project $PROJECT \
  --format="value(spec.template.spec.serviceAccountName)")
gcloud projects add-iam-policy-binding $PROJECT \
  --member "serviceAccount:$RUNTIME_SA" --role roles/cloudtasks.enqueuer
gcloud iam service-accounts add-iam-policy-binding $SA_EMAIL --project $PROJECT \
  --member "serviceAccount:$RUNTIME_SA" --role roles/iam.serviceAccountUser

# Only needed if the service is not already publicly invokable
gcloud run services add-iam-policy-binding $SERVICE --region $REGION --project $PROJECT \
  --member "serviceAccount:$SA_EMAIL" --role roles/run.invoker

# Queue: 3 attempts (1 + TASK_MAX_RETRIES), 30s -> 240s backoff, at most 2 jobs at once
gcloud tasks queues create rmsi-analysis --location $REGION --project $PROJECT \
  --max-attempts=3 --min-backoff=30s --max-backoff=240s --max-doublings=3 \
  --max-concurrent-dispatches=2
```

### Scheduler jobs (3 jobs are within Cloud Scheduler's free tier)

```bash
URL=$(gcloud run services describe $SERVICE --region $REGION --project $PROJECT --format="value(status.url)")

gcloud scheduler jobs create http rmsi-reap-stuck --location $REGION --project $PROJECT \
  --schedule="*/10 * * * *" --http-method=POST \
  --uri="$URL/internal/maintenance/reap-stuck-processing-jobs" \
  --oidc-service-account-email=$SA_EMAIL --oidc-token-audience=$URL

gcloud scheduler jobs create http rmsi-cleanup-uploads --location $REGION --project $PROJECT \
  --schedule="0 * * * *" --http-method=POST \
  --uri="$URL/internal/maintenance/cleanup-old-uploads" \
  --oidc-service-account-email=$SA_EMAIL --oidc-token-audience=$URL
```

Drive polling is the third job (`poll-google-drive`). The old schedule ran it every 2
minutes when `DRIVE_AUTO_WATCH=true`. The app also has an in-process watcher thread
(`modules/drive_watcher.py`) that starts when `DRIVE_AUTO_WATCH` is on. **Use one or the
other, not both.** A scheduler poll every 2 minutes also keeps the instance awake
around the clock, which defeats scale-to-zero. If you need it, prefer `*/5`:

```bash
gcloud scheduler jobs create http rmsi-poll-drive --location $REGION --project $PROJECT \
  --schedule="*/5 * * * *" --http-method=POST \
  --uri="$URL/internal/maintenance/poll-google-drive" \
  --oidc-service-account-email=$SA_EMAIL --oidc-token-audience=$URL
```

## Deploy

Order matters: create the GCP resources above, then deploy, then verify.

```bash
gcloud run deploy audio-safety-backend --source ./backend --region us-central1 \
  --env-vars-file ./backend/env.yaml \
  --max-instances=1 --concurrency=8 --timeout=900 \
  --cpu 2 --memory 4Gi --cpu-throttling
```

Add `TASK_BACKEND`, `TASKS_*` to `env.yaml` first (and `TASKS_TARGET_URL` is only known
once the service exists; set it with `gcloud run services update ... --update-env-vars`
if this is the first deploy).

Choices to make at deploy time:

- **`--max-instances=1` is required, not a tuning choice.** Uploads are written to the
  instance's local disk and the queued job reads them back. A second instance would not
  have the file. Fixing that properly means writing uploads to a Cloud Storage bucket.
- **`--cpu-throttling` (the default) is correct now.** The job runs inside the HTTP
  request that Cloud Tasks holds open, so CPU is allocated for its whole duration. This is
  what removes the always-on CPU charge.
- **`--min-instances`:** `0` is cheapest, but the first upload after an idle period waits
  for a cold start (the models take about 15-20 s to load). `1` avoids that and costs the
  idle rate for CPU and memory all month (a rough estimate is $20-35 depending on memory).
- **`--memory`:** keep 4 Gi until you have watched peak memory under real load. The README
  and `app.py` both record a July 2026 out-of-memory outage; 2 Gi is not safe to assume.
- **`--concurrency=8` with the queue's `--max-concurrent-dispatches=2`** leaves request
  slots free for API traffic while analyses run. `modules/ml_lock.py` serializes the native
  ML calls, so extra concurrent analyses would only queue up and hold memory.

## Verify after deploying

1. `GET /health` returns 200.
2. Unauthenticated `POST $URL/internal/maintenance/reap-stuck-processing-jobs` returns **401**.
3. Run a scheduler job once: `gcloud scheduler jobs run rmsi-reap-stuck --location $REGION`
   and confirm a 200 in the service logs.
4. Upload a short test transcript through the app and watch it go PROCESSING -> COMPLETE.
   In `gcloud tasks queues describe rmsi-analysis --location $REGION` the task count should
   rise and then drop back to 0.
5. Confirm no Redis or `max requests limit` errors appear in the logs.
6. After a day, check Billing -> Reports by SKU: the always-on **Services CPU
   (Instance-based billing)** line should stop growing.

## Rollback

- **Quickest, no external infrastructure:** set `TASK_BACKEND=thread` and redeploy with
  `--no-cpu-throttling`. Jobs then run in-process as background threads (the original
  threading mode). It works without Cloud Tasks but needs always-on CPU again.
- Rolling Cloud Run traffic back to an earlier revision returns to the Celery build, which
  needs a working Redis. That is only useful once Upstash is upgraded or reset.

## Known limits

- **Local disk and restarts.** If the instance restarts (a deploy, a crash) while an
  uploaded file is queued, the file is gone, the retry fails permanently and the job lands
  in the dead letter queue. Same exposure as before, but now worth fixing with Cloud Storage.
- **Instance death mid-run.** Cloud Tasks re-delivers the task. If every attempt is lost, the
  record stays PROCESSING until the stuck-job reaper (runs every 10 minutes) marks it FAILED
  once it is more than 30 minutes old.
- **No result backend.** Nothing reads task results (status lives in MongoDB), so none is kept.
- **Time limits.** The old Celery soft/hard limits (10-11 minutes) are replaced by the Cloud Tasks dispatch deadline (15 minutes) and the Cloud Run request timeout (`--timeout=900`).
- **Docs not yet updated:** the README's Mermaid architecture diagrams still draw Celery and Redis.
