import os
import logging
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import FileResponse

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

# Import MongoDB helpers
from database.mongo import (
    list_meetings, get_full_report, get_meeting,
    get_analysis, get_evidence as mongo_get_evidence,
    next_meeting_id, save_meeting_metadata,
)

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
        version="2.1.0",
        timestamp=datetime.now(timezone.utc).isoformat(),
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

    # Allocate a MongoDB meeting ID and create the initial record
    record_id = next_meeting_id()
    save_meeting_metadata(
        meeting_id=record_id,
        filename=original_filename,
        file_size_bytes=len(content),
        status="PROCESSING",
    )

    # Perform analysis
    try:
        result = await service.analyze_audio_file(
            filepath=filepath,
            filename=original_filename,
            record_id=record_id,
        )
        logger.info(f"Analysis completed successfully for: {original_filename}")
        # Invalidate all caches so the new report appears in /history immediately
        history_cache.invalidate()
        report_cache.invalidate()
        evidence_cache.invalidate()
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
    skip: int = 0,
    limit: int = 100,
    _user = Depends(get_current_user)
):
    """Get list of all analysis reports from MongoDB with caching."""
    try:
        cache_key = f"history_{skip}_{limit}"
        cached_result = history_cache.get(cache_key)
        if cached_result is not None:
            logger.debug("History cache hit")
            return cached_result

        data = list_meetings(skip=skip, limit=limit)

        items = [
            HistoryItem(
                id=r["id"],
                filename=r["filename"],
                severity=r.get("severity"),
                risk_score=r.get("risk_score"),
                created_at=r.get("created_at"),
                analyzed_at=r.get("created_at"),
            )
            for r in data.get("reports", [])
        ]

        result = HistoryResponse(reports=items, total=data.get("total", 0))
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
    _user = Depends(get_current_user)
):
    """Get detailed analysis report by ID from MongoDB with caching."""
    try:
        cache_key = f"report_{report_id}"
        cached_result = report_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Report cache hit for ID {report_id}")
            return cached_result

        report = get_full_report(report_id)
        if not report:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )

        result = ReportResponse(
            id=report["id"],
            filename=report["filename"],
            transcript=report.get("transcript"),
            findings=report.get("findings") or [],
            evidence=report.get("evidence") or [],
            stats=report.get("stats") or {},
            summary=report.get("summary"),
            llm_summary=report.get("llm_summary"),
            severity=report.get("severity"),
            risk_score=report.get("risk_score"),
            pdf_path=report.get("pdf_path"),
            created_at=report.get("created_at"),
        )

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
    _user = Depends(get_current_user)
):
    """Get evidence items for a specific report from MongoDB with caching."""
    try:
        cache_key = f"evidence_{report_id}"
        cached_result = evidence_cache.get(cache_key)
        if cached_result is not None:
            logger.debug(f"Evidence cache hit for report {report_id}")
            return cached_result

        meta = get_meeting(report_id)
        if not meta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )

        analysis = get_analysis(report_id) or {}
        ev = mongo_get_evidence(report_id)

        result = EvidenceResponse(
            report_id=report_id,
            severity=analysis.get("severity", ""),
            risk_score=analysis.get("risk_score", 0.0),
            evidence=ev,
        )

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
async def get_report_stats(report_id: int):
    """Get statistics for a specific report from MongoDB."""
    try:
        meta = get_meeting(report_id)
        if not meta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )

        analysis = get_analysis(report_id) or {}
        return {
            "categories":                analysis.get("category_breakdown", {}),
            "confidence_stats":          analysis.get("confidence_stats", {}),
            "severity_distribution":     analysis.get("severity_distribution", {}),
            "context_type_distribution": analysis.get("context_type_distribution", {}),
            "ml_stats":                  analysis.get("ml_stats", {}),
            "word_count":                analysis.get("word_count"),
            "finding_count":             analysis.get("finding_count", 0),
            "unique_categories":         analysis.get("unique_categories", 0),
        }

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
async def download_pdf(report_id: int):
    """Download PDF report — path resolved from MongoDB."""
    try:
        meta = get_meeting(report_id)
        if not meta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {report_id} not found"
            )

        pdf_path = meta.get("pdf_path") or f"reports/report_{report_id}.pdf"

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
async def chat(request: ChatRequest):
    """Ask questions about a specific report using the chatbot."""
    try:
        # Verify report exists in MongoDB
        meta = get_meeting(request.report_id)
        if not meta:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Report with ID {request.report_id} not found"
            )

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

# NOTE: DELETE /report/{report_id} is handled by app.py directly (no /api/v1 prefix).
# The Vite proxy strips /api/v1 before forwarding to the backend, so the route
# in app.py (@app.delete("/report/{report_id}")) is the one that handles all
# frontend delete requests. That route also invalidates the TTL cache and writes
# an audit log entry — do not add a duplicate here.
