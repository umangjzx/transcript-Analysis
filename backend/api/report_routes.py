"""
Report Routes (unversioned)
===========================
Prefix: none (root-level)

Endpoints:
  GET    /report/{id}/status   → poll processing status
  GET    /history              → paginated history (cached)
  GET    /report/{id}          → full report
  GET    /report/{id}/evidence → evidence list
  GET    /report/{id}/stats    → statistics
  GET    /report/{id}/pdf      → download PDF
  DELETE /report/{id}          → delete report + all associated data
"""

import os
import json
import logging
from typing import Dict, Any

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from fastapi.responses import FileResponse, Response

from auth import get_current_user
from database.mongo import (
    list_meetings, get_full_report, get_meeting,
    get_evidence as mongo_get_evidence,
    delete_meeting_data, audit_log,
)
from modules.cache import TTLCache, history_cache, report_cache, evidence_cache
from modules.chatbot import delete_transcript
from modules.s3_storage import delete_file as s3_delete_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reports"])

# Local TTL cache for unversioned routes
_cache = TTLCache(ttl=60, name="report_routes")


# ── GET /report/{id}/status ───────────────────────────────────────────────────

@router.get("/report/{report_id}/status")
def get_report_status(report_id: int):
    from database.mongo import get_processing_status
    ps = get_processing_status(report_id)
    meta = get_meeting(report_id)
    if ps is None and meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    status_val = (ps or {}).get("status") or (meta or {}).get("status", "UNKNOWN")
    error_msg = (ps or {}).get("error")
    return {"id": report_id, "status": status_val, "error_message": error_msg}


# ── GET /history ──────────────────────────────────────────────────────────────

@router.get("/history")
def get_history(
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user),
):
    """Paginated history with TTL cache — reads from MongoDB."""
    if limit > 500:
        limit = 500
    cache_key = f"history:{skip}:{limit}"
    cached = _cache.get(cache_key)
    if cached is not None:
        return cached

    result = list_meetings(skip=skip, limit=limit)
    result["skip"] = skip
    result["limit"] = limit
    _cache.set(cache_key, result)
    return result


# ── GET /report/{id} ──────────────────────────────────────────────────────────

@router.get("/report/{report_id}")
def get_report(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    report = get_full_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


# ── GET /report/{id}/evidence ─────────────────────────────────────────────────

@router.get("/report/{report_id}/evidence")
def get_evidence(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    from database.mongo import get_analysis
    analysis = get_analysis(report_id) or {}
    ev = mongo_get_evidence(report_id)
    return {
        "report_id": report_id,
        "severity": analysis.get("severity", ""),
        "risk_score": analysis.get("risk_score", 0),
        "evidence": ev,
    }


# ── GET /report/{id}/stats ───────────────────────────────────────────────────

@router.get("/report/{report_id}/stats")
def get_report_stats(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    from database.mongo import get_analysis
    analysis = get_analysis(report_id) or {}
    return {
        "categories": analysis.get("category_breakdown", {}),
        "confidence_stats": analysis.get("confidence_stats", {}),
        "severity_distribution": analysis.get("severity_distribution", {}),
        "context_type_distribution": analysis.get("context_type_distribution", {}),
        "ml_stats": analysis.get("ml_stats", {}),
        "word_count": analysis.get("word_count"),
        "finding_count": analysis.get("finding_count", 0),
        "unique_categories": analysis.get("unique_categories", 0),
    }


# ── GET /report/{id}/pdf ─────────────────────────────────────────────────────

@router.get("/report/{report_id}/pdf")
def download_pdf(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")
    pdf_path = meta.get("pdf_path") or f"reports/report_{report_id}.pdf"
    if not os.path.exists(pdf_path):
        raise HTTPException(status_code=404, detail="PDF report not found")
    return FileResponse(path=pdf_path, media_type="application/pdf",
                        filename=f"report_{report_id}.pdf")


# ── DELETE /report/{id} ───────────────────────────────────────────────────────

@router.delete("/report/{report_id}", status_code=204, response_class=Response)
def delete_report(
    report_id: int,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """Delete a report — returns 204 instantly, cleanup runs in background."""
    meta = get_meeting(report_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_path = meta.get("pdf_path")
    s3_audio_url = meta.get("s3_recording_url")
    s3_pdf_url = meta.get("s3_pdf_url")

    # Invalidate caches immediately
    _cache.invalidate()
    history_cache.invalidate()
    report_cache.invalidate()
    evidence_cache.invalidate()

    try:
        audit_log("report_deleted", meeting_id=report_id, details={"report_id": report_id})
    except Exception as _e:
        logger.warning(f"[#{report_id}] Audit log failed (non-fatal): {_e}")

    background_tasks.add_task(_bg_delete_report, report_id, pdf_path, s3_audio_url, s3_pdf_url)
    return Response(status_code=204)


def _bg_delete_report(
    report_id: int,
    pdf_path: str | None,
    s3_audio_url: str | None,
    s3_pdf_url: str | None,
) -> None:
    """Background cleanup — runs after 204 is already sent."""
    if pdf_path and os.path.exists(pdf_path):
        try:
            os.remove(pdf_path)
            logger.info(f"[#{report_id}] Local PDF deleted")
        except Exception as _e:
            logger.warning(f"[#{report_id}] Could not delete local PDF: {_e}")

    if s3_audio_url:
        try:
            s3_delete_file(s3_audio_url)
            logger.info(f"[#{report_id}] S3 audio deleted")
        except Exception as _e:
            logger.warning(f"[#{report_id}] S3 audio delete failed: {_e}")

    if s3_pdf_url:
        try:
            s3_delete_file(s3_pdf_url)
            logger.info(f"[#{report_id}] S3 PDF deleted")
        except Exception as _e:
            logger.warning(f"[#{report_id}] S3 PDF delete failed: {_e}")

    try:
        delete_transcript(report_id)
    except Exception as _e:
        logger.warning(f"[#{report_id}] ChromaDB cleanup failed: {_e}")

    try:
        delete_meeting_data(report_id)
        logger.info(f"[#{report_id}] MongoDB records deleted")
    except Exception as _e:
        logger.warning(f"[#{report_id}] MongoDB cleanup failed: {_e}")

    logger.info(f"[#{report_id}] Background cleanup complete")
