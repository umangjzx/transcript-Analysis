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

logger = logging.getLogger(__name__)


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
    from modules.email_notifier import send_alert_email, should_auto_alert
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
            save_full_analysis(
                meeting_id=record_id, filename=filename, transcript=transcript,
                timeline=timeline, findings=findings, risk_score=risk_score,
                severity=severity, llm_summary=llm_summary, rule_summary=summary,
                stats=stats, started_at=started_at, s3_url=s3_url,
                evidence=evidence, pdf_path=pdf_path, s3_pdf_url=s3_pdf_url,
            )
        except Exception as e:
            logger.warning(f"[#{record_id}] MongoDB save failed: {e}")
            try:
                save_processing_status(
                    record_id, "FAILED", "error",
                    started_at=started_at,
                    completed_at=datetime.now(timezone.utc),
                    error=str(e),
                )
                update_meeting_status(record_id, "FAILED")
            except Exception:
                pass

        # ── Step 8: Invalidate caches ─────────────────────────────────────────
        history_cache.invalidate()
        report_cache.invalidate()
        evidence_cache.invalidate()

        # ── Step 9: Auto-alert email ──────────────────────────────────────────
        if should_auto_alert(severity):
            try:
                send_alert_email(
                    report_id=record_id, filename=filename, severity=severity,
                    risk_score=risk_score, findings=findings, summary=llm_summary,
                    stats=stats, pdf_path=pdf_path, app_url=APP_URL,
                    transcript=transcript,
                )
                audit_log("alert_email_sent", meeting_id=record_id,
                          details={"severity": severity, "risk_score": risk_score})
            except Exception as e:
                logger.warning(f"[#{record_id}] Auto-alert email failed: {e}")

        logger.info(f"[#{record_id}] Analysis COMPLETED ({source}) — severity={severity}, score={risk_score:.1f}")
        notify_progress(record_id, "completed", 100, "Analysis complete",
                       severity=severity, risk_score=risk_score)

    except Exception as e:
        save_processing_status(record_id, "FAILED", "error",
                               started_at=started_at, completed_at=datetime.now(timezone.utc), error=str(e))
        update_meeting_status(record_id, "FAILED")
        audit_log(f"{source}_analysis_failed", meeting_id=record_id, details={"error": str(e)})
        logger.error(f"[#{record_id}] Pipeline FAILED ({source}): {e}", exc_info=True)
        notify_progress(record_id, "failed", 0, str(e), error=str(e))
