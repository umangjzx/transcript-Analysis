"""
FastAPI routes for Audio Safety Analysis.

This module defines all API endpoints with proper error handling,
logging, validation, and documentation.
"""

import os
import json
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

# Import schemas
from schemas.audio_analysis_schemas import (
    AnalysisResponse,
    HistoryResponse,
    HistoryItem,
    ReportResponse,
    EvidenceResponse,
    ChatRequest,
    ChatResponse,
    HealthResponse,
    ErrorResponse,
    AnalysisConfigRequest
)

# Import service
from services.audio_safety_service import AudioSafetyService, get_audio_safety_service

# Import database
from database.db import SessionLocal
from database.models import AudioAnalysis

# Import config
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS

# Import chatbot
from modules.chatbot import answer_question

# Import caching
from modules.cache import history_cache, report_cache, evidence_cache

# Import auth
from auth import get_current_user

# Configure logging
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(
    prefix="/api/v1",
    tags=["Audio Safety Analysis"]
)


# ============================================================================
# DEPENDENCIES
# ============================================================================

def get_db():
    """Database session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_service() -> AudioSafetyService:
    """Audio safety service dependency."""
    return get_audio_safety_service()


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health Check",
    description="Check if the service is running"
)
async def health_check():
    """Health check endpoint."""
    from app import _enable_ml
    return HealthResponse(
        status="healthy",
        service="Audio Safety Analyzer",
        version="2.0.0",
        timestamp=datetime.now().isoformat(),
    )


# ============================================================================
# ANALYZE AUDIO
# ============================================================================

@router.post(
    "/analyze",
    response_model=AnalysisResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Analyze Audio File",
    description="Upload and analyze an audio file for grooming patterns",
    responses={
        201: {"description": "Analysis completed successfully"},
        400: {"model": ErrorResponse, "description": "Invalid file format"},
        500: {"model": ErrorResponse, "description": "Analysis failed"}
    }
)
async def analyze_audio(
    file: UploadFile = File(..., description="Audio file to analyze"),
    db: Session = Depends(get_db),
    service: AudioSafetyService = Depends(get_service)
):
    """
    Analyze an audio file for grooming patterns.

    Supported formats: .mp3, .wav, .m4a, .aac, .ogg
    """
    import uuid as _uuid
    from app import MAX_UPLOAD_BYTES

    logger.info(f"Received analysis request for file: {file.filename}")

    # Validate file extension
    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {extension}. Supported: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Read into memory so we can enforce the size limit
    content = await file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
        )

    # Use a UUID-based filename on disk to prevent path traversal
    safe_disk_name = f"{_uuid.uuid4().hex}{extension}"
    original_filename = file.filename or safe_disk_name

    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(UPLOAD_FOLDER, safe_disk_name)
        with open(filepath, "wb") as buffer:
            buffer.write(content)
        logger.info(f"File saved to: {filepath}")
    except Exception as e:
        logger.error(f"File save failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save file: {str(e)}"
        )

    # Perform analysis
    try:
        result = await service.analyze_audio_file(
            filepath=filepath,
            filename=original_filename,
            db_session=db
        )
        logger.info(f"Analysis completed successfully for: {original_filename}")
        return result
    except Exception as e:
        logger.error(f"Analysis failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Analysis failed: {str(e)}"
        )


# ============================================================================
# HISTORY
# ============================================================================

@router.get(
    "/history",
    response_model=HistoryResponse,
    summary="Get Analysis History",
    description="Retrieve list of all analysis reports (cached)"
)
async def get_history(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100,
    _user = Depends(get_current_user)
):
    """Get list of all analysis reports with caching."""
    try:
        # Create cache key
        cache_key = f"history_{skip}_{limit}"
        
        # Try to get from cache
        cached_result = history_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"History cache hit")
            return cached_result
        
        # Cache miss — query database
        reports = db.query(AudioAnalysis).offset(skip).limit(limit).all()
        total = db.query(AudioAnalysis).count()
        
        items = [
            HistoryItem(
                id=report.id,
                filename=report.filename,
                severity=report.severity,
                risk_score=report.risk_score,
                created_at=report.created_at.isoformat() if report.created_at else None,
                analyzed_at=report.created_at.isoformat() if report.created_at else None,
            )
            for report in reports
        ]
        
        result = HistoryResponse(reports=items, total=total)
        
        # Cache the result
        history_cache.set(cache_key, result)
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to retrieve history: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve history: {str(e)}"
        )


# ============================================================================
# GET REPORT
# ============================================================================

@router.get(
    "/report/{report_id}",
    response_model=ReportResponse,
    summary="Get Analysis Report",
    description="Retrieve detailed analysis report by ID (cached)",
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"}
    }
)
async def get_report(
    report_id: int,
    db: Session = Depends(get_db),
    _user = Depends(get_current_user)
):
    """Get detailed analysis report by ID with caching."""
    try:
        # Create cache key
        cache_key = f"report_{report_id}"
        
        # Try to get from cache
        cached_result = report_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Report cache hit for ID {report_id}")
            return cached_result
        
        # Cache miss — query database
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        result = ReportResponse(
            id=report.id,
            filename=report.filename,
            transcript=report.transcript,
            findings=report.findings if isinstance(report.findings, list) else [],
            evidence=report.evidence if isinstance(report.evidence, list) else [],
            stats=report.stats if isinstance(report.stats, dict) else {},
            summary=report.summary,
            llm_summary=report.llm_summary,
            severity=report.severity,
            risk_score=report.risk_score,
            pdf_path=report.pdf_path,
            created_at=report.created_at.isoformat() if report.created_at else None
        )
        
        # Cache the result
        report_cache.set(cache_key, result)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve report {report_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve report: {str(e)}"
        )


# ============================================================================
# GET EVIDENCE
# ============================================================================

@router.get(
    "/report/{report_id}/evidence",
    response_model=EvidenceResponse,
    summary="Get Report Evidence",
    description="Retrieve evidence items for a specific report (cached)",
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"}
    }
)
async def get_evidence(
    report_id: int,
    db: Session = Depends(get_db),
    _user = Depends(get_current_user)
):
    """Get evidence items for a specific report with caching."""
    try:
        # Create cache key
        cache_key = f"evidence_{report_id}"
        
        # Try to get from cache
        cached_result = evidence_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Evidence cache hit for report {report_id}")
            return cached_result
        
        # Cache miss — query database
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        result = EvidenceResponse(
            report_id=report_id,
            severity=report.severity,
            risk_score=report.risk_score,
            evidence=report.evidence if isinstance(report.evidence, list) else []
        )
        
        # Cache the result
        evidence_cache.set(cache_key, result)
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve evidence for report {report_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve evidence: {str(e)}"
        )


# ============================================================================
# GET STATISTICS
# ============================================================================

@router.get(
    "/report/{report_id}/stats",
    summary="Get Report Statistics",
    description="Retrieve statistics for a specific report",
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"}
    }
)
async def get_report_stats(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Get statistics for a specific report."""
    try:
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        st = report.stats
        if isinstance(st, str):
            try:
                st = json.loads(st)
            except Exception:
                st = {}
        return st or {}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to retrieve stats for report {report_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve statistics: {str(e)}"
        )


