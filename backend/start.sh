#!/bin/bash
set -e

# Single process: the FastAPI app. Analysis jobs and the periodic maintenance
# jobs arrive as HTTP calls from Cloud Tasks / Cloud Scheduler
# (POST /internal/tasks/* and /internal/maintenance/*), so there is no separate
# worker or beat process and nothing needs CPU between requests.
#
# Deploy with --max-instances=1: uploads are written to the instance's local
# disk and the queued job reads them back, so the job must run on the same
# instance. See CLOUD-TASKS-MIGRATION.md.
exec uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1
