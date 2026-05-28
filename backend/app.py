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
import json
import uuid
import logging
import time
from typing import Optional, Dict, Any
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, UploadFile, File, HTTPException, status, BackgroundTasks, Request, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS, APP_URL
from database.mongo import (
    save_full_analysis, save_processing_status,
    update_meeting_status, audit_log, log_alert,
    delete_meeting_data,
    # Read helpers — used by all GET routes (SQLite-free)
    list_meetings, get_full_report, get_analytics_summary as mongo_analytics,
    get_meeting, get_evidence as mongo_get_evidence,
    update_s3_urls, update_pdf_path,
    next_meeting_id,
)
from modules.transcriber import transcribe_audio
from modules.grooming_detector import GroomingDetector
from modules.evidence_extractor import extract_evidence
from modules.risk_scorer import WeightedRiskScorer
from modules.severity_classifier import classify_severity
from modules.summarizer import generate_summary
from modules.stats import generate_stats
from modules.llm_summarizer import generate_llm_summary
from modules.report_generator import generate_pdf_report
from modules.chatbot import store_transcript, answer_question, delete_transcript
from modules.email_notifier import send_alert_email, send_summary_email, should_auto_alert
from modules.s3_storage import upload_audio as s3_upload_audio, upload_pdf_report as s3_upload_pdf, delete_file as s3_delete_file
from modules.virus_scanner import scan_file as virus_scan_file
from auth import get_current_user, authenticate_user, create_access_token

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
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
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

# -- Pipeline components -------------------------------------------------------

_enable_ml = os.getenv("ENABLE_ML_CLASSIFIER", "true").lower() == "true"
grooming_detector = GroomingDetector(
    min_confidence_threshold=0.3,
    enable_ml_classifier=_enable_ml,
)
risk_scorer = WeightedRiskScorer()

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
        from database.mongo import get_mongo_db as _get_db
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
                grooming_detector.analyze_transcript("warm-up ping", speaker_aware=False)
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
app.include_router(v1_router)
app.include_router(gdrive_router)
app.include_router(auth_router)
app.include_router(notify_router)
app.include_router(analytics_router)

# -- WebSocket endpoint for real-time progress ---------------------------------

from fastapi import WebSocket, WebSocketDisconnect as _WSD  # noqa: E402
from modules.websocket_manager import manager as ws_manager, process_progress_queue, init_progress_queue  # noqa: E402

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket, report_id: int = None):
    """WebSocket endpoint for real-time analysis progress updates."""
    await ws_manager.connect(websocket, report_id)
    try:
        while True:
            # Keep connection alive, handle client messages
            data = await websocket.receive_text()
            # Client can send {"subscribe": report_id} to subscribe to specific reports
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

@app.on_event("startup")
async def _start_ws_queue():
    """Start the WebSocket progress queue processor."""
    import asyncio
    init_progress_queue(asyncio.get_event_loop())
    asyncio.create_task(process_progress_queue())

if _enable_ml:
    logger.info("ML classifier ENABLED (distilbert-mnli)")
else:
    logger.info("ML classifier DISABLED — set ENABLE_ML_CLASSIFIER=true in .env to enable")

# -- Request models ------------------------------------------------------------

class ChatRequest(BaseModel):
    report_id: int
    question: str


class NotifyRequest(BaseModel):
    recipients: Optional[list] = None


# -- Background pipeline (Celery tasks) ----------------------------------------

def process_audio_background(record_id: int, filepath: str, filename: str):
    """Dispatch audio analysis to Celery worker."""
    from tasks.analysis_tasks import run_audio_analysis
    run_audio_analysis.delay(record_id, filepath, filename)


def process_video_background(record_id: int, audio_filepath: str, filename: str):
    """Dispatch video analysis to Celery worker."""
    from tasks.analysis_tasks import run_video_analysis
    run_video_analysis.delay(record_id, audio_filepath, filename)


def process_transcript_background(record_id: int, transcript: str, filename: str):
    """Dispatch transcript analysis to Celery worker."""
    from tasks.analysis_tasks import run_transcript_analysis
    run_transcript_analysis.delay(record_id, transcript, filename)


