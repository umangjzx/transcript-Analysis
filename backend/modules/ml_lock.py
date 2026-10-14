"""
Process-wide lock for native-code ML work (torch / transformers /
sentence-transformers / ChromaDB).

The Celery worker runs a thread pool (--pool=threads). These libraries are not
safe to drive from several threads at once: concurrent model loads and
inference calls segfault the whole worker process (Cloud Run: "Uncaught
signal: 11"), which stalls every queued analysis. Serialising the native calls
behind one re-entrant lock keeps threaded concurrency for everything else
(Mongo, S3, email, PDF) while the ML section runs one thread at a time.
"""
import functools
import threading

ML_LOCK = threading.RLock()


def serialized(fn):
    """Run ``fn`` while holding ML_LOCK."""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with ML_LOCK:
            return fn(*args, **kwargs)
    return wrapper
