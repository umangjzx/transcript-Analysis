"""
Google Drive / Docs Integration Routes
=======================================
Prefix: /api/v1/google-drive

Endpoints:
  GET  /auth-url          → returns the OAuth2 consent URL
  GET  /callback          → handles the OAuth2 redirect, exchanges code for tokens
  GET  /status            → returns whether the user is authenticated
  DELETE /logout          → revokes stored credentials
  GET  /files             → lists importable files from Google Drive
  POST /import            → imports a file as a transcript and runs the full pipeline

  GET  /watcher/status    → returns watcher running state + stats
  POST /watcher/start     → starts the auto-import background watcher
  POST /watcher/stop      → stops the watcher
"""

import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query, status
from fastapi.responses import RedirectResponse, JSONResponse
from pydantic import BaseModel

from services.google_drive_service import (
    get_auth_url,
    exchange_code_for_tokens,
    list_drive_files,
    read_drive_file,
    is_authenticated,
    revoke_credentials,
)
from modules.drive_watcher import (
    start_watcher,
    stop_watcher,
    get_status as watcher_get_status,
)
from database.mongo import (
    next_meeting_id,
    save_meeting_metadata,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1/google-drive",
    tags=["Google Drive Integration"],
)


# ── Request / Response models ─────────────────────────────────────────────────

class ImportRequest(BaseModel):
    file_id: str
    file_name: str
    mime_type: str


class ImportResponse(BaseModel):
    id: int
    filename: str
    status: str
    message: str
    source: str = "google_drive"


# ── Auth URL ──────────────────────────────────────────────────────────────────

@router.get(
    "/auth-url",
    summary="Get Google OAuth2 URL",
    description=(
        "Returns the Google OAuth2 consent-screen URL. "
        "Open this URL in a browser to grant Drive access."
    ),
)
def get_google_auth_url():
    """Return the OAuth2 consent URL for Google Drive."""
    try:
        url = get_auth_url()
        return {"auth_url": url}
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Failed to build auth URL: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not generate auth URL: {e}",
        )


# ── OAuth2 Callback ───────────────────────────────────────────────────────────

@router.get(
    "/callback",
    summary="OAuth2 Callback",
    description=(
        "Google redirects here after the user grants access. "
        "Exchanges the authorization code for tokens and stores them."
    ),
)
def google_oauth_callback(
    code: Optional[str] = Query(None),
    error: Optional[str] = Query(None),
):
    """Handle the OAuth2 redirect from Google."""
    if error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Google OAuth error: {error}",
        )
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing 'code' parameter in callback.",
        )
    try:
        result = exchange_code_for_tokens(code)
        logger.info("Google Drive authentication successful.")
        # Return a simple success page — the frontend can poll /status
        return JSONResponse(
            content={
                "message": "Google Drive connected successfully.",
                "scopes": result.get("scopes", []),
            }
        )
    except Exception as e:
        logger.error(f"Token exchange failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Token exchange failed: {e}",
        )


# ── Auth Status ───────────────────────────────────────────────────────────────

@router.get(
    "/status",
    summary="Google Drive Auth Status",
    description="Check whether the backend is authenticated with Google Drive.",
)
def google_auth_status():
    """Return current authentication status."""
    authenticated = is_authenticated()
    return {
        "authenticated": authenticated,
        "message": (
            "Connected to Google Drive."
            if authenticated
            else "Not authenticated. Call GET /api/v1/google-drive/auth-url to connect."
        ),
    }


# ── Logout / Revoke ───────────────────────────────────────────────────────────

@router.delete(
    "/logout",
    summary="Revoke Google Drive Access",
    description="Deletes stored credentials, disconnecting Google Drive.",
)
def google_logout():
    """Revoke and delete stored Google credentials."""
    try:
        revoke_credentials()
        return {"message": "Google Drive disconnected. Credentials deleted."}
    except Exception as e:
        logger.error(f"Logout failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logout failed: {e}",
        )


# ── List Files ────────────────────────────────────────────────────────────────

