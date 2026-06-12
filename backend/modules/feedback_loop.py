"""
Analyst Feedback Loop — Enterprise-grade feedback collection and model improvement.

This module implements a closed-loop system where analyst decisions
(true positive / false positive / escalate / dismiss) are:
  1. Stored in MongoDB for audit and analytics
  2. Used to dynamically adjust ML fusion weights per category
  3. Exported as labeled training data for model retraining
  4. Used to compute precision/recall/F1 metrics per category

Collections:
  - analyst_feedback: Individual feedback records per finding
  - feedback_stats:   Aggregated precision/recall per category (refreshed periodically)

Feedback Impact:
  - True Positive (TP):  confirms detection → increases ML fusion weight for that category
  - False Positive (FP): incorrect detection → decreases ML fusion weight, adds to safe-phrase candidates
  - True Negative (TN):  correctly not flagged (implicit from safe reports)
  - False Negative (FN):  analyst escalates missed content → adds to regex training patterns

Calibration:
  After collecting 50+ feedback records per category, the system computes
  per-category precision and adjusts the fusion weight accordingly:
    - precision ≥ 0.9 → higher ML trust (fusion_weight = 0.45)
    - precision 0.7–0.9 → normal trust (fusion_weight = 0.30)
    - precision < 0.7 → reduced ML trust (fusion_weight = 0.15)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── Feedback Types ────────────────────────────────────────────────────────────

FEEDBACK_TYPES = {
    "true_positive":  "Analyst confirms this is a genuine grooming indicator",
    "false_positive": "Analyst determines this is a false detection",
    "escalate":       "Analyst escalates for further review / action",
    "dismiss":        "Analyst dismisses as non-concerning",
    "needs_context":  "Analyst requests additional context before deciding",
}

# ── Dynamic Calibration ───────────────────────────────────────────────────────

# Per-category fusion weight overrides based on feedback precision
_calibrated_weights: Dict[str, float] = {}
_calibration_loaded = False
MIN_SAMPLES_FOR_CALIBRATION = 30


def get_calibrated_fusion_weight(category: str, default_weight: float = 0.25) -> float:
    """
    Get the dynamically calibrated ML fusion weight for a category.

    If enough analyst feedback has been collected, the weight is adjusted
    based on the ML's historical accuracy for that category.
    """
    global _calibration_loaded
    if not _calibration_loaded:
        _load_calibration()
    return _calibrated_weights.get(category, default_weight)


def _load_calibration():
    """Load calibration weights from MongoDB feedback_stats."""
    global _calibrated_weights, _calibration_loaded
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is None:
            _calibration_loaded = True
            return

        stats = db["feedback_stats"].find_one({"_id": "category_calibration"})
        if stats and stats.get("weights"):
            _calibrated_weights = stats["weights"]
            logger.info(f"Loaded calibrated weights for {len(_calibrated_weights)} categories")
        _calibration_loaded = True
    except Exception as e:
        logger.warning(f"Failed to load calibration weights: {e}")
        _calibration_loaded = True


def refresh_calibration():
    """Recompute calibration weights from all analyst feedback."""
    global _calibrated_weights, _calibration_loaded
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is None:
            return

        # Aggregate feedback by category
        pipeline = [
            {"$group": {
                "_id": "$category",
                "total": {"$sum": 1},
                "true_positives": {
                    "$sum": {"$cond": [{"$eq": ["$feedback_type", "true_positive"]}, 1, 0]}
                },
                "false_positives": {
                    "$sum": {"$cond": [{"$eq": ["$feedback_type", "false_positive"]}, 1, 0]}
                },
                "escalations": {
                    "$sum": {"$cond": [{"$eq": ["$feedback_type", "escalate"]}, 1, 0]}
                },
                "dismissals": {
                    "$sum": {"$cond": [{"$eq": ["$feedback_type", "dismiss"]}, 1, 0]}
                },
            }},
        ]

        results = list(db["analyst_feedback"].aggregate(pipeline))

        weights = {}
        category_stats = {}

        for r in results:
            cat = r["_id"]
            total = r["total"]
            tp = r["true_positives"] + r["escalations"]  # escalation = confirmed risk
            fp = r["false_positives"] + r["dismissals"]  # dismissal = not concerning

            if total < MIN_SAMPLES_FOR_CALIBRATION:
                continue

            precision = tp / (tp + fp) if (tp + fp) > 0 else 0.5

            # Calibrate fusion weight based on precision
            if precision >= 0.90:
                weights[cat] = 0.45  # High trust in ML for this category
            elif precision >= 0.75:
                weights[cat] = 0.35  # Normal trust
            elif precision >= 0.60:
                weights[cat] = 0.25  # Reduced trust
            else:
                weights[cat] = 0.15  # Low trust — ML is unreliable here

            category_stats[cat] = {
                "total": total,
                "true_positives": tp,
                "false_positives": fp,
                "precision": round(precision, 4),
                "fusion_weight": weights[cat],
            }

        # Save to MongoDB
        db["feedback_stats"].update_one(
            {"_id": "category_calibration"},
            {"$set": {
                "weights": weights,
                "category_stats": category_stats,
                "updated_at": datetime.now(timezone.utc),
                "total_feedback": sum(r["total"] for r in results),
            }},
            upsert=True,
        )

        _calibrated_weights = weights
        _calibration_loaded = True
        logger.info(f"Calibration updated: {len(weights)} categories calibrated")
        return category_stats

    except Exception as e:
        logger.error(f"Failed to refresh calibration: {e}")
        return None


# ── Feedback Storage ──────────────────────────────────────────────────────────

def submit_feedback(
    report_id: int,
    finding_index: int,
    feedback_type: str,
    analyst_id: str,
    analyst_notes: Optional[str] = None,
    correct_category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Submit analyst feedback for a specific finding.

    Args:
        report_id:        Meeting/report ID
        finding_index:    Index of the finding in the report's findings list
        feedback_type:    One of FEEDBACK_TYPES keys
        analyst_id:       ID of the reviewing analyst
        analyst_notes:    Optional free-text notes
        correct_category: If FP, what the correct category should be (or 'safe')

    Returns:
        {"success": bool, "feedback_id": str, "message": str}
    """
    if feedback_type not in FEEDBACK_TYPES:
        return {"success": False, "message": f"Invalid feedback type. Must be one of: {list(FEEDBACK_TYPES.keys())}"}

    try:
        from database.mongo import get_mongo_db, get_analysis, audit_log
        db = get_mongo_db()
        if db is None:
            return {"success": False, "message": "Database unavailable"}

        # Get the original finding to store context
        analysis = get_analysis(report_id)
        if not analysis:
            return {"success": False, "message": f"Report #{report_id} not found"}

        findings = analysis.get("findings", [])
        if finding_index < 0 or finding_index >= len(findings):
            return {"success": False, "message": f"Finding index {finding_index} out of range (0-{len(findings)-1})"}

        finding = findings[finding_index]

        # Build feedback document
        feedback_doc = {
            "report_id":       report_id,
            "finding_index":   finding_index,
            "feedback_type":   feedback_type,
            "analyst_id":      analyst_id,
            "analyst_notes":   analyst_notes,
            "correct_category": correct_category,
            "created_at":      datetime.now(timezone.utc),

            # Snapshot of the finding at time of feedback
            "category":        finding.get("category") or (finding.get("categories", [None])[0]),
            "categories":      finding.get("categories", []),
            "confidence":      finding.get("confidence", 0),
            "evidence":        finding.get("evidence", ""),
            "severity":        finding.get("severity", "unknown"),
            "ml_label":        (finding.get("ml") or {}).get("top_label"),
            "ml_confidence":   (finding.get("ml") or {}).get("top_confidence"),
            "ml_agreement":    (finding.get("ml") or {}).get("agreement"),
            "context_type":    finding.get("context_type"),
        }

        result = db["analyst_feedback"].insert_one(feedback_doc)
        feedback_id = str(result.inserted_id)

        # Audit log
        audit_log(
            "analyst_feedback_submitted",
            meeting_id=report_id,
            details={
                "finding_index": finding_index,
                "feedback_type": feedback_type,
                "analyst_id": analyst_id,
                "category": feedback_doc["category"],
            },
        )

        logger.info(
            f"Feedback recorded: report=#{report_id}, finding={finding_index}, "
            f"type={feedback_type}, analyst={analyst_id}"
        )

        return {
            "success": True,
            "feedback_id": feedback_id,
            "message": f"Feedback '{feedback_type}' recorded for finding #{finding_index}",
        }

    except Exception as e:
        logger.error(f"Failed to submit feedback: {e}")
        return {"success": False, "message": f"Error: {str(e)}"}


