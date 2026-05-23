"""
FastAPI routes for Audio Safety Analysis.

This module defines all API endpoints with proper error handling,
logging, validation, and documentation.
"""

import os
import json
import shutil
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
    return HealthResponse(
        status="healthy",
        service="Audio Safety Analyzer",
        version="2.0.0",
        timestamp=datetime.now().isoformat()
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
    
    Pipeline:
    1. Transcription
    2. Grooming Detection
    3. Risk Scoring
    4. Severity Classification
    5. Summary Generation
    6. PDF Report Generation
    7. Database Persistence
    
    Supported formats: .mp3, .wav, .m4a, .ogg, .flac
    """
    logger.info(f"Received analysis request for file: {file.filename}")
    
    # Validate file extension
    extension = os.path.splitext(file.filename)[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        logger.warning(f"Unsupported file format: {extension}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported audio format: {extension}. Supported: {', '.join(ALLOWED_EXTENSIONS)}"
        )
    
    # Save uploaded file
    try:
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
        filepath = os.path.join(UPLOAD_FOLDER, file.filename)
        
        with open(filepath, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
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
            filename=file.filename,
            db_session=db
        )
        
        logger.info(f"Analysis completed successfully for: {file.filename}")
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
    description="Retrieve list of all analysis reports"
)
async def get_history(
    db: Session = Depends(get_db),
    skip: int = 0,
    limit: int = 100
):
    """Get list of all analysis reports."""
    try:
        reports = db.query(AudioAnalysis).offset(skip).limit(limit).all()
        total = db.query(AudioAnalysis).count()
        
        items = [
            HistoryItem(
                id=report.id,
                filename=report.filename,
                severity=report.severity,
                risk_score=report.risk_score
            )
            for report in reports
        ]
        
        return HistoryResponse(reports=items, total=total)
        
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
    description="Retrieve detailed analysis report by ID",
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"}
    }
)
async def get_report(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Get detailed analysis report by ID."""
    try:
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        return ReportResponse(
            id=report.id,
            filename=report.filename,
            transcript=report.transcript,
            findings=json.loads(report.findings) if report.findings else [],
            evidence=json.loads(report.evidence) if report.evidence else [],
            stats=json.loads(report.stats) if report.stats else {},
            summary=report.summary,
            llm_summary=report.llm_summary,
            severity=report.severity,
            risk_score=report.risk_score,
            pdf_path=report.pdf_path
        )
        
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
    description="Retrieve evidence items for a specific report",
    responses={
        404: {"model": ErrorResponse, "description": "Report not found"}
    }
)
async def get_evidence(
    report_id: int,
    db: Session = Depends(get_db)
):
    """Get evidence items for a specific report."""
    try:
        report = db.query(AudioAnalysis).filter(
            AudioAnalysis.id == report_id
        ).first()
        
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )
        
        return EvidenceResponse(
            report_id=report_id,
            severity=report.severity,
            risk_score=report.risk_score,
            evidence=json.loads(report.evidence) if report.evidence else []
        )
        
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
        
        return json.loads(report.stats) if report.stats else {}
        
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
