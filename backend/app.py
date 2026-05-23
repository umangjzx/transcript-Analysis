"""
Audio Safety Analyzer - FastAPI Application

This is the main application file that provides audio safety analysis
with grooming pattern detection, risk scoring, and comprehensive reporting.

Features:
- Audio transcription with Whisper
- Multi-category grooming detection
- Weighted risk scoring
- Severity classification
- AI-powered summaries
- PDF report generation
- RAG-based chatbot
"""

import os
import json
import shutil
import logging
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi import Request

from pydantic import BaseModel

from sqlalchemy.orm import Session

from config import (
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS,
    APP_URL,
)

from database.db import (
    engine,
    SessionLocal
)

from database.models import (
    Base,
    AudioAnalysis
)

from database.mongo import (
    save_full_analysis,
    save_processing_status,
    update_meeting_status,
    audit_log,
    log_alert,
)

from modules.transcriber import (
    transcribe_audio
)

from modules.grooming_detector import (
    GroomingDetector
)

from modules.evidence_extractor import (
    extract_evidence
)

from modules.risk_scorer import (
    WeightedRiskScorer
)

from modules.severity_classifier import (
    classify_severity
)

from modules.summarizer import (
    generate_summary
)

from modules.stats import (
    generate_stats
)

from modules.llm_summarizer import (
    generate_llm_summary
)

from modules.report_generator import (
    generate_pdf_report
)

from modules.chatbot import (
    store_transcript,
    answer_question
)

from modules.email_notifier import (
    send_alert_email,
    send_summary_email,
    should_auto_alert,
)

from modules.s3_storage import upload_audio as s3_upload_audio, upload_pdf_report as s3_upload_pdf

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)
# Ensure the stream handler uses UTF-8 on Windows
for handler in logging.root.handlers:
    if isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler):
        handler.stream = open(handler.stream.fileno(), mode='w', encoding='utf-8', buffering=1)
logger = logging.getLogger(__name__)

# Create logs directory if it doesn't exist
os.makedirs('logs', exist_ok=True)
os.makedirs('reports', exist_ok=True)

# ----------------------------------------------------
# DATABASE INIT
# ----------------------------------------------------

try:
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
except Exception as e:
    logger.error(f"Database initialization failed: {str(e)}")
    raise

# ----------------------------------------------------
# FASTAPI APP
# ----------------------------------------------------

app = FastAPI(
    title="Audio Safety Analyzer",
    description="""
    Advanced audio safety analysis system for detecting grooming patterns in conversations.
    
    ## Features
    * Audio Transcription with Whisper
    * Multi-category Grooming Detection
    * Weighted Risk Scoring
    * Severity Classification
    * AI-powered Summaries
    * PDF Report Generation
    * RAG-based Chatbot
    
    ## Categories Detected
    - Meeting Requests (Critical)
    - Address/Location (Critical)
    - Secrecy (High)
    - Parent Monitoring (High)
    - School Information (Medium)
    - Routine/Schedule (Medium)
    - Video Call Requests (Medium)
    - Manipulation (Medium)
    - Trust Building (Low)
    - Relationship Building (Low)
    """,
    version="2.0.0",
    contact={
        "name": "Audio Safety Team",
        "email": "support@audiosafety.com"
    }
)

