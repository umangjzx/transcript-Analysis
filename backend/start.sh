#!/bin/bash
set -e

echo "Starting Celery worker in background..."
celery -A celery_app worker --loglevel=info --concurrency=6 --pool=threads &
CELERY_PID=$!

echo "Starting FastAPI server..."
uvicorn app:app --host 0.0.0.0 --port 8000 --workers 1 &
UVICORN_PID=$!

# Wait for either process to exit
wait -n $CELERY_PID $UVICORN_PID 2>/dev/null || wait $CELERY_PID $UVICORN_PID

# If one exits, kill the other and exit
echo "A process exited. Shutting down..."
kill $CELERY_PID $UVICORN_PID 2>/dev/null || true
wait 2>/dev/null
exit 1