@router.get(
    "/files",
    summary="List Google Drive Files",
    description=(
        "Lists .txt files and Google Docs from the authenticated Drive account. "
        "These can be imported as transcripts."
    ),
)
def list_files(
    page_size: int = Query(50, ge=1, le=100, description="Max number of files to return"),
    search: Optional[str] = Query(None, description="Optional filename search term"),
):
    """List importable files from Google Drive."""
    if not is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated with Google Drive. Call /auth-url first.",
        )
    try:
        query = None
        if search:
            # Combine name search with MIME type filter
            mime_filter = (
                "(mimeType='text/plain' or mimeType='application/vnd.google-apps.document')"
            )
            query = f"{mime_filter} and name contains '{search}' and trashed=false"

        files = list_drive_files(page_size=page_size, query=query)
        return {
            "files": files,
            "count": len(files),
        }
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to list Drive files: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list files: {e}",
        )


# ── Import File as Transcript ─────────────────────────────────────────────────

@router.post(
    "/import",
    response_model=ImportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Import Google Drive File as Transcript",
    description=(
        "Downloads the selected file from Google Drive, reads its text content, "
        "and feeds it directly into the analysis pipeline — no audio upload needed."
    ),
)
def import_drive_file(
    body: ImportRequest,
    background_tasks: BackgroundTasks,
):
    """
    Import a Google Drive file as a transcript and run the full analysis pipeline.

    The file content is read immediately; analysis runs in the background.
    Returns a record ID you can poll via GET /api/v1/report/{id}.
    """
    if not is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated with Google Drive. Call /auth-url first.",
        )

    # Validate MIME type
    accepted = {"text/plain", "application/vnd.google-apps.document"}
    if body.mime_type not in accepted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{body.mime_type}'. Accepted: {', '.join(accepted)}",
        )

    # Download the file content from Drive
    try:
        transcript_text = read_drive_file(body.file_id, body.mime_type)
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to read Drive file {body.file_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read file from Google Drive: {e}",
        )

    if not transcript_text or not transcript_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The selected file is empty or contains no readable text.",
        )

    # Allocate a meeting ID and create the initial record
    record_id = next_meeting_id()
    filename = body.file_name or f"gdrive_import_{record_id}.txt"
    save_meeting_metadata(
        meeting_id=record_id,
        filename=filename,
        file_size_bytes=len(transcript_text.encode("utf-8")),
        status="PROCESSING",
    )

    # Run the transcript analysis pipeline in the background
    background_tasks.add_task(
        _run_transcript_pipeline,
        record_id=record_id,
        transcript=transcript_text,
        filename=filename,
    )

    logger.info(
        f"[#{record_id}] Google Drive import queued: '{filename}' "
        f"({len(transcript_text)} chars)"
    )

    return ImportResponse(
        id=record_id,
        filename=filename,
        status="PROCESSING",
        message="Transcript imported from Google Drive. Analysis started in background.",
        source="google_drive",
    )


# ── Background pipeline (transcript-only) ────────────────────────────────────

