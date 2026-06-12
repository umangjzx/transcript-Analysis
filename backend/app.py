"""
Audio Safety Analyzer - FastAPI Application

Fixes applied:
- CORS locked to configured origins (env: ALLOWED_ORIGINS)
- File size limit enforced (env: MAX_UPLOAD_MB, default 200 MB)
- Secure filename — UUID on disk, original name in DB
- Request correlation ID middleware (X-Request-ID header)
- JWT authentication — credentials stored in MongoDB, bcrypt-hashed
- API key middleware kept for backward-compat with direct script access
- Stuck-job recovery on startup (PROCESSING > 30 min ? FAILED)
- ML classifier warm-up on startup when ENABLE_ML_CLASSIFIER=true
- Upload file cleanup daemon (env: UPLOAD_TTL_HOURS, default 24)
- TTL in-memory cache for /history and /analytics/summary (60 s)
- /history paginated (skip/limit), returns created_at
- /report/{id} returns timeline field
- JSON columns: ORM handles serialisation — no manual json.dumps/loads
- print() replaced with logger throughout
- versioned router (/api/v1/*) registered
"""

import os
import uuid
import logging
import time
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS, APP_URL
from auth import get_current_user

# -- Logging -------------------------------------------------------------------

os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

# Use structured JSON logging in production, human-readable in development
from modules.structured_logging import setup_logging
setup_logging()

logger = logging.getLogger(__name__)

# -- Config --------------------------------------------------------------------

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# API key — set API_KEY in .env to enable auth; leave blank to disable (dev).
API_KEY: str = os.getenv("API_KEY", "")

# Upload TTL — audio files older than this are deleted. 0 = disabled.
UPLOAD_TTL_HOURS: int = int(os.getenv("UPLOAD_TTL_HOURS", "24"))

# LLM summarizer — set ENABLE_LLM_SUMMARY=false to skip (faster, no API calls).
# Note: this is checked at runtime via the function below, not cached
def _get_enable_llm_summary() -> bool:
    """Read ENABLE_LLM_SUMMARY from environment (allows .env changes without restart)."""
    return os.getenv("ENABLE_LLM_SUMMARY", "true").strip().lower() == "true"

# -- TTL cache -----------------------------------------------------------------
# Use the shared Redis-backed cache from modules.cache
from modules.cache import TTLCache as _TTLCache_cls

_cache = _TTLCache_cls(ttl=60, name="app")

# -- Database init -------------------------------------------------------------

try:
    from database.mongo import get_mongo_db as _mongo_init
    _mongo_init()  # establishes connection + creates indexes on first call
    logger.info("MongoDB connection initialised")
except Exception as _e:
    logger.warning(f"MongoDB init warning (non-fatal): {_e}")

# -- FastAPI app ---------------------------------------------------------------

app = FastAPI(
    title="Audio Safety Analyzer",
    description="Advanced audio safety analysis system for detecting grooming patterns.",
    version="2.1.0",
)

# -- Request ID middleware -----------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIDMiddleware)

# -- Content-Security-Policy headers -------------------------------------------

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self'; "
            "style-src 'self'; "
            "img-src 'self' data: blob:; "
            "font-src 'self'; "
            "connect-src 'self' ws: wss:; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        return response

app.add_middleware(SecurityHeadersMiddleware)

# -- API Key auth middleware ----------------------------------------------------

_PUBLIC_PATHS = {"/", "/health", "/docs", "/openapi.json", "/redoc"}


class APIKeyMiddleware(BaseHTTPMiddleware):
    """
    Enforce X-API-Key header when API_KEY is set in .env.
    Leave API_KEY blank to disable (local dev).
    """
    async def dispatch(self, request: Request, call_next):
        if not API_KEY:
            return await call_next(request)
        if request.url.path in _PUBLIC_PATHS or request.url.path.startswith("/docs"):
            return await call_next(request)
        if request.headers.get("X-API-Key", "") != API_KEY:
            return JSONResponse(
                status_code=status.HTTP_401_UNAUTHORIZED,
                content={"error": "Unauthorized", "detail": "Missing or invalid X-API-Key header."},
            )
        return await call_next(request)

