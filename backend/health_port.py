"""
Minimal HTTP listener for Cloud Run's container contract.

Cloud Run requires a service's container to listen on $PORT and respond,
or the revision is marked unhealthy and torn down — even for a container
whose real job (a Celery worker or beat scheduler) never serves HTTP
traffic. This starts a trivial 200-OK responder in a daemon thread so
those services pass Cloud Run's startup/liveness probes without needing
a real app mounted.
"""

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *args):
        pass  # keep this out of the regular logs — it's just probe traffic


def start_health_server_in_background(port: int) -> None:
    """Starts the listener on a daemon thread; safe to call more than once
    per process (e.g. from a signal that can fire multiple times) since a
    second bind attempt just fails and is swallowed."""
    def _serve():
        try:
            server = ThreadingHTTPServer(("0.0.0.0", port), _HealthHandler)
            server.serve_forever()
        except OSError:
            pass  # already bound — another call in this process got there first
        except Exception as e:
            logger.warning(f"Health listener failed to start on port {port}: {e}")

    threading.Thread(target=_serve, daemon=True, name="health-listener").start()
