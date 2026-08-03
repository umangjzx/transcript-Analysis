"""
Unified analysis pipeline — single function that handles audio, video, and transcript inputs.

Consolidates the 4 duplicate pipeline functions:
  - app.py: process_audio_background, process_video_background, process_transcript_background
  - google_drive_routes.py: _run_transcript_pipeline
"""

import logging
import os
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple

from pymongo.errors import (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
    WriteConcernError,
)

logger = logging.getLogger(__name__)

# Infrastructure failures that are worth retrying rather than burning a real
# user's analysis on. Atlas drops idle pooled sockets routinely, so a write can
# fail purely because the connection went stale between operations — the work
# itself is fine and the same job succeeds on a second attempt. Anything not
# listed here (bad data, a bug, a permission error) is permanent: retrying it
# would just fail the same way three more times.
TRANSIENT_DB_ERRORS = (
    AutoReconnect,
    ConnectionFailure,
    NetworkTimeout,
    ServerSelectionTimeoutError,
    WriteConcernError,
)


class CriticalPersistenceError(Exception):
    """Raised when a write the record cannot be correct without did not land.

    Carries `transient` so the Celery layer knows whether retrying is worth
    anything, without having to re-inspect the original exception.
    """

    def __init__(self, message: str, transient: bool = False):
        super().__init__(message)
        self.transient = transient