app.add_middleware(APIKeyMiddleware)

# -- CORS ----------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -- Rate Limiting -------------------------------------------------------------

from middleware.rate_limiter import RateLimitMiddleware
app.add_middleware(RateLimitMiddleware)

# -- Global exception handler --------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logger.error(f"[{request_id}] Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "detail": "An unexpected error occurred. Please try again later.",
            "request_id": request_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )

# -- Pipeline config (used by startup warm-up only) ----------------------------

_enable_ml = os.getenv("ENABLE_ML_CLASSIFIER", "true").lower() == "true"

# -- Startup / shutdown --------------------------------------------------------

@app.on_event("startup")
async def startup_event():
    # ── Fail-fast: JWT_SECRET must be set in production ───────────────────────
    _env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    _jwt_secret = os.getenv("JWT_SECRET", "")
    if _env in ("production", "prod", "staging") and not _jwt_secret:
        logger.critical(
            "FATAL: JWT_SECRET is not set. The server refuses to start in "
            f"'{_env}' mode without a JWT signing secret. "
            "Set JWT_SECRET in your environment or .env file."
        )
        import sys
        sys.exit(1)

    logger.info("=" * 70)
    logger.info("Audio Safety Analyzer v2.1 Starting...")
    logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")
    logger.info(f"Max upload size: {MAX_UPLOAD_BYTES // (1024*1024)} MB")
    logger.info(f"API key auth: {'ENABLED' if API_KEY else 'DISABLED (set API_KEY in .env)'}")
    logger.info(f"ML classifier: {'ENABLED' if _enable_ml else 'DISABLED'}")
    logger.info("=" * 70)

    # Stuck-job recovery — mark PROCESSING jobs older than 30 min as FAILED
    try:
        from database.mongo import (
            get_mongo_db as _get_db,
            save_processing_status,
            update_meeting_status,
        )
        _mdb = _get_db()
        if _mdb is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
            stuck_cursor = _mdb["processing_status"].find(
                {"status": "PROCESSING", "started_at": {"$lt": cutoff}},
                {"meeting_id": 1, "_id": 0},
            )
            stuck_ids = [d["meeting_id"] for d in stuck_cursor]
            for mid in stuck_ids:
                save_processing_status(
                    mid, "FAILED", "error",
                    error="Processing timed out — server was restarted mid-analysis.",
                )
                update_meeting_status(mid, "FAILED")
                logger.warning(f"Stuck-job recovery: marked meeting #{mid} as FAILED")
    except Exception as _e:
        logger.warning(f"Stuck-job recovery failed: {_e}")

    # ML warm-up — load model into memory before first real request
    if _enable_ml:
        import threading as _threading
        def _warmup():
            try:
                logger.info("ML classifier warm-up: loading model...")
                from modules.grooming_detector import GroomingDetector
                _detector = GroomingDetector(min_confidence_threshold=0.3, enable_ml_classifier=True)
                _detector.analyze_transcript("warm-up ping", speaker_aware=False)
                logger.info("ML classifier warm-up complete")
            except Exception as _e:
                logger.warning(f"ML warm-up failed (non-fatal): {_e}")
        _threading.Thread(target=_warmup, daemon=True).start()

    # Chatbot warm-up — pre-load SentenceTransformer + ChromaDB so the first
    # import doesn't pay the cold-start cost mid-request (~4s on CPU).
    def _warmup_chatbot():
        try:
            logger.info("Chatbot warm-up: loading SentenceTransformer + ChromaDB...")
            from modules.chatbot import _get_embedding_model, _get_collection
            _get_embedding_model()
            _get_collection()
            logger.info("Chatbot warm-up complete")
        except Exception as _e:
            logger.warning(f"Chatbot warm-up failed (non-fatal): {_e}")

    import threading as _threading_chatbot
    _threading_chatbot.Thread(target=_warmup_chatbot, daemon=True).start()

    # Upload cleanup — scheduled via Celery Beat (see celery_app.py)
    # The old threading daemon is removed; use:
    #   celery -A celery_app beat --loglevel=info
    # with a schedule entry for tasks.cleanup_old_uploads every hour.
    if UPLOAD_TTL_HOURS > 0:
        logger.info(f"Upload cleanup configured (TTL={UPLOAD_TTL_HOURS}h) — run via Celery Beat")

    logger.info("Service initialized successfully")

    # Run database migrations
    try:
        from database.migrations import run_migrations
        migration_result = run_migrations()
        if migration_result["applied"]:
            logger.info(f"Database migrations applied: {migration_result['applied']}")
        if migration_result["failed"]:
            logger.error(f"Database migrations FAILED: {migration_result['failed']}")
    except Exception as _e:
        logger.warning(f"Database migration check failed (non-fatal): {_e}")

    # Auto-start Drive watcher — start directly in-process for development
    # In production, use Celery Beat (celery -A celery_app worker --beat --loglevel=info)
    from modules.drive_watcher import AUTO_WATCH as _auto_watch, start_watcher as _start_watcher
    if _auto_watch:
        _started = _start_watcher()
        if _started:
            logger.info("Google Drive auto-watcher STARTED (in-process polling thread)")
        else:
            logger.info("Google Drive auto-watcher already running")

    # WebSocket progress queue — process events from background threads
    import asyncio
    from modules.websocket_manager import init_progress_queue, process_progress_queue
    init_progress_queue(asyncio.get_event_loop())
    asyncio.create_task(process_progress_queue())
    logger.info("WebSocket progress queue initialized")


