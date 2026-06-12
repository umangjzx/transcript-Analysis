"""
Feedback Routes — Analyst feedback loop for model improvement.

Prefix: /api/v1

Endpoints:
  POST   /feedback                    → submit feedback for a finding
  GET    /feedback/report/{id}        → get all feedback for a report
  GET    /feedback/stats              → aggregate feedback statistics
  POST   /feedback/calibrate          → trigger weight recalibration
  GET    /feedback/export-training    → export labeled data for retraining
"""

import json
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from auth import get_current_user
from modules.feedback_loop import (
    submit_feedback,
    get_feedback_for_report,
    get_feedback_stats,
    refresh_calibration,
    export_training_data,
    FEEDBACK_TYPES,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Feedback"],
)


# ── Request Models ────────────────────────────────────────────────────────────

class FeedbackRequest(BaseModel):
    report_id: int
    finding_index: int
    feedback_type: str
    notes: Optional[str] = None
    correct_category: Optional[str] = None

    @field_validator("feedback_type")
    @classmethod
    def validate_feedback_type(cls, v):
        if v not in FEEDBACK_TYPES:
            raise ValueError(f"feedback_type must be one of: {list(FEEDBACK_TYPES.keys())}")
        return v


class BulkFeedbackRequest(BaseModel):
    report_id: int
    feedback_type: str
    finding_indices: List[int]
    notes: Optional[str] = None

    @field_validator("feedback_type")
    @classmethod
    def validate_feedback_type(cls, v):
        if v not in FEEDBACK_TYPES:
            raise ValueError(f"feedback_type must be one of: {list(FEEDBACK_TYPES.keys())}")
        return v


# ── POST /feedback ────────────────────────────────────────────────────────────

@router.post("/feedback")
def post_feedback(
    req: FeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Submit analyst feedback for a specific finding in a report.

    Feedback types:
      - true_positive: Confirms genuine grooming indicator
      - false_positive: Incorrect detection (not actually concerning)
      - escalate: Needs further review / action
      - dismiss: Not concerning in context
      - needs_context: Requires additional information

    Optionally provide `correct_category` when marking a false positive
    to indicate what the sentence actually represents (e.g., 'safe').
    """
    analyst_id = current_user.get("username") or current_user.get("sub", "unknown")

    result = submit_feedback(
        report_id=req.report_id,
        finding_index=req.finding_index,
        feedback_type=req.feedback_type,
        analyst_id=analyst_id,
        analyst_notes=req.notes,
        correct_category=req.correct_category,
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])

    return result


# ── POST /feedback/bulk ───────────────────────────────────────────────────────

@router.post("/feedback/bulk")
def post_bulk_feedback(
    req: BulkFeedbackRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Submit the same feedback type for multiple findings at once.
    Useful for marking all findings in a safe report as false_positive.
    """
    analyst_id = current_user.get("username") or current_user.get("sub", "unknown")

    results = []
    for idx in req.finding_indices:
        result = submit_feedback(
            report_id=req.report_id,
            finding_index=idx,
            feedback_type=req.feedback_type,
            analyst_id=analyst_id,
            analyst_notes=req.notes,
        )
        results.append({"finding_index": idx, **result})

    succeeded = sum(1 for r in results if r["success"])
    return {
        "total": len(req.finding_indices),
        "succeeded": succeeded,
        "failed": len(req.finding_indices) - succeeded,
        "results": results,
    }


# ── GET /feedback/report/{id} ────────────────────────────────────────────────

@router.get("/feedback/report/{report_id}")
def get_report_feedback(
    report_id: int,
    current_user: dict = Depends(get_current_user),
):
    """Get all analyst feedback submitted for a specific report."""
    feedback = get_feedback_for_report(report_id)
    return {
        "report_id": report_id,
        "total": len(feedback),
        "feedback": feedback,
    }


# ── GET /feedback/stats ───────────────────────────────────────────────────────

@router.get("/feedback/stats")
def get_stats(current_user: dict = Depends(get_current_user)):
    """
    Get aggregate feedback statistics including:
    - Total feedback count
    - Breakdown by type (true_positive, false_positive, etc.)
    - Per-category precision metrics
    - Overall system precision
    - Current calibration state
    """
    return get_feedback_stats()


# ── POST /feedback/calibrate ─────────────────────────────────────────────────

@router.post("/feedback/calibrate")
def trigger_calibration(current_user: dict = Depends(get_current_user)):
    """
    Trigger recalibration of ML fusion weights based on accumulated feedback.

    Requires at least 30 feedback records per category to calibrate.
    Categories with fewer records keep their default weights.

    This adjusts how much the system trusts the ML classifier per category:
    - High precision (≥90%) → increased ML trust (weight 0.45)
    - Normal precision (75-90%) → standard trust (weight 0.35)
    - Low precision (60-75%) → reduced trust (weight 0.25)
    - Poor precision (<60%) → minimal trust (weight 0.15)
    """
    result = refresh_calibration()
    if result is None:
        raise HTTPException(status_code=500, detail="Calibration failed")

    return {
        "message": "Calibration complete",
        "calibrated_categories": len(result),
        "details": result,
    }


# ── GET /feedback/export-training ─────────────────────────────────────────────

@router.get("/feedback/export-training")
def export_training(
    min_confidence: float = 0.0,
    current_user: dict = Depends(get_current_user),
):
    """
    Export analyst-labeled data as NLI training samples.

    Returns data in the same format as the fine-tuning dataset:
    [{"premise": str, "hypothesis": str, "label": 0|1|2}, ...]

    This data can be appended to backend/data/grooming_nli_dataset.json
    and used to retrain the model with:
        python finetune_model.py --dataset data/combined_dataset.json
    """
    samples = export_training_data(min_confidence=min_confidence)
    return {
        "total_samples": len(samples),
        "samples": samples,
        "usage": "Append to data/grooming_nli_dataset.json and run: python finetune_model.py",
    }


# ── GET /feedback/types ───────────────────────────────────────────────────────

@router.get("/feedback/types")
def get_feedback_types():
    """List available feedback types and their descriptions."""
    return {"types": FEEDBACK_TYPES}
