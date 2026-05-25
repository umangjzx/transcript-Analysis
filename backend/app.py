"""
Audio Safety Analyzer - FastAPI Application

Fixes applied:
- CORS locked to configured origins (env: ALLOWED_ORIGINS)
- File size limit enforced (env: MAX_UPLOAD_MB, default 200 MB)
- Secure filename — UUID on disk, original name in DB
- Request correlation ID middleware (X-Request-ID header)
- API key authentication (env: API_KEY — leave blank to disable in dev)
- Stuck-job recovery on startup (PROCESSING > 30 min → FAILED)
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
import threading
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

from fastapi import FastAPI, UploadFile, File, HTTPException, status, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, APP_URL
from database.db import engine, SessionLocal
from database.models import Base, AudioAnalysis
from database.mongo import (
    save_full_analysis, save_processing_status,
    update_meeting_status, audit_log, log_alert,
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
from modules.chatbot import store_transcript, answer_question
from modules.email_notifier import send_alert_email, send_summary_email, should_auto_alert
from modules.s3_storage import upload_audio as s3_upload_audio, upload_pdf_report as s3_upload_pdf

# ── Logging ───────────────────────────────────────────────────────────────────

os.makedirs("logs", exist_ok=True)
os.makedirs("reports", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler("logs/app.log", encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
for _handler in logging.root.handlers:
    if isinstance(_handler, logging.StreamHandler) and not isinstance(_handler, logging.FileHandler):
        try:
            _handler.stream = open(_handler.stream.fileno(), mode="w", encoding="utf-8", buffering=1)
        except Exception:
            pass

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024

_raw_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
ALLOWED_ORIGINS = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# API key — set API_KEY in .env to enable auth; leave blank to disable (dev).
API_KEY: str = os.getenv("API_KEY", "")

# Upload TTL — audio files older than this are deleted. 0 = disabled.
UPLOAD_TTL_HOURS: int = int(os.getenv("UPLOAD_TTL_HOURS", "24"))

# ── TTL cache ─────────────────────────────────────────────────────────────────

_CACHE_TTL = 60  # seconds


class _TTLCache:
    """Minimal thread-safe TTL cache for read-heavy endpoints."""

    def __init__(self, ttl: int = _CACHE_TTL):
        self._ttl = ttl
        self._store: Dict[str, Any] = {}
        self._ts: Dict[str, float] = {}
        self._lock = threading.Lock()

    def get(self, key: str):
        with self._lock:
            if key in self._store and (time.monotonic() - self._ts[key]) < self._ttl:
                return self._store[key]
            return None

    def set(self, key: str, value: Any):
        with self._lock:
            self._store[key] = value
            self._ts[key] = time.monotonic()

    def invalidate(self, key: str = None):
        with self._lock:
            if key:
                self._store.pop(key, None); self._ts.pop(key, None)
            else:
                self._store.clear(); self._ts.clear()


_cache = _TTLCache()

# ── Database init ─────────────────────────────────────────────────────────────

try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")
except Exception as _e:
    logger.error(f"Database initialization failed: {_e}")
    raise

# ── FastAPI app ───────────────────────────────────────────────────────────────

app = FastAPI(
    title="Audio Safety Analyzer",
    description="Advanced audio safety analysis system for detecting grooming patterns.",
    version="2.1.0",
)

# ── Request ID middleware ─────────────────────────────────────────────────────

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

app.add_middleware(RequestIDMiddleware)

# ── API Key auth middleware ────────────────────────────────────────────────────

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

# ── CORS ──────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global exception handler ──────────────────────────────────────────────────

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
            "timestamp": datetime.utcnow().isoformat(),
        },
    )

# ── Pipeline components ───────────────────────────────────────────────────────

_enable_ml = os.getenv("ENABLE_ML_CLASSIFIER", "false").lower() == "true"
grooming_detector = GroomingDetector(
    min_confidence_threshold=0.3,
    enable_ml_classifier=_enable_ml,
)
risk_scorer = WeightedRiskScorer()

# ── Startup / shutdown ────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    logger.info("=" * 70)
    logger.info("Audio Safety Analyzer v2.1 Starting...")
    logger.info(f"CORS allowed origins: {ALLOWED_ORIGINS}")
    logger.info(f"Max upload size: {MAX_UPLOAD_BYTES // (1024*1024)} MB")
    logger.info(f"API key auth: {'ENABLED' if API_KEY else 'DISABLED (set API_KEY in .env)'}")
    logger.info(f"ML classifier: {'ENABLED' if _enable_ml else 'DISABLED'}")
    logger.info("=" * 70)

    # Stuck-job recovery
    try:
        db: Session = SessionLocal()
        cutoff = datetime.utcnow() - timedelta(minutes=30)
        stuck = (
            db.query(AudioAnalysis)
            .filter(AudioAnalysis.status == "PROCESSING", AudioAnalysis.created_at < cutoff)
            .all()
        )
        for rec in stuck:
            rec.status = "FAILED"
            rec.error_message = "Processing timed out — server was restarted mid-analysis."
            logger.warning(f"Stuck-job recovery: marked record #{rec.id} as FAILED")
        if stuck:
            db.commit()
        db.close()
    except Exception as _e:
        logger.warning(f"Stuck-job recovery failed: {_e}")

    # ML warm-up — load model into memory before first real request
    if _enable_ml:
        def _warmup():
            try:
                logger.info("ML classifier warm-up: loading model...")
                grooming_detector.analyze_transcript("warm-up ping", speaker_aware=False)
                logger.info("ML classifier warm-up complete")
            except Exception as _e:
                logger.warning(f"ML warm-up failed (non-fatal): {_e}")
        threading.Thread(target=_warmup, daemon=True).start()

    # Upload cleanup daemon
    if UPLOAD_TTL_HOURS > 0:
        def _cleanup():
            while True:
                try:
                    cutoff_ts = time.time() - UPLOAD_TTL_HOURS * 3600
                    deleted = 0
                    if os.path.isdir(UPLOAD_FOLDER):
                        for fname in os.listdir(UPLOAD_FOLDER):
                            fpath = os.path.join(UPLOAD_FOLDER, fname)
                            try:
                                if os.path.isfile(fpath) and os.path.getmtime(fpath) < cutoff_ts:
                                    os.remove(fpath)
                                    deleted += 1
                            except Exception:
                                pass
                    if deleted:
                        logger.info(f"Upload cleanup: removed {deleted} file(s) older than {UPLOAD_TTL_HOURS}h")
                except Exception as _e:
                    logger.warning(f"Upload cleanup error: {_e}")
                time.sleep(3600)
        threading.Thread(target=_cleanup, daemon=True).start()
        logger.info(f"Upload cleanup daemon started (TTL={UPLOAD_TTL_HOURS}h)")

    logger.info("Service initialized successfully")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Audio Safety Analyzer shutting down...")

# ── Register versioned router ─────────────────────────────────────────────────

from api.audio_analysis_routes import router as v1_router  # noqa: E402
app.include_router(v1_router)

if _enable_ml:
    logger.info("ML classifier ENABLED (distilbert-mnli)")
else:
    logger.info("ML classifier DISABLED — set ENABLE_ML_CLASSIFIER=true in .env to enable")

# ── Request models ────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    report_id: int
    question: str


class NotifyRequest(BaseModel):
    recipients: Optional[list] = None


# ── Background pipeline ───────────────────────────────────────────────────────

def process_audio_background(record_id: int, filepath: str, filename: str):
    """Full analysis pipeline — runs in a background thread."""
    db: Session = SessionLocal()
    record = db.query(AudioAnalysis).filter(AudioAnalysis.id == record_id).first()
    if not record:
        db.close()
        return

    started_at = datetime.utcnow()
    save_processing_status(record_id, "PROCESSING", "transcription", started_at=started_at)
    audit_log("analysis_started", meeting_id=record_id, details={"filename": filename})
    s3_url: Optional[str] = None

    try:
        # S3 audio upload (non-fatal)
        try:
            s3_url = s3_upload_audio(filepath, record_id, filename)
            if s3_url:
                logger.info(f"[#{record_id}] Audio uploaded to S3: {s3_url}")
                audit_log("s3_upload_success", meeting_id=record_id, details={"s3_url": s3_url})
        except Exception as _e:
            logger.warning(f"[#{record_id}] S3 upload failed: {_e}")

        # Transcription
        transcript, timeline = transcribe_audio(filepath)
        logger.info(f"[#{record_id}] Transcription complete: {len(transcript)} chars")
        save_processing_status(record_id, "PROCESSING", "analysis", started_at=started_at)

        # Detection
        analysis_result = grooming_detector.analyze_transcript(transcript=transcript, speaker_aware=True)
        findings = analysis_result.get("grouped_findings", [])
        evidence = extract_evidence(findings)
        save_processing_status(record_id, "PROCESSING", "scoring", started_at=started_at)

        # Scoring & severity
        risk_result = risk_scorer.calculate_score(findings)
        risk_score = risk_result.get("score", 0)
        severity = classify_severity(risk_score)
        logger.info(f"[#{record_id}] Risk score: {risk_score:.1f} → {severity}")

        # Stats & summaries
        stats = generate_stats(transcript, findings, severity, risk_score)
        summary = generate_summary(transcript, findings, risk_score, severity)
        save_processing_status(record_id, "PROCESSING", "llm_summary", started_at=started_at)

        try:
            llm_summary = generate_llm_summary(transcript, findings, risk_score, severity)
        except Exception as _e:
            logger.warning(f"[#{record_id}] LLM summary failed: {_e}")
            llm_summary = f"LLM Summary unavailable: {_e}"

        # SQLite save — ORM handles JSON serialisation via JSONEncoder columns
        record.transcript = transcript
        record.findings   = findings
        record.evidence   = evidence
        record.stats      = stats
        record.summary    = summary
        record.llm_summary = llm_summary
        record.severity   = severity
        record.risk_score = risk_score
        record.diarization = timeline
        record.updated_at = datetime.utcnow()
        db.commit()

        # Vector store
        try:
            store_transcript(record_id, transcript)
        except Exception as _e:
            logger.warning(f"[#{record_id}] Vector store failed: {_e}")

        # PDF
        try:
            pdf_path = generate_pdf_report(
                report_id=record_id, filename=filename, severity=severity,
                risk_score=risk_score, findings=findings, summary=llm_summary,
            )
            record.pdf_path = pdf_path
            record.updated_at = datetime.utcnow()
            try:
                s3_pdf_url = s3_upload_pdf(pdf_path, record_id)
                if s3_pdf_url:
                    audit_log("s3_pdf_uploaded", meeting_id=record_id, details={"s3_url": s3_pdf_url})
            except Exception as _e:
                logger.warning(f"[#{record_id}] S3 PDF upload failed: {_e}")
        except Exception as _e:
            logger.error(f"[#{record_id}] PDF generation failed: {_e}", exc_info=True)

        record.status = "COMPLETED"
        record.updated_at = datetime.utcnow()
        db.commit()

        # Invalidate caches so next /history and /analytics reflect new data
        _cache.invalidate()

        # MongoDB
        try:
            save_full_analysis(
                meeting_id=record_id, filename=filename, transcript=transcript,
                timeline=timeline, findings=findings, risk_score=risk_score,
                severity=severity, llm_summary=llm_summary, rule_summary=summary,
                stats=stats, started_at=started_at, s3_url=s3_url,
            )
        except Exception as _e:
            logger.warning(f"[#{record_id}] MongoDB save failed: {_e}")

        # Auto-alert email
        if should_auto_alert(severity):
            try:
                send_alert_email(
                    report_id=record_id, filename=filename, severity=severity,
                    risk_score=risk_score, findings=findings, summary=llm_summary,
                    stats=stats, pdf_path=record.pdf_path, app_url=APP_URL,
                )
                audit_log("alert_email_sent", meeting_id=record_id,
                          details={"severity": severity, "risk_score": risk_score})
            except Exception as _e:
                logger.warning(f"[#{record_id}] Auto-alert email failed: {_e}")

        logger.info(f"[#{record_id}] Analysis COMPLETED — severity={severity}, score={risk_score:.1f}")

    except Exception as _e:
        record.status = "FAILED"
        record.error_message = str(_e)
        record.updated_at = datetime.utcnow()
        db.commit()
        save_processing_status(record_id, "FAILED", "error",
                               started_at=started_at, completed_at=datetime.utcnow(), error=str(_e))
        audit_log("analysis_failed", meeting_id=record_id, details={"error": str(_e)})
        logger.error(f"[#{record_id}] Background processing FAILED: {_e}", exc_info=True)
    finally:
        db.close()

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/")
def home():
    return {"message": "Audio Safety Analyzer Running", "version": "2.1.0"}


@app.get("/health")
def health():
    from modules.s3_storage import ping as s3_ping
    from database.mongo import ping as mongo_ping
    return {
        "status": "healthy",
        "service": "Audio Safety Analyzer",
        "ml_classifier": {"enabled": _enable_ml},
        "s3": s3_ping(),
        "mongodb": {"connected": mongo_ping()},
    }


@app.post("/analyze")
async def analyze_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{extension}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

    safe_disk_name = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filepath = os.path.join(UPLOAD_FOLDER, safe_disk_name)
    with open(filepath, "wb") as buffer:
        buffer.write(content)

    original_filename = file.filename or safe_disk_name

    db: Session = SessionLocal()
    record = AudioAnalysis(
        filename=original_filename, status="PROCESSING",
        created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    record_id = record.id
    db.close()

    background_tasks.add_task(process_audio_background, record_id, filepath, original_filename)
    audit_log("file_uploaded", meeting_id=record_id, user_action="upload",
              details={"filename": original_filename, "size_bytes": len(content)})
    logger.info(f"[#{record_id}] Upload accepted: {original_filename} ({len(content)//1024} KB)")

    return {"id": record_id, "filename": original_filename,
            "status": "PROCESSING", "message": "Analysis started in background"}


@app.get("/report/{report_id}/status")
def get_report_status(report_id: int):
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return {"id": report.id, "status": report.status, "error_message": report.error_message}


@app.get("/history")
def get_history(skip: int = 0, limit: int = 100):
    """Paginated history with TTL cache — returns id, filename, severity, risk_score, status, created_at."""
    if limit > 500:
        limit = 500
    cache_key = f"history:{skip}:{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    db = SessionLocal()
    total = db.query(AudioAnalysis).count()
    reports = (
        db.query(AudioAnalysis)
        .order_by(AudioAnalysis.id.desc())
        .offset(skip).limit(limit).all()
    )
    db.close()

    result = {
        "reports": [
            {
                "id": row.id, "filename": row.filename, "severity": row.severity,
                "risk_score": row.risk_score, "status": row.status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in reports
        ],
        "total": total, "skip": skip, "limit": limit,
    }
    _cache.set(cache_key, result)
    return result


@app.get("/report/{report_id}")
def get_report(report_id: int):
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")

    # JSON columns are auto-deserialised by the ORM JSONEncoder.
    # Fallback json.loads handles any legacy TEXT rows written before the migration.
    def _j(val, default):
        if val is None:
            return default
        if isinstance(val, (list, dict)):
            return val
        try:
            return json.loads(val)
        except Exception:
            return default

    diarization = _j(report.diarization, [])
    return {
        "id": report.id, "filename": report.filename, "transcript": report.transcript,
        "findings": _j(report.findings, []), "evidence": _j(report.evidence, []),
        "stats": _j(report.stats, {}), "summary": report.summary,
        "llm_summary": report.llm_summary, "severity": report.severity,
        "risk_score": report.risk_score, "pdf_path": report.pdf_path,
        "status": report.status, "diarization": diarization,
        "timeline": diarization,  # frontend alias
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


@app.get("/report/{report_id}/evidence")
def get_evidence(report_id: int):
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    ev = report.evidence
    if isinstance(ev, str):
        try: ev = json.loads(ev)
        except Exception: ev = []
    return {"report_id": report_id, "severity": report.severity,
            "risk_score": report.risk_score, "evidence": ev or []}


@app.get("/report/{report_id}/stats")
def get_report_stats(report_id: int):
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    st = report.stats
    if isinstance(st, str):
        try: st = json.loads(st)
        except Exception: st = {}
    return st or {}


@app.get("/report/{report_id}/pdf")
def download_pdf(report_id: int):
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    pdf_path = report.pdf_path or f"reports/report_{report_id}.pdf"
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not found")
    return FileResponse(path=pdf_path, media_type="application/pdf",
                        filename=f"report_{report_id}.pdf")


@app.delete("/report/{report_id}", status_code=204)
def delete_report(report_id: int):
    """Delete a report record, its PDF file, and invalidate caches."""
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    if not report:
        db.close()
        raise HTTPException(status_code=404, detail="Report not found")

    # Delete PDF from disk if it exists
    if report.pdf_path and os.path.exists(report.pdf_path):
        try:
            os.remove(report.pdf_path)
            logger.info(f"[#{report_id}] PDF deleted: {report.pdf_path}")
        except Exception as _e:
            logger.warning(f"[#{report_id}] Could not delete PDF: {_e}")

    db.delete(report)
    db.commit()
    db.close()

    # Invalidate caches so history/analytics reflect the deletion immediately
    _cache.invalidate()

    audit_log("report_deleted", meeting_id=report_id,
              details={"report_id": report_id})
    logger.info(f"[#{report_id}] Report deleted")

# ── Notifications ─────────────────────────────────────────────────────────────

def _load_report_for_notify(report_id: int) -> AudioAnalysis:
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
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
    report = _load_report_for_notify(report_id)
    findings = _parse_json_field(report.findings, [])
    stats    = _parse_json_field(report.stats, {})
    result = send_alert_email(
        report_id=report_id, filename=report.filename,
        severity=report.severity or "Unknown", risk_score=report.risk_score or 0,
        findings=findings, summary=report.llm_summary or report.summary or "",
        stats=stats, pdf_path=report.pdf_path,
        recipients=body.recipients or None, app_url=APP_URL,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.filename, report.severity or "", report.risk_score or 0,
              result["recipients"], email_type="alert")
    audit_log("alert_email_manual", meeting_id=report_id, user_action="send_alert",
              details={"recipients": result["recipients"]})
    return result


@app.post("/notify/summary/{report_id}")
def notify_summary(report_id: int, body: NotifyRequest = NotifyRequest()):
    report = _load_report_for_notify(report_id)
    findings = _parse_json_field(report.findings, [])
    stats    = _parse_json_field(report.stats, {})
    result = send_summary_email(
        report_id=report_id, filename=report.filename,
        severity=report.severity or "Unknown", risk_score=report.risk_score or 0,
        findings=findings, llm_summary=report.llm_summary or "",
        rule_summary=report.summary or "", stats=stats, pdf_path=report.pdf_path,
        recipients=body.recipients or None, app_url=APP_URL,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.filename, report.severity or "", report.risk_score or 0,
              result["recipients"], email_type="summary")
    audit_log("summary_email_sent", meeting_id=report_id, user_action="send_summary",
              details={"recipients": result["recipients"]})
    return result


# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/analytics/summary")
def get_analytics_summary():
    """Aggregate analytics with TTL cache — only loads lightweight columns."""
    cached = _cache.get("analytics")
    if cached is not None:
        return cached

    db = SessionLocal()
    reports = (
        db.query(
            AudioAnalysis.id, AudioAnalysis.severity,
            AudioAnalysis.risk_score, AudioAnalysis.status, AudioAnalysis.stats,
        ).all()
    )
    db.close()

    severity_dist: dict = {}
    status_dist: dict = {}
    risk_histogram = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    category_totals: dict = {}
    context_totals: dict = {}
    ml_agreed = ml_disagreed = ml_total = 0
    conf_histogram = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
    total_findings = 0
    risk_scores = []

    for row in reports:
        sev = (row.severity or "unknown").capitalize()
        severity_dist[sev] = severity_dist.get(sev, 0) + 1
        st = row.status or "unknown"
        status_dist[st] = status_dist.get(st, 0) + 1
        score = row.risk_score or 0
        risk_scores.append(score)
        if score <= 20:   risk_histogram["0-20"] += 1
        elif score <= 40: risk_histogram["21-40"] += 1
        elif score <= 60: risk_histogram["41-60"] += 1
        elif score <= 80: risk_histogram["61-80"] += 1
        else:             risk_histogram["81-100"] += 1

        if row.stats:
            try:
                s = row.stats if isinstance(row.stats, dict) else json.loads(row.stats)
                for cat, cnt in (s.get("categories") or {}).items():
                    category_totals[cat] = category_totals.get(cat, 0) + cnt
                for ctx, cnt in (s.get("context_type_distribution") or {}).items():
                    context_totals[ctx] = context_totals.get(ctx, 0) + cnt
                ml_s = s.get("ml_stats") or {}
                ml_agreed    += ml_s.get("agreed", 0)
                ml_disagreed += ml_s.get("disagreed", 0)
                ml_total     += ml_s.get("total_with_ml", 0)
                for bucket, cnt in (s.get("confidence_histogram") or {}).items():
                    if bucket in conf_histogram:
                        conf_histogram[bucket] += cnt
                total_findings += s.get("finding_count", 0)
            except Exception:
                pass

    avg_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0
    ml_rate  = round(ml_agreed / ml_total, 4) if ml_total > 0 else None
    top_categories = sorted(
        [{"category": k, "count": v} for k, v in category_totals.items()],
        key=lambda x: x["count"], reverse=True,
    )

    result = {
        "total_reports": len(reports), "total_findings": total_findings,
        "avg_risk_score": avg_risk, "severity_distribution": severity_dist,
        "status_distribution": status_dist, "risk_score_histogram": risk_histogram,
        "top_categories": top_categories, "context_type_totals": context_totals,
        "ml_agreement_totals": {
            "agreed": ml_agreed, "disagreed": ml_disagreed,
            "total": ml_total, "rate": ml_rate,
        },
        "confidence_histogram": conf_histogram,
    }
    _cache.set("analytics", result)
    return result


# ── Chatbot ───────────────────────────────────────────────────────────────────

@app.post("/chat")
def chat(request: ChatRequest):
    try:
        return answer_question(request.report_id, request.question)
    except Exception as _e:
        raise HTTPException(status_code=500, detail=str(_e))