@app.on_event("shutdown")
async def shutdown_event():
    """Graceful shutdown — clean up resources."""
    logger.info("Audio Safety Analyzer shutting down...")

    # Stop Drive watcher thread
    from modules.drive_watcher import stop_watcher as _stop_watcher
    try:
        _stop_watcher()
    except Exception:
        pass

    # Stop WebSocket progress queue
    from modules.websocket_manager import _progress_queue
    if _progress_queue:
        try:
            _progress_queue.put_nowait(None)  # Signal to stop
        except Exception:
            pass

    # Close MongoDB connection pool
    try:
        from database.mongo import _client as mongo_client
        if mongo_client:
            mongo_client.close()
            logger.info("MongoDB connection pool closed")
    except Exception as e:
        logger.warning(f"MongoDB shutdown error: {e}")

    # Close Redis connections
    try:
        from modules.cache import _get_redis
        r = _get_redis()
        if r:
            r.close()
            logger.info("Redis connection closed")
    except Exception as e:
        logger.warning(f"Redis shutdown error: {e}")

    # Reset circuit breakers
    try:
        from modules.circuit_breaker import ollama_breaker, s3_breaker
        ollama_breaker.reset()
        s3_breaker.reset()
    except Exception:
        pass

    logger.info("Graceful shutdown complete")

# -- Register versioned router -------------------------------------------------

from api.audio_analysis_routes import router as v1_router  # noqa: E402
from api.google_drive_routes import router as gdrive_router  # noqa: E402
from api.auth_routes import router as auth_router  # noqa: E402
from api.notification_routes import router as notify_router  # noqa: E402
from api.analytics_routes import router as analytics_router  # noqa: E402
from api.upload_routes import router as upload_router  # noqa: E402
from api.report_routes import router as report_router  # noqa: E402
from api.feedback_routes import router as feedback_router  # noqa: E402

app.include_router(v1_router)
app.include_router(gdrive_router)
app.include_router(auth_router)
app.include_router(notify_router)
app.include_router(analytics_router)
app.include_router(upload_router)
app.include_router(report_router)
app.include_router(feedback_router)

# -- WebSocket endpoint for real-time progress ---------------------------------

from fastapi import WebSocket, WebSocketDisconnect as _WSD  # noqa: E402
from modules.websocket_manager import manager as ws_manager  # noqa: E402

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket, report_id: int = None):
    """WebSocket endpoint for real-time analysis progress updates."""
    await ws_manager.connect(websocket, report_id)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                import json as _json
                msg = _json.loads(data)
                if "subscribe" in msg:
                    rid = int(msg["subscribe"])
                    async with ws_manager._lock:
                        if rid not in ws_manager._subscriptions:
                            ws_manager._subscriptions[rid] = set()
                        ws_manager._subscriptions[rid].add(websocket)
            except Exception:
                pass
    except _WSD:
        await ws_manager.disconnect(websocket)
    except Exception:
        await ws_manager.disconnect(websocket)

