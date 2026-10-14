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
#
# Polled with kill -0 rather than `wait -n`: the PID-argument form of
# `wait -n` needs bash 5.1+, and the fallback `wait` blocks until ALL children
# exit — so a segfaulted worker went unnoticed while uvicorn/beat kept running
# and every queued analysis sat in PROCESSING. On top of liveness, ping the
# worker so a hung (not dead) worker also recycles the instance.
ping_failures=0
tick=0
while true; do
  for pid in $CELERY_WORKER_PID $CELERY_BEAT_PID $UVICORN_PID; do
    if ! kill -0 "$pid" 2>/dev/null; then
      echo "Process $pid exited."
      break 2
    fi
  done
  tick=$((tick + 1))
  # Every ~60s, after a 5-minute grace for model warm-up.
  if [ $((tick % 12)) -eq 0 ] && [ "$tick" -gt 60 ]; then
    if timeout 20 celery -A celery_app:celery_app inspect ping --timeout 15 >/dev/null 2>&1; then
      ping_failures=0
    else
      ping_failures=$((ping_failures + 1))
      echo "Celery worker ping failed ($ping_failures/3)"
      if [ "$ping_failures" -ge 3 ]; then
        echo "Celery worker unresponsive."
        break
      fi
    fi
  fi
  sleep 5
done

echo "A process exited. Shutting down..."
kill $CELERY_WORKER_PID $CELERY_BEAT_PID $UVICORN_PID 2>/dev/null || true
wait 2>/dev/null
exit 1