def get_feedback_for_report(report_id: int) -> List[Dict[str, Any]]:
    """Get all analyst feedback for a specific report."""
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is None:
            return []

        cursor = db["analyst_feedback"].find(
            {"report_id": report_id},
            {"_id": 0},
        ).sort("created_at", -1)

        return list(cursor)
    except Exception as e:
        logger.warning(f"Failed to get feedback for report #{report_id}: {e}")
        return []


def get_feedback_stats() -> Dict[str, Any]:
    """Get aggregate feedback statistics across all reports."""
    try:
        from database.mongo import get_mongo_db
        db = get_mongo_db()
        if db is None:
            return {}

        total = db["analyst_feedback"].count_documents({})

        # By type
        type_pipeline = [
            {"$group": {"_id": "$feedback_type", "count": {"$sum": 1}}}
        ]
        type_results = list(db["analyst_feedback"].aggregate(type_pipeline))
        by_type = {r["_id"]: r["count"] for r in type_results}

        # By category
        cat_pipeline = [
            {"$group": {
                "_id": "$category",
                "total": {"$sum": 1},
                "true_positives": {
                    "$sum": {"$cond": [{"$in": ["$feedback_type", ["true_positive", "escalate"]]}, 1, 0]}
                },
                "false_positives": {
                    "$sum": {"$cond": [{"$in": ["$feedback_type", ["false_positive", "dismiss"]]}, 1, 0]}
                },
            }},
            {"$sort": {"total": -1}},
        ]
        cat_results = list(db["analyst_feedback"].aggregate(cat_pipeline))

        categories = {}
        for r in cat_results:
            cat = r["_id"]
            tp = r["true_positives"]
            fp = r["false_positives"]
            total_cat = r["total"]
            precision = tp / (tp + fp) if (tp + fp) > 0 else None
            categories[cat] = {
                "total": total_cat,
                "true_positives": tp,
                "false_positives": fp,
                "precision": round(precision, 4) if precision is not None else None,
            }

        # Overall precision
        total_tp = sum(c["true_positives"] for c in categories.values())
        total_fp = sum(c["false_positives"] for c in categories.values())
        overall_precision = total_tp / (total_tp + total_fp) if (total_tp + total_fp) > 0 else None

        # Load calibration stats
        cal_doc = db["feedback_stats"].find_one({"_id": "category_calibration"})
        calibration = cal_doc.get("category_stats", {}) if cal_doc else {}

        return {
            "total_feedback": total,
            "by_type": by_type,
            "by_category": categories,
            "overall_precision": round(overall_precision, 4) if overall_precision is not None else None,
            "overall_recall": None,  # requires ground-truth annotation
            "calibration": calibration,
            "calibrated_categories": len(_calibrated_weights),
        }

    except Exception as e:
        logger.error(f"Failed to get feedback stats: {e}")
        return {"error": str(e)}