def run_analysis_pipeline(
    record_id: int,
    filename: str,
    transcript: Optional[str] = None,
    timeline: Optional[List[Dict[str, Any]]] = None,
    audio_filepath: Optional[str] = None,
    upload_to_s3: bool = False,
    delete_audio_after_transcription: bool = False,
    source: str = "upload",
) -> None:
    """
    Unified analysis pipeline. Runs in a background thread.

    Args:
        record_id: MongoDB meeting ID
        filename: Original filename for display
        transcript: Pre-supplied transcript text (skips transcription if provided)
        timeline: Pre-supplied timeline segments
        audio_filepath: Path to audio file (required if transcript is None)
        upload_to_s3: Whether to upload the audio file to S3
        delete_audio_after_transcription: Delete audio file after transcription (video sources)
        source: Source identifier for audit logs (upload, video, transcript, google_drive)
    """
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
    from modules.email_notifier import send_alert_email, send_admin_report, should_auto_alert, should_parent_alert
    from modules.s3_storage import upload_audio as s3_upload_audio, upload_pdf_report as s3_upload_pdf
    from modules.cache import history_cache, report_cache, evidence_cache
    from config import APP_URL

    started_at = datetime.now(timezone.utc)
    s3_url: Optional[str] = None
    s3_pdf_url: Optional[str] = None
    pdf_path: Optional[str] = None

    # WebSocket progress notifications
    from modules.websocket_manager import notify_progress
    notify_progress(record_id, "started", 0, f"Analysis started for {filename}")

    enable_ml = os.getenv("ENABLE_ML_CLASSIFIER", "true").lower() == "true"
    enable_llm = os.getenv("ENABLE_LLM_SUMMARY", "true").strip().lower() == "true"

    grooming_detector = GroomingDetector(
        min_confidence_threshold=0.3,
        enable_ml_classifier=enable_ml,
        ml_max_sentences=int(os.getenv("ML_MAX_SENTENCES", "10")),
    )
    risk_scorer = WeightedRiskScorer()

    try:
        # ── Step 1: Transcription (if needed) ─────────────────────────────────
        if transcript is None:
            if audio_filepath is None:
                raise ValueError("Either transcript or audio_filepath must be provided")

            save_processing_status(record_id, "PROCESSING", "transcription", started_at=started_at)
            audit_log(f"{source}_analysis_started", meeting_id=record_id, details={"filename": filename})

            # S3 audio upload (non-fatal, only for direct audio uploads)
            if upload_to_s3:
                try:
                    s3_url = s3_upload_audio(audio_filepath, record_id, filename)
                    if s3_url:
                        logger.info(f"[#{record_id}] Audio uploaded to S3: {s3_url}")
                        update_s3_urls(record_id, s3_audio_url=s3_url)
                        audit_log("s3_upload_success", meeting_id=record_id, details={"s3_url": s3_url})
                except Exception as e:
                    logger.warning(f"[#{record_id}] S3 upload failed: {e}")

            # Transcribe
            from modules.transcriber import transcribe_audio
            try:
                transcript, timeline = transcribe_audio(audio_filepath)
                logger.info(f"[#{record_id}] Transcription complete: {len(transcript)} chars")
            finally:
                if delete_audio_after_transcription:
                    try:
                        os.remove(audio_filepath)
                        logger.info(f"[#{record_id}] Temp audio file deleted: {audio_filepath}")
                    except Exception as e:
                        logger.warning(f"[#{record_id}] Could not delete temp audio: {e}")
        else:
            # Transcript provided directly
            save_processing_status(record_id, "PROCESSING", "analysis", started_at=started_at)
            audit_log(f"{source}_analysis_started", meeting_id=record_id, details={"filename": filename})
            if timeline is None:
                timeline = [{"start": 0.0, "end": 0.0, "text": transcript, "speaker": "UNKNOWN"}]

        # ── Step 2: Detection ─────────────────────────────────────────────────
        save_processing_status(record_id, "PROCESSING", "analysis", started_at=started_at)
        notify_progress(record_id, "analysis", 30, "Running grooming detection...")
        analysis_result = grooming_detector.analyze_transcript(transcript=transcript, speaker_aware=True)
        findings = analysis_result.get("grouped_findings", [])
        evidence = extract_evidence(findings)
        save_processing_status(record_id, "PROCESSING", "scoring", started_at=started_at)
        notify_progress(record_id, "scoring", 50, "Calculating risk score...")

        # ── Step 3: Scoring & severity ────────────────────────────────────────
        risk_result = risk_scorer.calculate_score(findings)
        risk_score = risk_result.get("score", 0)
        severity = classify_severity(risk_score)
        logger.info(f"[#{record_id}] Risk score: {risk_score:.1f} → {severity}")

        # ── Step 3b: Temporal weighting & escalation detection ────────────────
        from modules.temporal_weighting import apply_temporal_weighting, detect_escalation_patterns
        total_sentences = len(transcript.split('\n')) if transcript else 0
        findings = apply_temporal_weighting(findings, total_sentences)
        escalation_info = detect_escalation_patterns(findings)

        # Re-score after temporal weighting if escalation detected
        if escalation_info.get("has_escalation"):
            risk_result = risk_scorer.calculate_score(findings)
            risk_score = risk_result.get("score", 0)
            # Apply escalation bonus to risk score (up to +15 points)
            escalation_bonus = min(15.0, escalation_info["escalation_score"] * 15)
            risk_score = min(100.0, risk_score + escalation_bonus)
            severity = classify_severity(risk_score)
            logger.info(
                f"[#{record_id}] Escalation detected: +{escalation_bonus:.1f} pts → "
                f"score={risk_score:.1f}, severity={severity}"
            )

        # ── Step 4: Stats & summaries ─────────────────────────────────────────
        stats = generate_stats(transcript, findings, severity, risk_score)
        summary = generate_summary(transcript, findings, risk_score, severity)

        if enable_llm:
            save_processing_status(record_id, "PROCESSING", "llm_summary", started_at=started_at)
            notify_progress(record_id, "llm_summary", 70, "Generating AI summary...")
            try:
                llm_summary = generate_llm_summary(transcript, findings, risk_score, severity)
            except Exception as e:
                logger.warning(f"[#{record_id}] LLM summary failed: {e}")
                llm_summary = f"LLM Summary unavailable: {e}"
        else:
            logger.info(f"[#{record_id}] LLM summary skipped (ENABLE_LLM_SUMMARY=false)")
            llm_summary = summary

        # ── Step 5: Vector store ──────────────────────────────────────────────
        try:
            store_transcript(record_id, transcript)
        except Exception as e:
            logger.warning(f"[#{record_id}] Vector store failed: {e}")

        # ── Step 6: PDF generation ────────────────────────────────────────────
        try:
            pdf_path = generate_pdf_report(
                report_id=record_id, filename=filename, severity=severity,
                risk_score=risk_score, findings=findings, summary=llm_summary,
            )
            update_pdf_path(record_id, pdf_path)
            try:
                s3_pdf_url = s3_upload_pdf(pdf_path, record_id)
                if s3_pdf_url:
                    update_s3_urls(record_id, s3_pdf_url=s3_pdf_url)
                    audit_log("s3_pdf_uploaded", meeting_id=record_id, details={"s3_url": s3_pdf_url})
            except Exception as e:
                logger.warning(f"[#{record_id}] S3 PDF upload failed: {e}")
        except Exception as e:
            logger.error(f"[#{record_id}] PDF generation failed: {e}", exc_info=True)

        # ── Step 7: MongoDB save ──────────────────────────────────────────────
        try:
            save_results = save_full_analysis(
                meeting_id=record_id, filename=filename, transcript=transcript,
                timeline=timeline, findings=findings, risk_score=risk_score,
                severity=severity, llm_summary=llm_summary, rule_summary=summary,
                stats=stats, started_at=started_at, s3_url=s3_url,
                evidence=evidence, pdf_path=pdf_path, s3_pdf_url=s3_pdf_url,
            )
            # Treat persistence of the core result + status as mandatory. If
            # these did not land, the record would be stuck in PROCESSING
            # forever, so surface it as FAILED instead of silently "completing".
            critical = ("analysis_results", "processing_status", "meeting_metadata")
            critical_failed = [c for c in critical if not save_results.get(c)]
            if critical_failed:
                # save_full_analysis() swallows the driver exception and reports
                # per-collection booleans, so there is no exception left to
                # inspect here. Losing several collections at once is what a
                # dropped connection looks like from this side, so treat it as
                # transient and let the retry decide.
                raise CriticalPersistenceError(
                    f"critical MongoDB writes failed: {critical_failed}",
                    transient=True,
                )
            logger.info(f"[#{record_id}] Analysis persisted to MongoDB.")
        except TRANSIENT_DB_ERRORS as e:
            raise CriticalPersistenceError(
                f"MongoDB save failed: {e}", transient=True
            ) from e

        # ── Step 8: Invalidate caches ─────────────────────────────────────────
        history_cache.invalidate()
        report_cache.invalidate()
        evidence_cache.invalidate()

        # ── Step 9: Auto-alert email ──────────────────────────────────────────
        send_parent = should_parent_alert(severity)
        send_admin  = should_auto_alert(severity)

        if send_parent or send_admin:
            try:
                if send_parent:
                    # Parent email — simplified, no internal data
                    send_alert_email(
                        report_id=record_id, filename=filename, severity=severity,
                        risk_score=risk_score, findings=findings, summary=llm_summary,
                        stats=stats, pdf_path=pdf_path, app_url=APP_URL,
                        transcript=transcript,
                    )
                if send_admin:
                    # Admin email — full detail for internal staff
                    send_admin_report(
                        report_id=record_id, filename=filename, severity=severity,
                        risk_score=risk_score, findings=findings,
                        llm_summary=llm_summary or "", rule_summary=summary or "",
                        stats=stats, pdf_path=pdf_path, app_url=APP_URL,
                        transcript=transcript,
                    )
                audit_log("alert_email_sent", meeting_id=record_id,
                          details={"severity": severity, "risk_score": risk_score,
                                   "parent_notified": send_parent, "admin_notified": send_admin})
            except Exception as e:
                logger.warning(f"[#{record_id}] Auto-alert email failed: {e}")

        logger.info(f"[#{record_id}] Analysis COMPLETED ({source}) — severity={severity}, score={risk_score:.1f}")
        notify_progress(record_id, "completed", 100, "Analysis complete",
                       severity=severity, risk_score=risk_score)

        # ── Step 10: Notify MW backend via webhook ────────────────────────────
        try:
            from api.webhook_routes import notify_mw_backend_sync
            notify_mw_backend_sync(
                meeting_id=record_id,
                status="COMPLETED",
                severity=severity,
                risk_score=risk_score,
            )
        except Exception as e:
            logger.warning(f"[#{record_id}] MW webhook notification failed: {e}")

    except Exception as e:
        # Transient infrastructure failures are the caller's to retry. Leave the
        # record PROCESSING and re-raise: marking it FAILED here would both lie
        # about a job that is about to be retried and race the retry's own
        # status writes. tasks/analysis_tasks.py decides how many attempts to
        # spend before giving up and marking it FAILED for real.
        if isinstance(e, TRANSIENT_DB_ERRORS) or (
            isinstance(e, CriticalPersistenceError) and e.transient
        ):
            logger.warning(
                f"[#{record_id}] Pipeline hit a transient failure ({source}): {e} "
                f"— leaving PROCESSING for retry."
            )
            raise

        save_processing_status(record_id, "FAILED", "error",
                               started_at=started_at, completed_at=datetime.now(timezone.utc), error=str(e))
        update_meeting_status(record_id, "FAILED")
        audit_log(f"{source}_analysis_failed", meeting_id=record_id, details={"error": str(e)})
        logger.error(f"[#{record_id}] Pipeline FAILED ({source}): {e}", exc_info=True)
        notify_progress(record_id, "failed", 0, str(e), error=str(e))

        # Notify MW backend of failure
        try:
            from api.webhook_routes import notify_mw_backend_sync
            notify_mw_backend_sync(
                meeting_id=record_id,
                status="FAILED",
                error=str(e),
            )
        except Exception:
            pass
