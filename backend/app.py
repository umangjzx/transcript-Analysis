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
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, HTTPException, status, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi import Request

from pydantic import BaseModel

from sqlalchemy.orm import Session

from config import (
    UPLOAD_FOLDER,
    ALLOWED_EXTENSIONS
)

from database.db import (
    engine,
    SessionLocal
)

from database.models import (
    Base,
    AudioAnalysis
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

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
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

    return {
        "status": "healthy",
        "service": "Audio Safety Analyzer"
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

    try:
        # ----------------------------------
        # TRANSCRIPTION
        # ----------------------------------
        transcript, timeline = transcribe_audio(filepath)

        # ----------------------------------
        # ANALYSIS
        # ----------------------------------
        analysis_result = grooming_detector.analyze_transcript(
            transcript=transcript,
            speaker_aware=True
        )
        findings = analysis_result.get("grouped_findings", [])
        evidence = extract_evidence(findings)

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

        # ----------------------------------
        # LLM SUMMARY
        # ----------------------------------
        try:
            llm_summary = generate_llm_summary(transcript, findings, risk_score, severity)
        except Exception as e:
            llm_summary = "LLM Summary Failed: " + str(e)

        # ----------------------------------
        # DATABASE SAVE
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
        except Exception as e:
            print("PDF Generation Failed: " + str(e))

        # Mark as completed
        record.status = "COMPLETED"
        db.commit()

    except Exception as e:
        record.status = "FAILED"
        record.error_message = str(e)
        db.commit()
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