# ── Training Data Export ──────────────────────────────────────────────────────

def export_training_data(
    min_confidence: float = 0.0,
    feedback_types: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    Export analyst-labeled data for model retraining.

    Returns NLI-format training samples derived from analyst feedback:
    - True positive → entailment (premise=evidence, hypothesis=category description)
    - False positive → contradiction (premise=evidence, hypothesis=category description)

    This data can be fed directly into finetune_model.py.
    """
    try:
        from database.mongo import get_mongo_db
        from modules.ml_classifier import HYPOTHESES, CATEGORY_KEYS
        db = get_mongo_db()
        if db is None:
            return []

        query = {}
        if feedback_types:
            query["feedback_type"] = {"$in": feedback_types}
        if min_confidence > 0:
            query["confidence"] = {"$gte": min_confidence}

        cursor = db["analyst_feedback"].find(query, {"_id": 0})
        feedback_records = list(cursor)

        # Build hypothesis lookup
        cat_to_hypothesis = dict(zip(CATEGORY_KEYS, HYPOTHESES))

        training_samples = []
        for record in feedback_records:
            evidence = record.get("evidence", "").strip()
            category = record.get("category", "")
            feedback_type = record.get("feedback_type", "")

            if not evidence or not category:
                continue

            hypothesis = cat_to_hypothesis.get(category)
            if not hypothesis:
                continue

            # Map feedback to NLI label
            if feedback_type in ("true_positive", "escalate"):
                # Analyst confirmed → this IS the category (entailment)
                training_samples.append({
                    "premise": evidence,
                    "hypothesis": hypothesis,
                    "label": 0,  # entailment
                    "source": "analyst_feedback",
                    "report_id": record.get("report_id"),
                    "analyst_id": record.get("analyst_id"),
                })
                # Also add contradiction with "safe" hypothesis
                training_samples.append({
                    "premise": evidence,
                    "hypothesis": "a safe or normal conversation",
                    "label": 2,  # contradiction
                    "source": "analyst_feedback",
                    "report_id": record.get("report_id"),
                })
            elif feedback_type in ("false_positive", "dismiss"):
                # Analyst rejected → this is NOT the category (contradiction)
                training_samples.append({
                    "premise": evidence,
                    "hypothesis": hypothesis,
                    "label": 2,  # contradiction
                    "source": "analyst_feedback",
                    "report_id": record.get("report_id"),
                    "analyst_id": record.get("analyst_id"),
                })
                # If analyst provided correct category, add entailment for that
                correct_cat = record.get("correct_category")
                if correct_cat and correct_cat != "safe":
                    correct_hyp = cat_to_hypothesis.get(correct_cat)
                    if correct_hyp:
                        training_samples.append({
                            "premise": evidence,
                            "hypothesis": correct_hyp,
                            "label": 0,  # entailment
                            "source": "analyst_correction",
                            "report_id": record.get("report_id"),
                        })
                elif correct_cat == "safe":
                    training_samples.append({
                        "premise": evidence,
                        "hypothesis": "a safe or normal conversation",
                        "label": 0,  # entailment
                        "source": "analyst_correction",
                        "report_id": record.get("report_id"),
                    })

        logger.info(f"Exported {len(training_samples)} training samples from {len(feedback_records)} feedback records")
        return training_samples

    except Exception as e:
        logger.error(f"Failed to export training data: {e}")
        return []
