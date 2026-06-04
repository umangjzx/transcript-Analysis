"""
Audio Safety Analysis Service.

This service orchestrates the complete pipeline for audio safety analysis:
1. Transcription → 2. Detection → 3. Risk Scoring → 4. Severity
5. Summaries → 6. PDF → 7. MongoDB Persistence → 8. S3 → 9. Email alert

SQLite removed — MongoDB is the sole persistence layer.
"""

import os
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timezone
import asyncio
from functools import wraps

from modules.grooming_detector import GroomingDetector
from modules.risk_scorer import WeightedRiskScorer
from modules.severity_classifier import classify_severity
from modules.summarizer import generate_summary
from modules.llm_summarizer import generate_llm_summary
from modules.report_generator import generate_pdf_report
from modules.transcriber import transcribe_audio
from modules.evidence_extractor import extract_evidence
from modules.stats import generate_stats
from modules.chatbot import store_transcript
from modules.email_notifier import send_alert_email, should_auto_alert
from modules.s3_storage import upload_audio as s3_upload_audio, upload_pdf_report as s3_upload_pdf

# MongoDB — sole persistence layer
from database.mongo import (
    save_full_analysis,
    update_s3_urls,
    update_meeting_status,
    save_processing_status,
)

from config import APP_URL

logger = logging.getLogger(__name__)


