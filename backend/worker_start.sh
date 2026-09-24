#!/bin/bash
set -e

# Standalone worker service. The health listener also self-starts from
# celery_app.py's celeryd_after_setup signal, but that only fires once
# celery has finished initializing — start it here too so Cloud Run's
# startup probe has something to hit immediately.
python -c "
from health_port import start_health_server_in_background
import os
start_health_server_in_background(int(os.environ.get('PORT', '8000')))
import time
while True:
    time.sleep(3600)
" &

exec celery -A celery_app:celery_app worker --loglevel=info --pool=threads --concurrency="${CELERY_CONCURRENCY:-6}"
