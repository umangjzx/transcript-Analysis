"""
Audio Safety Analysis Service.

This service orchestrates the complete pipeline for audio safety analysis:
1. Transcription
2. Grooming Detection
3. Risk Scoring
4. Severity Classification
5. Summary Generation (Rule-based + LLM)
6. PDF Report Generation
7. Database Persistence

Implements dependency injection, async compatibility, error handling, and logging.
"""

import logging
import json
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime
import asyncio
from functools import wraps

# Import detection modules
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

# Database
from database.models import AudioAnalysis
from sqlalchemy.orm import Session

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    
    This service integrates all detection and analysis components into
    a unified pipeline with proper error handling, logging, and database persistence.
    """
    
    def __init__(
        self,
        grooming_detector: Optional[GroomingDetector] = None,
        risk_scorer: Optional[WeightedRiskScorer] = None,
        min_confidence_threshold: float = 0.3,
        enable_llm_summary: bool = True,
        enable_vector_storage: bool = True
    ):
        """
        Initialize the audio safety service.
        
        Args:
            grooming_detector: Custom grooming detector instance (optional)
            risk_scorer: Custom risk scorer instance (optional)
            min_confidence_threshold: Minimum confidence for detections
            enable_llm_summary: Enable LLM-based summary generation
            enable_vector_storage: Enable vector storage for chatbot
        """
        # Initialize components with dependency injection
        self.grooming_detector = grooming_detector or GroomingDetector(
            min_confidence_threshold=min_confidence_threshold
        )
        self.risk_scorer = risk_scorer or WeightedRiskScorer()
        
        self.enable_llm_summary = enable_llm_summary
        self.enable_vector_storage = enable_vector_storage
        
        logger.info("AudioSafetyService initialized")
    
    async def analyze_audio_file(
        self,
        filepath: str,
        filename: str,
        db_session: Session
    ) -> Dict[str, Any]:
        """
        Perform complete audio safety analysis pipeline.
        
        Args:
            filepath: Path to audio file
            filename: Original filename
            db_session: Database session for persistence
        
        Returns:
            Complete analysis results dictionary
        
        Raises:
            Exception: If critical pipeline step fails
        """
        logger.info(f"Starting analysis for file: {filename}")
        
        try:
            # Step 1: Transcription
            transcript, timeline = await self._transcribe_audio(filepath)
            logger.info(f"Transcription completed: {len(transcript)} characters")
            
            # Step 2: Grooming Detection
            detection_results = await self._detect_grooming_patterns(transcript)
            logger.info(f"Detection completed: {detection_results['summary']['total_findings']} findings")
            
            # Step 3: Evidence Extraction
            evidence = await self._extract_evidence(detection_results['grouped_findings'])
            logger.info(f"Evidence extracted: {len(evidence)} items")
            
            # Step 4: Risk Scoring
            risk_result = await self._calculate_risk_score(detection_results['grouped_findings'])
            logger.info(f"Risk score calculated: {risk_result['score']}/100 ({risk_result['level']})")
            
            # Step 5: Severity Classification
            severity = await self._classify_severity(risk_result['score'])
            logger.info(f"Severity classified: {severity}")
            
            # Step 6: Statistics Generation
            stats = await self._generate_statistics(
                transcript,
                detection_results['grouped_findings'],
                severity,
                risk_result['score']
            )
            
            # Step 7: Rule-based Summary
            rule_summary = await self._generate_rule_summary(
                transcript,
                detection_results['grouped_findings'],
                risk_result['score'],
                severity
            )
            logger.info("Rule-based summary generated")
            
            # Step 8: LLM Summary (optional)
            llm_summary = await self._generate_llm_summary(
                transcript,
                detection_results['grouped_findings'],
                risk_result['score'],
                severity
            )
            
            # Step 9: Database Persistence
            record = await self._save_to_database(
                db_session=db_session,
                filename=filename,
                transcript=transcript,
                findings=detection_results['grouped_findings'],
                evidence=evidence,
                stats=stats,
                rule_summary=rule_summary,
                llm_summary=llm_summary,
                severity=severity,
                risk_score=risk_result['score']
            )
            logger.info(f"Analysis saved to database with ID: {record.id}")
            
            # Step 10: Vector Storage (optional)
            if self.enable_vector_storage:
                await self._store_in_vector_db(record.id, transcript)
            
            # Step 11: PDF Report Generation
            pdf_path = await self._generate_pdf_report(
                record_id=record.id,
                filename=filename,
                severity=severity,
                risk_score=risk_result['score'],
                findings=detection_results['grouped_findings'],
                summary=llm_summary or rule_summary
            )
            
            # Update PDF path in database
            await self._update_pdf_path(db_session, record.id, pdf_path)
            logger.info(f"PDF report generated: {pdf_path}")
            
            # Prepare response
            response = self._build_response(
                record_id=record.id,
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
                pdf_path=pdf_path
            )
            
            logger.info(f"Analysis completed successfully for: {filename}")
            return response
            
        except Exception as e:
            logger.error(f"Analysis failed for {filename}: {str(e)}", exc_info=True)
            raise
    
    @async_wrap
    def _transcribe_audio(self, filepath: str) -> Tuple[str, List[Dict]]:
        """Transcribe audio file."""
        try:
            return transcribe_audio(filepath)
        except Exception as e:
            logger.error(f"Transcription failed: {str(e)}")
            raise Exception(f"Transcription failed: {str(e)}")
    
    @async_wrap
    def _detect_grooming_patterns(self, transcript: str) -> Dict[str, Any]:
        """Detect grooming patterns in transcript."""
        try:
            return self.grooming_detector.analyze_transcript(
                transcript=transcript,
                speaker_aware=True
            )
        except Exception as e:
            logger.error(f"Grooming detection failed: {str(e)}")
            raise Exception(f"Grooming detection failed: {str(e)}")
    
    @async_wrap
    def _extract_evidence(self, findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract evidence from findings."""
        try:
            return extract_evidence(findings)
        except Exception as e:
            logger.warning(f"Evidence extraction failed: {str(e)}")
            # Return empty list on failure (non-critical)
            return []
    
    @async_wrap
    def _calculate_risk_score(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Calculate risk score from findings."""
        try:
            return self.risk_scorer.calculate_score(findings)
        except Exception as e:
            logger.error(f"Risk scoring failed: {str(e)}")
            # Return safe default on failure
            return {
                "score": 0.0,
                "level": "Safe",
                "breakdown": {},
                "total_findings": 0
            }
    
    @async_wrap
    def _classify_severity(self, risk_score: float) -> str:
        """Classify severity based on risk score."""
        try:
            return classify_severity(risk_score)
        except Exception as e:
            logger.warning(f"Severity classification failed: {str(e)}")
            return "Unknown"
    
    @async_wrap
    def _generate_statistics(
        self,
        transcript: str,
        findings: List[Dict[str, Any]],
        severity: str,
        risk_score: float
    ) -> Dict[str, Any]:
        """Generate statistics."""
        try:
            return generate_stats(transcript, findings, severity, risk_score)
        except Exception as e:
            logger.warning(f"Statistics generation failed: {str(e)}")
            return {}
    
    @async_wrap
    def _generate_rule_summary(
        self,
        transcript: str,
        findings: List[Dict[str, Any]],
        risk_score: float,
        severity: str
    ) -> str:
        """Generate rule-based summary."""
        try:
            return generate_summary(transcript, findings, risk_score, severity)
        except Exception as e:
            logger.warning(f"Rule summary generation failed: {str(e)}")
            return "Summary generation failed."
    
    @async_wrap
    def _generate_llm_summary(
        self,
        transcript: str,
        findings: List[Dict[str, Any]],
        risk_score: float,
        severity: str
    ) -> Optional[str]:
        """Generate LLM-based summary."""
        if not self.enable_llm_summary:
            return None
        
        try:
            return generate_llm_summary(transcript, findings, risk_score, severity)
        except Exception as e:
            logger.warning(f"LLM summary generation failed: {str(e)}")
            return None
    
    @async_wrap
    def _save_to_database(
        self,
        db_session: Session,
        filename: str,
        transcript: str,
        findings: List[Dict[str, Any]],
        evidence: List[Dict[str, Any]],
        stats: Dict[str, Any],
        rule_summary: str,
        llm_summary: Optional[str],
        severity: str,
        risk_score: float
    ) -> AudioAnalysis:
        """Save analysis results to database."""
        try:
            record = AudioAnalysis(
                filename=filename,
                transcript=transcript,
                findings=json.dumps(findings),
                evidence=json.dumps(evidence),
                stats=json.dumps(stats),
                summary=rule_summary,
                llm_summary=llm_summary or rule_summary,
                severity=severity,
                risk_score=risk_score,
                pdf_path=""
            )
            
            db_session.add(record)
            db_session.commit()
            db_session.refresh(record)
            
            return record
            
        except Exception as e:
            db_session.rollback()
            logger.error(f"Database save failed: {str(e)}")
            raise Exception(f"Database save failed: {str(e)}")
    
    @async_wrap
    def _store_in_vector_db(self, record_id: int, transcript: str) -> None:
        """Store transcript in vector database for chatbot."""
        try:
            store_transcript(record_id, transcript)
            logger.info(f"Transcript stored in vector DB for record {record_id}")
        except Exception as e:
            logger.warning(f"Vector storage failed: {str(e)}")
            # Non-critical, don't raise
    
    @async_wrap
    def _generate_pdf_report(
        self,
        record_id: int,
        filename: str,
        severity: str,
        risk_score: float,
        findings: List[Dict[str, Any]],
        summary: str
    ) -> str:
        """Generate PDF report."""
        try:
            return generate_pdf_report(
                report_id=record_id,
                filename=filename,
                severity=severity,
                risk_score=risk_score,
                findings=findings,
                summary=summary
            )
        except Exception as e:
            logger.error(f"PDF generation failed: {str(e)}")
            return f"PDF generation failed: {str(e)}"
    
    @async_wrap
    def _update_pdf_path(
        self,
        db_session: Session,
        record_id: int,
        pdf_path: str
    ) -> None:
        """Update PDF path in database."""
        try:
            record = db_session.query(AudioAnalysis).filter(
                AudioAnalysis.id == record_id
            ).first()
            
            if record:
                record.pdf_path = pdf_path
                db_session.commit()
                
        except Exception as e:
            logger.warning(f"PDF path update failed: {str(e)}")
            db_session.rollback()
    
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
        pdf_path: str
    ) -> Dict[str, Any]:
        """Build final response dictionary."""
        return {
            "id": record_id,
            "filename": filename,
            "transcript": transcript,
            "timeline": timeline,
            "detection": {
                "findings": detection_results['findings'],
                "grouped_findings": detection_results['grouped_findings'],
                "summary": detection_results['summary'],
                "metadata": detection_results['metadata']
            },
            "evidence": evidence,
            "risk": {
                "score": risk_result['score'],
                "level": risk_result['level'],
                "breakdown": risk_result['breakdown'],
                "category_counts": risk_result['category_counts']
            },
            "severity": severity,
            "stats": stats,
            "summaries": {
                "rule_based": rule_summary,
                "llm_based": llm_summary
            },
            "pdf_report": pdf_path,
            "analysis_metadata": {
                "analyzed_at": datetime.now().isoformat(),
                "min_confidence_threshold": self.grooming_detector.min_confidence_threshold,
                "total_findings": detection_results['summary']['total_findings'],
                "high_confidence_findings": detection_results['summary'].get('high_confidence_findings', 0)
            }
        }


# Dependency injection factory
def get_audio_safety_service(
    min_confidence: float = 0.3,
    enable_llm: bool = True,
    enable_vector: bool = True
) -> AudioSafetyService:
    """
    Factory function for creating AudioSafetyService instances.
    
    Args:
        min_confidence: Minimum confidence threshold
        enable_llm: Enable LLM summary
        enable_vector: Enable vector storage
    
    Returns:
        Configured AudioSafetyService instance
    """
    return AudioSafetyService(
        min_confidence_threshold=min_confidence,
        enable_llm_summary=enable_llm,
        enable_vector_storage=enable_vector
    )
