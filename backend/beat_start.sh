#!/bin/bash
set -e

# Cloud Run requires something listening on $PORT even though beat itself
# never serves HTTP — see health_port.py.
python -c "
from health_port import start_health_server_in_background
import os
start_health_server_in_background(int(os.environ.get('PORT', '8000')))
import time
while True:
    time.sleep(3600)
" &

exec celery -A celery_app:celery_app beat --loglevel=info