if _enable_ml:
    logger.info("ML classifier ENABLED (distilbert-mnli)")
else:
    logger.info("ML classifier DISABLED — set ENABLE_ML_CLASSIFIER=true in .env to enable")


# -- Minimal root routes (kept in app.py) --------------------------------------

@app.get("/")
def home():
    return {"message": "Audio Safety Analyzer Running", "version": "2.1.0"}


@app.get("/health")
def health(request: Request):
    """
    Health check endpoint.

    Returns basic status for unauthenticated requests (load balancer probes).
    Returns full service topology only for authenticated admin requests.
    """
    import shutil
    from database.mongo import ping as mongo_ping

    # Basic health — always public (needed for Docker/LB health checks)
    mongo_ok = mongo_ping()
    try:
        disk = shutil.disk_usage(UPLOAD_FOLDER)
        disk_ok = disk.free > 1 * 1024**3
    except Exception:
        disk_ok = True

    all_healthy = mongo_ok and disk_ok
    basic_response = {
        "status": "healthy" if all_healthy else "degraded",
        "service": "Audio Safety Analyzer",
        "version": "2.1.0",
    }

    # Check if request is authenticated — only then expose detailed topology
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("access_token")

    if not token or not os.getenv("JWT_SECRET", ""):
        return basic_response

    # Validate token before returning sensitive info
    try:
        from auth import decode_access_token
        decode_access_token(token)
    except Exception:
        return basic_response

    # Authenticated — return full topology details
    from modules.s3_storage import ping as s3_ping

    try:
        disk = shutil.disk_usage(UPLOAD_FOLDER)
        disk_free_gb = round(disk.free / (1024**3), 2)
        disk_total_gb = round(disk.total / (1024**3), 2)
    except Exception:
        disk_free_gb = None
        disk_total_gb = None

    whisper_status = {"available": False, "model": None}
    try:
        from modules.transcriber import get_whisper_model_info
        whisper_info = get_whisper_model_info()
        whisper_status = {"available": True, **whisper_info}
    except ImportError:
        try:
            import whisper
            whisper_status = {"available": True, "model": "base"}
        except ImportError:
            whisper_status = {"available": False, "error": "whisper not installed"}
    except Exception as e:
        whisper_status = {"available": False, "error": str(e)}

    chromadb_status = {"available": False}
    try:
        from modules.chatbot import _get_collection
        col = _get_collection()
        chromadb_status = {"available": col is not None, "collection_count": col.count() if col else 0}
    except Exception as e:
        chromadb_status = {"available": False, "error": str(e)}

    ollama_status = {"available": False}
    try:
        import requests as _req
        ollama_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        resp = _req.get(f"{ollama_url}/api/tags", timeout=3)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            ollama_status = {"available": True, "models": len(models)}
        else:
            ollama_status = {"available": False, "error": f"HTTP {resp.status_code}"}
    except Exception as e:
        ollama_status = {"available": False, "error": str(e)}

    redis_status = {"available": False}
    try:
        from modules.cache import _get_redis
        r = _get_redis()
        redis_status = {"available": r is not None}
    except Exception as e:
        redis_status = {"available": False, "error": str(e)}

    return {
        **basic_response,
        "ml_classifier": {"enabled": _enable_ml},
        "s3": s3_ping(),
        "mongodb": {"connected": mongo_ok},
        "whisper": whisper_status,
        "chromadb": chromadb_status,
        "ollama": ollama_status,
        "redis": redis_status,
        "disk": {"ok": disk_ok, "free_gb": disk_free_gb, "total_gb": disk_total_gb},
    }


@app.post("/collect")
@app.options("/collect")
def collect_telemetry():
    """Silently accept and discard Vite analytics telemetry."""
    return {"status": "ok"}