def async_wrap(func):
    """Decorator to make synchronous functions async-compatible."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
    return wrapper


class AudioSafetyService:
    """
    Service for comprehensive audio safety analysis.
    Writes exclusively to MongoDB + S3 — no SQLite dependency.
    """

    def __init__(
        self,
        grooming_detector: Optional[GroomingDetector] = None,
        risk_scorer: Optional[WeightedRiskScorer] = None,
        min_confidence_threshold: float = 0.3,
        enable_llm_summary: bool = True,
        enable_vector_storage: bool = True,
    ):
        _enable_ml = os.getenv("ENABLE_ML_CLASSIFIER", "false").lower() == "true"

        self.grooming_detector = grooming_detector or GroomingDetector(
            min_confidence_threshold=min_confidence_threshold,
            enable_ml_classifier=_enable_ml,
        )
        self.risk_scorer = risk_scorer or WeightedRiskScorer()
        self.enable_llm_summary = enable_llm_summary
        self.enable_vector_storage = enable_vector_storage

        logger.info(
            "AudioSafetyService initialized (ML classifier %s)",
            "ENABLED" if _enable_ml else "DISABLED",
        )
    
    async def analyze_audio_file(
        self,
        filepath: str,
        filename: str,
        record_id: int,
    ) -> Dict[str, Any]:
        """
        Perform complete audio safety analysis pipeline.
        record_id must be pre-allocated by the caller via next_meeting_id().
        """
        logger.info(f"Starting analysis for file: {filename} (id={record_id})")

        s3_url: Optional[str] = None
        s3_pdf_url: Optional[str] = None
        pdf_path: Optional[str] = None

        try:
            # Step 1: S3 audio upload (non-blocking)
            try:
                s3_url = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: s3_upload_audio(filepath, record_id, filename)
                )
                if s3_url:
                    logger.info(f"Audio uploaded to S3: {s3_url}")
                    update_s3_urls(record_id, s3_audio_url=s3_url)
            except Exception as _e:
                logger.warning(f"S3 audio upload failed (non-fatal): {_e}")

            # Step 2: Transcription
            transcript, timeline = await self._transcribe_audio(filepath)
            logger.info(f"Transcription completed: {len(transcript)} characters")
            save_processing_status(record_id, "PROCESSING", "analysis")

            # Step 3: Grooming Detection
            detection_results = await self._detect_grooming_patterns(transcript)
            logger.info(f"Detection completed: {detection_results['summary']['total_findings']} findings")

            # Step 4: Evidence Extraction
            evidence = await self._extract_evidence(detection_results['grouped_findings'])
            logger.info(f"Evidence extracted: {len(evidence)} items")
            save_processing_status(record_id, "PROCESSING", "scoring")

            # Step 5: Risk Scoring
            risk_result = await self._calculate_risk_score(detection_results['grouped_findings'])
            logger.info(f"Risk score calculated: {risk_result['score']}/100 ({risk_result['level']})")

            # Step 6: Severity Classification
            severity = await self._classify_severity(risk_result['score'])
            logger.info(f"Severity classified: {severity}")

            # Step 7: Statistics Generation
            stats = await self._generate_statistics(
                transcript, detection_results['grouped_findings'], severity, risk_result['score'],
            )

            # Step 8: Rule-based Summary
            rule_summary = await self._generate_rule_summary(
                transcript, detection_results['grouped_findings'], risk_result['score'], severity,
            )
            logger.info("Rule-based summary generated")

            # Step 9: LLM Summary (optional)
            save_processing_status(record_id, "PROCESSING", "llm_summary")
            llm_summary = await self._generate_llm_summary(
                transcript, detection_results['grouped_findings'], risk_result['score'], severity,
            )

            # Step 10: Vector Storage (optional)
            if self.enable_vector_storage:
                await self._store_in_vector_db(record_id, transcript)

            # Step 11: PDF Report Generation
            pdf_path = await self._generate_pdf_report(
                record_id=record_id,
                filename=filename,
                severity=severity,
                risk_score=risk_result['score'],
                findings=detection_results['grouped_findings'],
                summary=llm_summary or rule_summary,
            )
            logger.info(f"PDF report generated: {pdf_path}")

            # Step 12: S3 PDF upload (non-blocking)
            try:
                s3_pdf_url = await asyncio.get_event_loop().run_in_executor(
                    None, lambda: s3_upload_pdf(pdf_path, record_id)
                )
                if s3_pdf_url:
                    logger.info(f"PDF uploaded to S3: {s3_pdf_url}")
            except Exception as _e:
                logger.warning(f"S3 PDF upload failed (non-fatal): {_e}")

            # Step 13: MongoDB — full analysis save
            try:
                save_full_analysis(
                    meeting_id=record_id,
                    filename=filename,
                    transcript=transcript,
                    timeline=timeline,
                    findings=detection_results['grouped_findings'],
                    risk_score=risk_result['score'],
                    severity=severity,
                    llm_summary=llm_summary or rule_summary,
                    rule_summary=rule_summary,
                    stats=stats,
                    s3_url=s3_url,
                    evidence=evidence,
                    pdf_path=pdf_path,
                    s3_pdf_url=s3_pdf_url,
                )
                logger.info(f"MongoDB: full analysis saved for record #{record_id}")
            except Exception as _e:
                logger.warning(f"MongoDB save failed (non-fatal): {_e}")

            # Step 14: Auto-alert email
            if should_auto_alert(severity):
                try:
                    _transcript_snap = transcript  # capture for lambda closure
                    await asyncio.get_event_loop().run_in_executor(
                        None,
                        lambda: send_alert_email(
                            report_id=record_id,
                            filename=filename,
                            severity=severity,
                            risk_score=risk_result['score'],
                            findings=detection_results['grouped_findings'],
                            summary=llm_summary or rule_summary,
                            stats=stats,
                            pdf_path=pdf_path,
                            app_url=APP_URL,
                            transcript=_transcript_snap,
                        ),
                    )
                    logger.info(f"Auto-alert email sent for severity={severity}")
                except Exception as _e:
                    logger.warning(f"Auto-alert email failed (non-fatal): {_e}")

            response = self._build_response(
                record_id=record_id,
                filename=filename,
                transcript=transcript,
                timeline=timeline,
                detection_results=detection_results,
                evidence=evidence,
                stats=stats,
                rule_summary=rule_summary,
                llm_summary=llm_summary,
                severity=severity,
                risk_result=risk_result,
                pdf_path=pdf_path or "",
            )

            logger.info(f"Analysis completed successfully for: {filename}")
            return response

        except Exception as e:
            logger.error(f"Analysis failed for {filename}: {str(e)}", exc_info=True)
            try:
                save_processing_status(record_id, "FAILED", "error", error=str(e))
                update_meeting_status(record_id, "FAILED")
            except Exception:
                pass
            raise
    
    @async_wrap
    def _transcribe_audio(self, filepath: str) -> Tuple[str, List[Dict]]:
        try:
            return transcribe_audio(filepath)
        except Exception as e:
            raise Exception(f"Transcription failed: {str(e)}")

    @async_wrap
    def _detect_grooming_patterns(self, transcript: str) -> Dict[str, Any]:
        try:
            return self.grooming_detector.analyze_transcript(
                transcript=transcript, speaker_aware=True
            )
        except Exception as e:
            raise Exception(f"Grooming detection failed: {str(e)}")

    @async_wrap
    def _extract_evidence(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        try:
            return extract_evidence(findings)
        except Exception as e:
            logger.warning(f"Evidence extraction failed: {str(e)}")
            return []

    @async_wrap
    def _calculate_risk_score(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        try:
            return self.risk_scorer.calculate_score(findings)
        except Exception as e:
            logger.error(f"Risk scoring failed: {str(e)}")
            return {"score": 0.0, "level": "Safe", "breakdown": {}, "total_findings": 0}

    @async_wrap
    def _classify_severity(self, risk_score: float) -> str:
        try:
            return classify_severity(risk_score)
        except Exception as e:
            logger.warning(f"Severity classification failed: {str(e)}")
            return "Unknown"

    @async_wrap
    def _generate_statistics(
        self, transcript: str, findings: List[Dict[str, Any]],
        severity: str, risk_score: float,
    ) -> Dict[str, Any]:
        try:
            return generate_stats(transcript, findings, severity, risk_score)
        except Exception as e:
            logger.warning(f"Statistics generation failed: {str(e)}")
            return {}

    @async_wrap
    def _generate_rule_summary(
        self, transcript: str, findings: List[Dict[str, Any]],
        risk_score: float, severity: str,
    ) -> str:
        try:
            return generate_summary(transcript, findings, risk_score, severity)
        except Exception as e:
            logger.warning(f"Rule summary generation failed: {str(e)}")
            return "Summary generation failed."

    @async_wrap
    def _generate_llm_summary(
        self, transcript: str, findings: List[Dict[str, Any]],
        risk_score: float, severity: str,
    ) -> Optional[str]:
        if not self.enable_llm_summary:
            return None
        try:
            return generate_llm_summary(transcript, findings, risk_score, severity)
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {str(e)}")
            return None

    @async_wrap
    def _store_in_vector_db(self, record_id: int, transcript: str) -> None:
        try:
            store_transcript(record_id, transcript)
            logger.info(f"Transcript stored in vector DB for record {record_id}")
        except Exception as e:
            logger.warning(f"Vector storage failed: {str(e)}")

    @async_wrap
    def _generate_pdf_report(
        self, record_id: int, filename: str, severity: str,
        risk_score: float, findings: List[Dict[str, Any]], summary: str,
    ) -> str:
        try:
            return generate_pdf_report(
                report_id=record_id, filename=filename, severity=severity,
                risk_score=risk_score, findings=findings, summary=summary,
            )
        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            return f"PDF generation failed: {str(e)}"

    def _build_response(
        self,
        record_id: int,
        filename: str,
        transcript: str,
        timeline: List[Dict],
        detection_results: Dict[str, Any],
        evidence: List[Dict[str, Any]],
        stats: Dict[str, Any],
        rule_summary: str,
        llm_summary: Optional[str],
        severity: str,
        risk_result: Dict[str, Any],
        pdf_path: str,
    ) -> Dict[str, Any]:
        return {
            "id": record_id,
            "filename": filename,
            "transcript": transcript,
            "timeline": timeline,
            "detection": {
                "findings": detection_results['findings'],
                "grouped_findings": detection_results['grouped_findings'],
                "summary": detection_results['summary'],
                "metadata": detection_results['metadata'],
            },
            "evidence": evidence,
            "risk": {
                "score": risk_result['score'],
                "level": risk_result['level'],
                "breakdown": risk_result['breakdown'],
                "category_counts": risk_result['category_counts'],
            },
            "severity": severity,
            "stats": stats,
            "summaries": {
                "rule_based": rule_summary,
                "llm_based": llm_summary,
            },
            "pdf_report": pdf_path,
            "analysis_metadata": {
                "analyzed_at": datetime.now(timezone.utc).isoformat(),
                "min_confidence_threshold": self.grooming_detector.min_confidence_threshold,
                "total_findings": detection_results['summary']['total_findings'],
                "high_confidence_findings": detection_results['summary'].get('high_confidence_findings', 0),
            },
        }


def get_audio_safety_service(
    min_confidence: float = 0.3,
    enable_llm: bool = True,
    enable_vector: bool = True,
) -> AudioSafetyService:
    """Factory function for creating AudioSafetyService instances."""
    return AudioSafetyService(
        min_confidence_threshold=min_confidence,
        enable_llm_summary=enable_llm,
        enable_vector_storage=enable_vector,
    )
