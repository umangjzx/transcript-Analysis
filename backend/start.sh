#!/bin/bash
set -e

# Combined API + Celery worker + Celery beat, one Cloud Run service.
#
# Cloud Run only allocates real CPU to a container while it's handling a
# request, which starved a worker thread the moment the triggering upload
# request returned — analyses stalled or died mid-run with nothing left to
# mark them FAILED. That's fixed at the deploy level, not in this script:
# deploy this service with --no-cpu-throttling --min-instances=1
# --max-instances=1 (see README's Cloud Run section) so the instance always
# has real CPU and never scales beyond one.
#
# --max-instances=1 is also what makes it safe to run beat in here too —
# beat must never run as more than one instance at a time or scheduled
# tasks fire multiple times; pinning this service to exactly one instance
# guarantees that.
echo "Starting Celery worker..."
celery -A celery_app:celery_app worker --loglevel=info --pool=threads --concurrency="${CELERY_CONCURRENCY:-6}" &
CELERY_WORKER_PID=$!

echo "Starting Celery beat..."
celery -A celery_app:celery_app beat --loglevel=info &
CELERY_BEAT_PID=$!

echo "Starting FastAPI server..."
uvicorn app:app --host 0.0.0.0 --port "${PORT:-8000}" --workers 1 &
UVICORN_PID=$!

# If any one of the three exits, none of them can do their job properly on
# their own — kill the rest and exit non-zero so Cloud Run restarts the
# instance clean, rather than limping along with e.g. no worker.
wait -n $CELERY_WORKER_PID $CELERY_BEAT_PID $UVICORN_PID 2>/dev/null \
  || wait $CELERY_WORKER_PID $CELERY_BEAT_PID $UVICORN_PID

echo "A process exited. Shutting down..."
kill $CELERY_WORKER_PID $CELERY_BEAT_PID $UVICORN_PID 2>/dev/null || true
wait 2>/dev/null
exit 1