# ============================================================================
# DOWNLOAD PDF
# ============================================================================

@router.get(
    "/report/{report_id}/pdf",
    summary="Download PDF Report",
    description="Download PDF report for a specific analysis",
    responses={
        404: {"model": ErrorResponse, "description": "PDF not found"}
    }
)
async def download_pdf(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Download PDF report."""
    try:
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        pdf_path = report.pdf_path or f"reports/report_{report_id}.pdf"
        
        if not os.path.exists(pdf_path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="PDF report not found"
            )
        
        return FileResponse(
            path=pdf_path,
            media_type="application/pdf",
            filename=f"report_{report_id}.pdf"
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download PDF for report {report_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download PDF: {str(e)}"
        )


# ============================================================================
# CHATBOT
# ============================================================================

@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask Question About Report",
    description="Ask questions about a specific analysis report using the chatbot",
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"},
        500: {"model": ErrorResponse, "description": "Chatbot error"}
    }
)
async def chat(
    request: ChatRequest,
    db: Session = Depends(get_db)
):
    """Ask questions about a specific report using the chatbot."""
    try:
        # Verify report exists
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == request.report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {request.report_id} not found"
            )
        
        # Get answer from chatbot
        response = answer_question(request.report_id, request.question)
        
        return ChatResponse(
            answer=response.get("answer", "No answer available"),
            sources=response.get("sources"),
            confidence=response.get("confidence")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chatbot error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Chatbot error: {str(e)}"
        )


# ============================================================================
# DELETE REPORT
# ============================================================================

@router.delete(
    "/report/{report_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete Report",
    description="Delete an analysis report and associated files",
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"}
    }
)
async def delete_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Delete an analysis report."""
    try:
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        # Delete PDF if exists
        if report.pdf_path and os.path.exists(report.pdf_path):
            try:
                os.remove(report.pdf_path)
            except Exception as e:
                logger.warning(f"Failed to delete PDF: {str(e)}")
        
        # Delete database record
        db.delete(report)
        db.commit()
        
        logger.info(f"Report {report_id} deleted successfully")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete report {report_id}: {str(e)}")
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete report: {str(e)}"
        )