def _run_transcript_pipeline(record_id: int, transcript: str, filename: str):
    """
    Runs the full analysis pipeline on a plain-text transcript.
    Mirrors process_audio_background() in app.py but skips transcription.
    """
    from datetime import datetime
    from database.mongo import (
        save_full_analysis, save_processing_status,
        update_meeting_status, audit_log, update_pdf_path,
        update_s3_urls,
    )
    from modules.grooming_detector import GroomingDetector
    from modules.evidence_extractor import extract_evidence
    from modules.risk_scorer import WeightedRiskScorer
    from modules.severity_classifier import classify_severity
    from modules.summarizer import generate_summary
    from modules.stats import generate_stats
    from modules.llm_summarizer import generate_llm_summary
    from modules.report_generator import generate_pdf_report
    from modules.chatbot import store_transcript
    from modules.email_notifier import send_alert_email, should_auto_alert
    from modules.s3_storage import upload_pdf_report as s3_upload_pdf
    import os

    started_at = datetime.utcnow()
    save_processing_status(record_id, "PROCESSING", "analysis", started_at=started_at)
    audit_log(
        "gdrive_transcript_analysis_started",
        meeting_id=record_id,
        details={"filename": filename},
    )

    pdf_path = None
    s3_pdf_url = None

    try:
        # Minimal timeline — no timestamps for raw text
        timeline = [{"start": 0.0, "end": 0.0, "text": transcript, "speaker": "UNKNOWN"}]

        # Detection
        grooming_detector = GroomingDetector(min_confidence_threshold=0.3)
        analysis_result = grooming_detector.analyze_transcript(
            transcript=transcript, speaker_aware=True
        )
        findings = analysis_result.get("grouped_findings", [])
        evidence = extract_evidence(findings)
        save_processing_status(record_id, "PROCESSING", "scoring", started_at=started_at)

        # Scoring & severity
        risk_scorer = WeightedRiskScorer()
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

        # Vector store
        try:
            store_transcript(record_id, transcript)
        except Exception as _e:
            logger.warning(f"[#{record_id}] Vector store failed: {_e}")

        # PDF
        try:
            pdf_path = generate_pdf_report(
                report_id=record_id,
                filename=filename,
                severity=severity,
                risk_score=risk_score,
                findings=findings,
                summary=llm_summary,
            )
            update_pdf_path(record_id, pdf_path)
            try:
                s3_pdf_url = s3_upload_pdf(pdf_path, record_id)
                if s3_pdf_url:
                    update_s3_urls(record_id, s3_pdf_url=s3_pdf_url)
            except Exception as _e:
                logger.warning(f"[#{record_id}] S3 PDF upload failed: {_e}")
        except Exception as _e:
            logger.error(f"[#{record_id}] PDF generation failed: {_e}", exc_info=True)

        # MongoDB — full save
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
            s3_url=None,
            evidence=evidence,
            pdf_path=pdf_path,
            s3_pdf_url=s3_pdf_url,
        )

        # Auto-alert email
        if should_auto_alert(severity):
            try:
                from config import APP_URL
                send_alert_email(
                    report_id=record_id,
                    filename=filename,
                    severity=severity,
                    risk_score=risk_score,
                    findings=findings,
                    summary=llm_summary,
                    stats=stats,
                    pdf_path=pdf_path,
                    app_url=APP_URL,
                )
                audit_log(
                    "alert_email_sent",
                    meeting_id=record_id,
                    details={"severity": severity, "risk_score": risk_score},
                )
            except Exception as _e:
                logger.warning(f"[#{record_id}] Auto-alert email failed: {_e}")

        logger.info(
            f"[#{record_id}] GDrive transcript analysis COMPLETED "
            f"— severity={severity}, score={risk_score:.1f}"
        )

    except Exception as _e:
        save_processing_status(
            record_id, "FAILED", "error",
            started_at=started_at,
            completed_at=datetime.utcnow(),
            error=str(_e),
        )
        update_meeting_status(record_id, "FAILED")
        audit_log(
            "gdrive_transcript_analysis_failed",
            meeting_id=record_id,
            details={"error": str(_e)},
        )
        logger.error(
            f"[#{record_id}] GDrive transcript pipeline FAILED: {_e}", exc_info=True
        )


# ── Watcher control endpoints ─────────────────────────────────────────────────

@router.get(
    "/watcher/status",
    summary="Drive Watcher Status",
    description="Returns whether the auto-import watcher is running and its stats.",
)
def get_watcher_status():
    """Return current watcher state."""
    return watcher_get_status()


@router.post(
    "/watcher/start",
    summary="Start Drive Watcher",
    description=(
        "Starts the background watcher that polls Google Drive for new files "
        "and automatically imports them for analysis. "
        "Configure interval with DRIVE_POLL_INTERVAL_SECONDS in .env (default 120s). "
        "Optionally restrict to a folder with DRIVE_WATCH_FOLDER_ID."
    ),
)
def start_drive_watcher():
    """Start the auto-import background watcher."""
    if not is_authenticated():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated with Google Drive. Call /auth-url first.",
        )
    started = start_watcher()
    return {
        "message": "Watcher started." if started else "Watcher was already running.",
        "status": watcher_get_status(),
    }


@router.post(
    "/watcher/stop",
    summary="Stop Drive Watcher",
    description="Stops the background polling watcher.",
)
def stop_drive_watcher():
    """Stop the auto-import background watcher."""
    stopped = stop_watcher()
    return {
        "message": "Watcher stopped." if stopped else "Watcher was not running.",
        "status": watcher_get_status(),
    }