# -- Routes --------------------------------------------------------------------

# -- Auth models ---------------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


# -- Auth endpoints ------------------------------------------------------------

@app.post("/auth/login")
def login(body: LoginRequest):
    """
    Authenticate with username + password.
    Returns a signed JWT in an httpOnly cookie and in the response body.
    """
    from auth import authenticate_user, create_access_token
    user = authenticate_user(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    token = create_access_token(user["username"], user.get("role", "admin"))
    audit_log("login_success", details={"username": user["username"]})
    logger.info(f"Login: '{user['username']}' authenticated successfully.")

    response = JSONResponse(content={
        "access_token": token,
        "token_type": "bearer",
        "username": user["username"],
        "role": user.get("role", "admin"),
    })
    # Set JWT in httpOnly cookie — secure, not accessible via JavaScript
    from auth import JWT_EXPIRE_MINUTES
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,
        secure=os.getenv("COOKIE_SECURE", "false").lower() == "true",
        samesite="lax",
        max_age=JWT_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response


@app.post("/auth/logout")
def logout():
    """
    Logout — clears the httpOnly cookie and logs for audit.
    """
    audit_log("logout")
    response = JSONResponse(content={"message": "Logged out successfully."})
    response.delete_cookie(key="access_token", path="/")
    return response


@app.get("/auth/me")
def me(current_user: dict = Depends(get_current_user)):
    """Return the currently authenticated user's info."""
    return current_user

@app.get("/")
def home():
    return {"message": "Audio Safety Analyzer Running", "version": "2.1.0"}


@app.get("/health")
def health():
    import shutil
    from modules.s3_storage import ping as s3_ping
    from database.mongo import ping as mongo_ping

    # Disk space check
    try:
        disk = shutil.disk_usage(UPLOAD_FOLDER)
        disk_free_gb = round(disk.free / (1024**3), 2)
        disk_total_gb = round(disk.total / (1024**3), 2)
        disk_ok = disk.free > 1 * 1024**3  # At least 1 GB free
    except Exception:
        disk_free_gb = None
        disk_total_gb = None
        disk_ok = True  # Can't check, assume OK

    # Whisper model check
    whisper_status = {"available": False, "model": None}
    try:
        from modules.transcriber import get_whisper_model_info
        whisper_info = get_whisper_model_info()
        whisper_status = {"available": True, **whisper_info}
    except ImportError:
        # Function doesn't exist yet — check if whisper is importable
        try:
            import whisper
            whisper_status = {"available": True, "model": "base"}
        except ImportError:
            whisper_status = {"available": False, "error": "whisper not installed"}
    except Exception as e:
        whisper_status = {"available": False, "error": str(e)}

    # ChromaDB check
    chromadb_status = {"available": False}
    try:
        from modules.chatbot import _get_collection
        col = _get_collection()
        chromadb_status = {"available": col is not None, "collection_count": col.count() if col else 0}
    except Exception as e:
        chromadb_status = {"available": False, "error": str(e)}

    # Ollama LLM check
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

    # Redis check
    redis_status = {"available": False}
    try:
        from modules.cache import _get_redis
        r = _get_redis()
        redis_status = {"available": r is not None}
    except Exception as e:
        redis_status = {"available": False, "error": str(e)}

    all_healthy = mongo_ping() and disk_ok
    return {
        "status": "healthy" if all_healthy else "degraded",
        "service": "Audio Safety Analyzer",
        "ml_classifier": {"enabled": _enable_ml},
        "s3": s3_ping(),
        "mongodb": {"connected": mongo_ping()},
        "whisper": whisper_status,
        "chromadb": chromadb_status,
        "ollama": ollama_status,
        "redis": redis_status,
        "disk": {
            "ok": disk_ok,
            "free_gb": disk_free_gb,
            "total_gb": disk_total_gb,
        },
    }


@app.post("/collect")
@app.options("/collect")
def collect_telemetry():
    """
    Vite analytics endpoint — silently accept and discard telemetry.
    Prevents 400 errors in logs when frontend tries to send analytics data.
    """
    return {"status": "ok"}


_AUDIO_CHUNK_SIZE = 1024 * 1024  # 1 MB chunks — stream to disk, never hold full file in memory


@app.post("/analyze")
async def analyze_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    # Disk space pre-check before accepting upload
    from modules.disk_space_checker import check_disk_space
    disk_check = check_disk_space()
    if not disk_check["ok"]:
        raise HTTPException(
            status_code=507,
            detail=f"Insufficient disk space: {disk_check['free_mb']:.0f} MB available, "
                   f"need {disk_check['required_mb']} MB.",
        )

    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{extension}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    # Stream upload to disk in chunks — prevents OOM on concurrent large uploads
    safe_disk_name = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filepath = os.path.join(UPLOAD_FOLDER, safe_disk_name)
    file_size = 0
    try:
        with open(filepath, "wb") as buffer:
            while True:
                chunk = await file.read(size=_AUDIO_CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_BYTES:
                    buffer.close()
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        try:
            os.remove(filepath)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    # Virus scan
    scan_result = virus_scan_file(filepath)
    if not scan_result["safe"]:
        os.remove(filepath)
        raise HTTPException(
            status_code=422,
            detail=f"File rejected: virus detected ({scan_result['threat']})",
        )

    original_filename = file.filename or safe_disk_name

    # Allocate a new meeting ID from MongoDB counter and create the initial record
    from database.mongo import save_meeting_metadata as _save_meta
    record_id = next_meeting_id()
    _save_meta(
        meeting_id=record_id,
        filename=original_filename,
        file_size_bytes=file_size,
        status="PROCESSING",
    )

    background_tasks.add_task(process_audio_background, record_id, filepath, original_filename)
    audit_log("file_uploaded", meeting_id=record_id, user_action="upload",
              details={"filename": original_filename, "size_bytes": file_size})
    logger.info(f"[#{record_id}] Upload accepted: {original_filename} ({file_size//1024} KB)")

    return {"id": record_id, "filename": original_filename,
            "status": "PROCESSING", "message": "Analysis started in background"}


MAX_VIDEO_UPLOAD_BYTES = int(os.getenv("MAX_VIDEO_UPLOAD_MB", "500")) * 1024 * 1024
_VIDEO_CHUNK_SIZE = 1024 * 1024  # 1 MB chunks — never loads full file into memory


@app.post("/analyze/video")
async def analyze_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """
    Upload a video file, extract its audio track, then run the full analysis pipeline.
    Supported formats: .mp4, .mkv, .avi, .mov, .webm, .flv, .wmv

    The video is streamed to disk in 1 MB chunks — the full file is never held
    in memory. The video file is deleted immediately after audio extraction.
    Only the transcript text and analysis results are stored.
    """
    # Disk space pre-check
    from modules.disk_space_checker import check_disk_space
    disk_check = check_disk_space()
    if not disk_check["ok"]:
        raise HTTPException(
            status_code=507,
            detail=f"Insufficient disk space: {disk_check['free_mb']:.0f} MB available, "
                   f"need {disk_check['required_mb']} MB.",
        )

    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format '{extension}'. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}",
        )

    safe_disk_name = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    video_filepath = os.path.join(UPLOAD_FOLDER, safe_disk_name)
    original_filename = file.filename or safe_disk_name

    # Stream to disk in chunks — avoids loading 500 MB into memory
    file_size = 0
    try:
        with open(video_filepath, "wb") as buffer:
            while True:
                chunk = await file.read(size=_VIDEO_CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_VIDEO_UPLOAD_BYTES:
                    # Exceeded limit — clean up and reject
                    buffer.close()
                    try:
                        os.remove(video_filepath)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size for video is {MAX_VIDEO_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        try:
            os.remove(video_filepath)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save video file: {str(e)}")

    # Extract audio from video to a WAV file
    audio_disk_name = f"{uuid.uuid4().hex}.wav"
    audio_filepath = os.path.join(UPLOAD_FOLDER, audio_disk_name)

    # Virus scan the video file before processing
    scan_result = virus_scan_file(video_filepath)
    if not scan_result["safe"]:
        try:
            os.remove(video_filepath)
        except Exception:
            pass
        raise HTTPException(
            status_code=422,
            detail=f"File rejected: virus detected ({scan_result['threat']})",
        )

    try:
        from modules.transcriber import extract_audio_from_video
        extract_audio_from_video(video_filepath, audio_filepath)
    except Exception as e:
        try:
            os.remove(video_filepath)
        except Exception:
            pass
        raise HTTPException(
            status_code=422,
            detail=f"Could not extract audio from video: {str(e)}",
        )

    # Remove the original video file immediately — never stored
    try:
        os.remove(video_filepath)
        logger.info(f"Video file deleted after extraction: {video_filepath}")
    except Exception as _e:
        logger.warning(f"Could not delete video file: {_e}")

    from database.mongo import save_meeting_metadata as _save_meta
    record_id = next_meeting_id()
    _save_meta(
        meeting_id=record_id,
        filename=original_filename,
        file_size_bytes=file_size,
        status="PROCESSING",
    )

    background_tasks.add_task(process_video_background, record_id, audio_filepath, original_filename)
    audit_log("video_uploaded", meeting_id=record_id, user_action="upload",
              details={"filename": original_filename, "size_bytes": file_size})
    logger.info(f"[#{record_id}] Video upload accepted, audio extracted: {original_filename} ({file_size // 1024} KB)")

    return {"id": record_id, "filename": original_filename,
            "status": "PROCESSING", "message": "Video audio extracted, analysis started in background"}


@app.post("/analyze/transcript")
async def analyze_transcript_text(background_tasks: BackgroundTasks, request: Request):
    """
    Submit a plain-text transcript and run the analysis pipeline,
    skipping the transcription step.

    Accepts either:
      - JSON body:  { "transcript": "...", "filename": "optional-name.txt" }
      - File upload: multipart/form-data with a .txt file field named "file"
    """
    content_type = request.headers.get("content-type", "")

    # -- Multipart file upload (.txt) ------------------------------------------
    if "multipart/form-data" in content_type:
        from fastapi import Form
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file is None:
            raise HTTPException(status_code=400, detail="No file field found in form data.")

        original_filename = uploaded_file.filename or "transcript_input.txt"
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in (".txt",):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Only .txt files are accepted for transcript upload.",
            )

        raw_bytes = await uploaded_file.read()
        if len(raw_bytes) > 10 * 1024 * 1024:  # 10 MB limit for text files
            raise HTTPException(status_code=413, detail="Text file too large. Maximum 10 MB.")

        try:
            transcript_text = raw_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            try:
                transcript_text = raw_bytes.decode("latin-1").strip()
            except Exception:
                raise HTTPException(status_code=422, detail="Could not decode file as text. Ensure it is UTF-8 encoded.")

        if not transcript_text:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")

    # -- JSON body -------------------------------------------------------------
    else:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Request body must be valid JSON.")

        transcript_text = body.get("transcript", "").strip()
        if not transcript_text:
            raise HTTPException(status_code=400, detail="'transcript' field is required and must not be empty.")
        original_filename = body.get("filename", "transcript_input.txt").strip() or "transcript_input.txt"

    if len(transcript_text) > 500_000:
        raise HTTPException(status_code=413, detail="Transcript too large. Maximum 500,000 characters.")

    # ── Transcript input validation ───────────────────────────────────────────
    # Reject binary content (high ratio of non-printable characters)
    _non_printable = sum(
        1 for ch in transcript_text[:10000]
        if ord(ch) < 32 and ch not in ('\n', '\r', '\t')
    )
    if _non_printable > len(transcript_text[:10000]) * 0.05:
        raise HTTPException(
            status_code=422,
            detail="Input appears to be binary data, not a text transcript. "
                   "Please submit plain text (UTF-8).",
        )

    # Reject lines exceeding max length (likely binary or minified data)
    _MAX_LINE_LENGTH = 10_000
    for i, line in enumerate(transcript_text.split('\n')[:100], 1):
        if len(line) > _MAX_LINE_LENGTH:
            raise HTTPException(
                status_code=422,
                detail=f"Line {i} exceeds maximum length of {_MAX_LINE_LENGTH} characters. "
                       f"Transcripts should contain natural-language text with line breaks.",
            )
    # ──────────────────────────────────────────────────────────────────────────

    from database.mongo import save_meeting_metadata as _save_meta
    record_id = next_meeting_id()
    _save_meta(
        meeting_id=record_id,
        filename=original_filename,
        file_size_bytes=len(transcript_text.encode("utf-8")),
        status="PROCESSING",
    )

    background_tasks.add_task(
        process_transcript_background, record_id, transcript_text, original_filename
    )
    audit_log("transcript_submitted", meeting_id=record_id, user_action="upload",
              details={"filename": original_filename, "char_count": len(transcript_text)})
    logger.info(f"[#{record_id}] Transcript submitted: {original_filename} ({len(transcript_text)} chars)")

    return {"id": record_id, "filename": original_filename,
            "status": "PROCESSING", "message": "Transcript received, analysis started in background"}


@app.get("/report/{report_id}/status")
def get_report_status(report_id: int):
    from database.mongo import get_processing_status
    ps = get_processing_status(report_id)
    meta = get_meeting(report_id)
    if ps is None and meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    status_val = (ps or {}).get("status") or (meta or {}).get("status", "UNKNOWN")
    error_msg  = (ps or {}).get("error")
    return {"id": report_id, "status": status_val, "error_message": error_msg}


@app.get("/history")
def get_history(
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Paginated history with TTL cache — reads from MongoDB."""
    if limit > 500:
        limit = 500
    cache_key = f"history:{skip}:{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    result = list_meetings(skip=skip, limit=limit)
    result["skip"]  = skip
    result["limit"] = limit
    _cache.set(cache_key, result)
    return result


@app.get("/report/{report_id}")
def get_report(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    report = get_full_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.get("/report/{report_id}/evidence")
def get_evidence(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    from database.mongo import get_analysis
    analysis = get_analysis(report_id) or {}
    ev = mongo_get_evidence(report_id)
    return {
        "report_id":  report_id,
        "severity":   analysis.get("severity", ""),
        "risk_score": analysis.get("risk_score", 0),
        "evidence":   ev,
    }


@app.get("/report/{report_id}/stats")
def get_report_stats(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    from database.mongo import get_analysis
    analysis = get_analysis(report_id) or {}
    return {
        "categories":                analysis.get("category_breakdown", {}),
        "confidence_stats":          analysis.get("confidence_stats", {}),
        "severity_distribution":     analysis.get("severity_distribution", {}),
        "context_type_distribution": analysis.get("context_type_distribution", {}),
        "ml_stats":                  analysis.get("ml_stats", {}),
        "word_count":                analysis.get("word_count"),
        "finding_count":             analysis.get("finding_count", 0),
        "unique_categories":         analysis.get("unique_categories", 0),
    }


@app.get("/report/{report_id}/pdf")
def download_pdf(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    pdf_path = meta.get("pdf_path") or f"reports/report_{report_id}.pdf"
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not found")
    return FileResponse(path=pdf_path, media_type="application/pdf",
                        filename=f"report_{report_id}.pdf")


@app.delete("/report/{report_id}", status_code=204, response_class=Response)
def delete_report(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Delete a report record from MongoDB, S3, and local PDF."""
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")

    # Snapshot URLs/paths before deleting
    pdf_path     = meta.get("pdf_path")
    s3_audio_url = meta.get("s3_recording_url")
    s3_pdf_url   = meta.get("s3_pdf_url")

    # -- 1. Delete local PDF from disk -----------------------------------------
    if pdf_path and os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
            logger.info(f"[#{report_id}] Local PDF deleted: {pdf_path}")
        except Exception as _e:
            logger.warning(f"[#{report_id}] Could not delete local PDF: {_e}")

    # -- 2. Delete audio file from S3 -----------------------------------------
    if s3_audio_url:
        try:
            s3_delete_file(s3_audio_url)
            logger.info(f"[#{report_id}] S3 audio deleted: {s3_audio_url}")
        except Exception as _e:
            logger.warning(f"[#{report_id}] S3 audio delete failed (non-fatal): {_e}")

    # -- 3. Delete PDF from S3 -------------------------------------------------
    if s3_pdf_url:
        try:
            s3_delete_file(s3_pdf_url)
            logger.info(f"[#{report_id}] S3 PDF deleted: {s3_pdf_url}")
        except Exception as _e:
            logger.warning(f"[#{report_id}] S3 PDF delete failed (non-fatal): {_e}")

    # -- 4. Delete vector-store transcript chunks -----------------------------
    try:
        delete_transcript(report_id)
    except Exception as _e:
        logger.warning(f"[#{report_id}] ChromaDB cleanup failed (non-fatal): {_e}")

    # -- 5. Delete all MongoDB collections for this meeting --------------------
    try:
        delete_meeting_data(report_id)
        logger.info(f"[#{report_id}] MongoDB records deleted")
    except Exception as _e:
        logger.warning(f"[#{report_id}] MongoDB cleanup failed (non-fatal): {_e}")

    # -- 6. Invalidate caches --------------------------------------------------
    _cache.invalidate()
    from modules.cache import history_cache as _h_cache, report_cache as _r_cache, evidence_cache as _e_cache
    _h_cache.invalidate()
    _r_cache.invalidate()
    _e_cache.invalidate()

    logger.info(f"[#{report_id}] Report fully deleted (local PDF + S3 + MongoDB)")

    try:
        audit_log("report_deleted", meeting_id=report_id,
                  details={"report_id": report_id})
    except Exception as _e:
        logger.warning(f"[#{report_id}] Audit log failed (non-fatal): {_e}")

    return Response(status_code=204)

# -- Notifications -------------------------------------------------------------

def _load_report_for_notify(report_id: int) -> Dict[str, Any]:
    report = get_full_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _parse_json_field(val, default):
    if val is None: return default
    if isinstance(val, (list, dict)): return val
    try: return json.loads(val)
    except Exception: return default


@app.post("/notify/alert/{report_id}")
def notify_alert(report_id: int, body: NotifyRequest = NotifyRequest()):
    report   = _load_report_for_notify(report_id)
    findings = _parse_json_field(report.get("findings"), [])
    stats    = _parse_json_field(report.get("stats"), {})
    result = send_alert_email(
        report_id=report_id, filename=report.get("filename", ""),
        severity=report.get("severity") or "Unknown", risk_score=report.get("risk_score") or 0,
        findings=findings, summary=report.get("llm_summary") or report.get("summary") or "",
        stats=stats, pdf_path=report.get("pdf_path"),
        recipients=body.recipients or None, app_url=APP_URL,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.get("filename", ""), report.get("severity") or "",
              report.get("risk_score") or 0, result["recipients"], email_type="alert")
    audit_log("alert_email_manual", meeting_id=report_id, user_action="send_alert",
              details={"recipients": result["recipients"]})
    return result


@app.post("/notify/summary/{report_id}")
def notify_summary(report_id: int, body: NotifyRequest = NotifyRequest()):
    report   = _load_report_for_notify(report_id)
    findings = _parse_json_field(report.get("findings"), [])
    stats    = _parse_json_field(report.get("stats"), {})
    result = send_summary_email(
        report_id=report_id, filename=report.get("filename", ""),
        severity=report.get("severity") or "Unknown", risk_score=report.get("risk_score") or 0,
        findings=findings, llm_summary=report.get("llm_summary") or "",
        rule_summary=report.get("summary") or "", stats=stats,
        pdf_path=report.get("pdf_path"),
        recipients=body.recipients or None, app_url=APP_URL,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.get("filename", ""), report.get("severity") or "",
              report.get("risk_score") or 0, result["recipients"], email_type="summary")
    audit_log("summary_email_sent", meeting_id=report_id, user_action="send_summary",
              details={"recipients": result["recipients"]})
    return result


# -- Analytics -----------------------------------------------------------------

@app.get("/analytics/summary")
def get_analytics_summary():
    """Aggregate analytics with TTL cache — reads from MongoDB."""
    cached = _cache.get("analytics")
    if cached is not None:
        return cached

    result = mongo_analytics()
    _cache.set("analytics", result)
    return result


# -- Chatbot -------------------------------------------------------------------

@app.post("/chat")
def chat(request: ChatRequest):
    try:
        return answer_question(request.report_id, request.question)
    except Exception as _e:
        raise HTTPException(status_code=500, detail=str(_e))