# ----------------------------------------------------
# CORS MIDDLEWARE
# ----------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ----------------------------------------------------
# GLOBAL EXCEPTION HANDLER
# ----------------------------------------------------

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler for unhandled errors."""
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "InternalServerError",
            "detail": "An unexpected error occurred. Please try again later.",
            "timestamp": datetime.now().isoformat()
        }
    )

# ----------------------------------------------------
# STARTUP/SHUTDOWN EVENTS
# ----------------------------------------------------

@app.on_event("startup")
async def startup_event():
    """Execute on application startup."""
    logger.info("=" * 80)
    logger.info("Audio Safety Analyzer v2.0 Starting...")
    logger.info("=" * 80)
    logger.info("Service initialized successfully")

@app.on_event("shutdown")
async def shutdown_event():
    """Execute on application shutdown."""
    logger.info("Audio Safety Analyzer shutting down...")

# ----------------------------------------------------
# INITIALIZE COMPONENTS
# ----------------------------------------------------

grooming_detector = GroomingDetector(min_confidence_threshold=0.3)
risk_scorer = WeightedRiskScorer()


# ----------------------------------------------------
# CHAT REQUEST MODEL
# ----------------------------------------------------

class ChatRequest(BaseModel):
    report_id: int
    question: str


# ----------------------------------------------------
# NOTIFY REQUEST MODEL
# ----------------------------------------------------

class NotifyRequest(BaseModel):
    recipients: Optional[list] = None   # override ALERT_RECIPIENTS if provided


# ----------------------------------------------------
# HOME
# ----------------------------------------------------

@app.get("/")
def home():

    return {
        "message": "Audio Safety Analyzer Running"
    }


# ----------------------------------------------------
# HEALTH CHECK
# ----------------------------------------------------

@app.get("/health")
def health():
    from modules.s3_storage import ping as s3_ping
    from database.mongo import ping as mongo_ping
    return {
        "status":  "healthy",
        "service": "Audio Safety Analyzer",
        "s3":      s3_ping(),
        "mongodb": {"connected": mongo_ping()},
    }


# ----------------------------------------------------
# ANALYZE AUDIO
# ----------------------------------------------------

def process_audio_background(record_id: int, filepath: str, filename: str):
    db: Session = SessionLocal()
    record = db.query(AudioAnalysis).filter(AudioAnalysis.id == record_id).first()

    if not record:
        db.close()
        return

    started_at = datetime.now()

    # ── Processing Status: started ────────────────────────────────────────────
    save_processing_status(record_id, "PROCESSING", "transcription", started_at=started_at)
    audit_log("analysis_started", meeting_id=record_id, details={"filename": filename})

    s3_url: Optional[str] = None  # populated after S3 upload

    try:
        # ----------------------------------
        # S3 UPLOAD (non-blocking)
        # ----------------------------------
        try:
            s3_url = s3_upload_audio(filepath, record_id, filename)
            if s3_url:
                logger.info(f"Audio uploaded to S3: {s3_url}")
                audit_log("s3_upload_success", meeting_id=record_id,
                          details={"s3_url": s3_url})
        except Exception as e:
            logger.warning(f"S3 upload failed for #{record_id}: {e}")
            audit_log("s3_upload_failed", meeting_id=record_id,
                      details={"error": str(e)})
        # ----------------------------------
        # TRANSCRIPTION
        # ----------------------------------
        transcript, timeline = transcribe_audio(filepath)
        save_processing_status(record_id, "PROCESSING", "analysis", started_at=started_at)

        # ----------------------------------
        # ANALYSIS
        # ----------------------------------
        analysis_result = grooming_detector.analyze_transcript(
            transcript=transcript,
            speaker_aware=True
        )
        findings = analysis_result.get("grouped_findings", [])
        evidence = extract_evidence(findings)
        save_processing_status(record_id, "PROCESSING", "scoring", started_at=started_at)

        # ----------------------------------
        # RISK
        # ----------------------------------
        risk_result = risk_scorer.calculate_score(findings)
        risk_score = risk_result.get("score", 0)
        severity = classify_severity(risk_score)

        # ----------------------------------
        # STATS
        # ----------------------------------
        stats = generate_stats(transcript, findings, severity, risk_score)

        # ----------------------------------
        # SUMMARY
        # ----------------------------------
        summary = generate_summary(transcript, findings, risk_score, severity)
        save_processing_status(record_id, "PROCESSING", "llm_summary", started_at=started_at)

        # ----------------------------------
        # LLM SUMMARY
        # ----------------------------------
        try:
            llm_summary = generate_llm_summary(transcript, findings, risk_score, severity)
        except Exception as e:
            llm_summary = "LLM Summary Failed: " + str(e)

        # ----------------------------------
        # DATABASE SAVE (SQLite)
        # ----------------------------------
        record.transcript = transcript
        record.findings = json.dumps(findings)
        record.evidence = json.dumps(evidence)
        record.stats = json.dumps(stats)
        record.summary = summary
        record.llm_summary = llm_summary
        record.severity = severity
        record.risk_score = risk_score
        db.commit()

        # ----------------------------------
        # VECTOR STORAGE
        # ----------------------------------
        try:
            store_transcript(record_id, transcript)
        except Exception as e:
            print(f"Vector Store Error: {e}")

        # ----------------------------------
        # PDF REPORT
        # ----------------------------------
        try:
            pdf_path = generate_pdf_report(
                report_id=record_id,
                filename=filename,
                severity=severity,
                risk_score=risk_score,
                findings=findings,
                summary=llm_summary
            )
            record.pdf_path = pdf_path

            # Upload PDF to S3
            try:
                s3_pdf_url = s3_upload_pdf(pdf_path, record_id)
                if s3_pdf_url:
                    audit_log("s3_pdf_uploaded", meeting_id=record_id,
                              details={"s3_url": s3_pdf_url})
            except Exception as e:
                logger.warning(f"S3 PDF upload failed for #{record_id}: {e}")

        except Exception as e:
            print("PDF Generation Failed: " + str(e))

        # Mark SQLite record as completed
        record.status = "COMPLETED"
        db.commit()

        # ----------------------------------
        # MONGODB — all 7 collections
        # ----------------------------------
        try:
            save_full_analysis(
                meeting_id=record_id,
                filename=filename,
                transcript=transcript,
                timeline=timeline,
                findings=findings,
                risk_score=risk_score,
                severity=severity,
                llm_summary=llm_summary,
                rule_summary=summary,
                stats=stats,
                started_at=started_at,
                s3_url=s3_url,
            )
        except Exception as e:
            logger.warning(f"MongoDB save_full_analysis failed for #{record_id}: {e}")

        # ----------------------------------
        # AUTO ALERT EMAIL
        # ----------------------------------
        if should_auto_alert(severity):
            try:
                send_alert_email(
                    report_id=record_id,
                    filename=filename,
                    severity=severity,
                    risk_score=risk_score,
                    findings=findings,
                    summary=llm_summary,
                    stats=stats,
                    pdf_path=record.pdf_path,
                    app_url=APP_URL,
                )
                audit_log("alert_email_sent", meeting_id=record_id,
                          details={"severity": severity, "risk_score": risk_score})
            except Exception as e:
                logger.warning(f"Auto-alert email failed for report {record_id}: {e}")

    except Exception as e:
        record.status = "FAILED"
        record.error_message = str(e)
        db.commit()
        save_processing_status(record_id, "FAILED", "error",
                               started_at=started_at,
                               completed_at=datetime.now(),
                               error=str(e))
        audit_log("analysis_failed", meeting_id=record_id, details={"error": str(e)})
        logger.error(f"Background processing failed for record {record_id}: {str(e)}", exc_info=True)
    finally:
        db.close()


@app.post("/analyze")
async def analyze_audio(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...)
):

    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filepath = os.path.join(UPLOAD_FOLDER, file.filename)

    with open(filepath, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    # Create initial record
    db: Session = SessionLocal()
    record = AudioAnalysis(
        filename=file.filename,
        status="PROCESSING"
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    record_id = record.id
    db.close()

    # Dispatch background task
    background_tasks.add_task(process_audio_background, record_id, filepath, file.filename)

    # Audit: file uploaded
    audit_log("file_uploaded", meeting_id=record_id,
              user_action="upload",
              details={"filename": file.filename})

    return {
        "id": record_id,
        "filename": file.filename,
        "status": "PROCESSING",
        "message": "Analysis started in background"
    }

@app.get("/report/{report_id}/status")
def get_report_status(report_id: int):
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
    
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
        
    return {
        "id": report.id,
        "status": report.status,
        "error_message": report.error_message
    }


# ----------------------------------------------------
# HISTORY
# ----------------------------------------------------

@app.get("/history")
def get_history():

    db = SessionLocal()

    reports = db.query(
        AudioAnalysis
    ).all()

    result = []

    for row in reports:

        result.append({

            "id": row.id,

            "filename": row.filename,

            "severity": row.severity,

            "risk_score": row.risk_score
        })

    db.close()

    return result


# ----------------------------------------------------
# REPORT
# ----------------------------------------------------

@app.get("/report/{report_id}")
def get_report(report_id: int):

    db = SessionLocal()

    report = db.query(
        AudioAnalysis
    ).filter(
        AudioAnalysis.id == report_id
    ).first()

    db.close()

    if not report:

        raise HTTPException(
            status_code=404,
            detail="Report not found"
        )

    return {

        "id": report.id,

        "filename": report.filename,

        "transcript": report.transcript,

        "findings":
        json.loads(report.findings)
        if report.findings else [],

        "evidence":
        json.loads(report.evidence)
        if report.evidence else [],

        "stats":
        json.loads(report.stats)
        if report.stats else {},

        "summary": report.summary,

        "llm_summary": report.llm_summary,

        "severity": report.severity,

        "risk_score": report.risk_score,

        "pdf_path": report.pdf_path
    }


# ----------------------------------------------------
# EVIDENCE
# ----------------------------------------------------

@app.get("/report/{report_id}/evidence")
def get_evidence(report_id: int):

    db = SessionLocal()

    report = db.query(
        AudioAnalysis
    ).filter(
        AudioAnalysis.id == report_id
    ).first()

    db.close()

    if not report:

        raise HTTPException(
            status_code=404,
            detail="Report not found"
        )

    return {

        "report_id": report_id,

        "severity": report.severity,

        "risk_score": report.risk_score,

        "evidence":
        json.loads(report.evidence)
        if report.evidence else []
    }


# ----------------------------------------------------
# STATS
# ----------------------------------------------------

@app.get("/report/{report_id}/stats")
def get_report_stats(report_id: int):

    db = SessionLocal()

    report = db.query(
        AudioAnalysis
    ).filter(
        AudioAnalysis.id == report_id
    ).first()

    db.close()

    if not report:

        raise HTTPException(
            status_code=404,
            detail="Report not found"
        )

    return (
        json.loads(report.stats)
        if report.stats else {}
    )


# ----------------------------------------------------
# PDF DOWNLOAD
# ----------------------------------------------------

@app.get("/report/{report_id}/pdf")
def download_pdf(report_id: int):

    pdf_path = (
        f"reports/report_{report_id}.pdf"
    )

    if not os.path.exists(
        pdf_path
    ):

        raise HTTPException(
            status_code=404,
            detail="PDF report not found"
        )

    return FileResponse(

        path=pdf_path,

        media_type="application/pdf",

        filename=f"report_{report_id}.pdf"
    )


# ----------------------------------------------------
# NOTIFICATIONS
# ----------------------------------------------------

def _load_report_for_notify(report_id: int):
    """Helper — load a completed report from DB, raise 404 if missing."""
    db = SessionLocal()
    report = db.query(AudioAnalysis).filter(AudioAnalysis.id == report_id).first()
    db.close()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@app.post("/notify/alert/{report_id}")
def notify_alert(report_id: int, body: NotifyRequest = NotifyRequest()):
    """
    Manually trigger a red-alert email for any report regardless of severity.
    Useful for re-sending or sending to a custom recipient list.
    """
    report = _load_report_for_notify(report_id)
    findings = json.loads(report.findings) if report.findings else []
    stats    = json.loads(report.stats)    if report.stats    else {}

    result = send_alert_email(
        report_id=report_id,
        filename=report.filename,
        severity=report.severity or "Unknown",
        risk_score=report.risk_score or 0,
        findings=findings,
        summary=report.llm_summary or report.summary or "",
        stats=stats,
        pdf_path=report.pdf_path,
        recipients=body.recipients or None,
        app_url=APP_URL,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.filename, report.severity or "", report.risk_score or 0,
              result["recipients"], email_type="alert")
    audit_log("alert_email_manual", meeting_id=report_id,
              user_action="send_alert",
              details={"recipients": result["recipients"]})
    return result


@app.post("/notify/summary/{report_id}")
def notify_summary(report_id: int, body: NotifyRequest = NotifyRequest()):
    """
    Send a full analysis summary email for any report.
    """
    report = _load_report_for_notify(report_id)
    findings = json.loads(report.findings) if report.findings else []
    stats    = json.loads(report.stats)    if report.stats    else {}

    result = send_summary_email(
        report_id=report_id,
        filename=report.filename,
        severity=report.severity or "Unknown",
        risk_score=report.risk_score or 0,
        findings=findings,
        llm_summary=report.llm_summary or "",
        rule_summary=report.summary or "",
        stats=stats,
        pdf_path=report.pdf_path,
        recipients=body.recipients or None,
        app_url=APP_URL,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.filename, report.severity or "", report.risk_score or 0,
              result["recipients"], email_type="summary")
    audit_log("summary_email_sent", meeting_id=report_id,
              user_action="send_summary",
              details={"recipients": result["recipients"]})
    return result


# ----------------------------------------------------
# ANALYTICS SUMMARY  (cross-report aggregation)
# ----------------------------------------------------

@app.get("/analytics/summary")
def get_analytics_summary():
    """
    Aggregate analytics across ALL reports for dashboard-level charts.

    Returns:
        - severity_distribution  : {Critical: n, High: n, ...}
        - risk_score_histogram   : {"0-20": n, "21-40": n, ...}
        - total_reports          : int
        - total_findings         : int
        - avg_risk_score         : float
        - status_distribution    : {COMPLETED: n, FAILED: n, PROCESSING: n}
        - top_categories         : [{category, count}] sorted desc
        - context_type_totals    : {GROOMING: n, NEUTRAL: n, ...}
        - ml_agreement_totals    : {agreed: n, disagreed: n, rate: float}
        - confidence_histogram   : {"0-25": n, ...}
    """
    db = SessionLocal()
    reports = db.query(AudioAnalysis).all()
    db.close()

    severity_dist: dict = {}
    status_dist: dict = {}
    risk_histogram = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
    category_totals: dict = {}
    context_totals: dict = {}
    ml_agreed = 0
    ml_disagreed = 0
    ml_total = 0
    conf_histogram = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
    total_findings = 0
    risk_scores = []

    for report in reports:
        # Severity
        sev = (report.severity or "unknown").capitalize()
        severity_dist[sev] = severity_dist.get(sev, 0) + 1

        # Status
        st = report.status or "unknown"
        status_dist[st] = status_dist.get(st, 0) + 1

        # Risk histogram
        score = report.risk_score or 0
        risk_scores.append(score)
        if score <= 20:
            risk_histogram["0-20"] += 1
        elif score <= 40:
            risk_histogram["21-40"] += 1
        elif score <= 60:
            risk_histogram["41-60"] += 1
        elif score <= 80:
            risk_histogram["61-80"] += 1
        else:
            risk_histogram["81-100"] += 1

        # Per-report stats (already computed and stored)
        if report.stats:
            try:
                s = json.loads(report.stats)

                # Category totals
                for cat, cnt in (s.get("categories") or {}).items():
                    category_totals[cat] = category_totals.get(cat, 0) + cnt

                # Context type totals
                for ctx, cnt in (s.get("context_type_distribution") or {}).items():
                    context_totals[ctx] = context_totals.get(ctx, 0) + cnt

                # ML agreement
                ml_s = s.get("ml_stats") or {}
                ml_agreed    += ml_s.get("agreed", 0)
                ml_disagreed += ml_s.get("disagreed", 0)
                ml_total     += ml_s.get("total_with_ml", 0)

                # Confidence histogram
                ch = s.get("confidence_histogram") or {}
                for bucket, cnt in ch.items():
                    if bucket in conf_histogram:
                        conf_histogram[bucket] += cnt

                # Finding count
                total_findings += s.get("finding_count", 0)

            except Exception:
                pass

    avg_risk = round(sum(risk_scores) / len(risk_scores), 2) if risk_scores else 0.0
    ml_rate = round(ml_agreed / ml_total, 4) if ml_total > 0 else None

    top_categories = sorted(
        [{"category": k, "count": v} for k, v in category_totals.items()],
        key=lambda x: x["count"],
        reverse=True
    )

    return {
        "total_reports":        len(reports),
        "total_findings":       total_findings,
        "avg_risk_score":       avg_risk,
        "severity_distribution": severity_dist,
        "status_distribution":  status_dist,
        "risk_score_histogram": risk_histogram,
        "top_categories":       top_categories,
        "context_type_totals":  context_totals,
        "ml_agreement_totals": {
            "agreed":    ml_agreed,
            "disagreed": ml_disagreed,
            "total":     ml_total,
            "rate":      ml_rate,
        },
        "confidence_histogram": conf_histogram,
    }


# ----------------------------------------------------
# CHATBOT
# ----------------------------------------------------

@app.post("/chat")
def chat(
    request: ChatRequest
):

    try:

        return answer_question(

            request.report_id,

            request.question
        )

    except Exception as e:

        raise HTTPException(
            status_code=500,
            detail=str(e)
        )