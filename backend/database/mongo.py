"""
MongoDB client — 7-collection schema for AuraSafety.

Collections
-----------
1. meeting_metadata    — Meeting ID, title, date, duration, participants,
                         s3 recording url, status
2. transcripts         — Full transcript, speaker segments, timestamps, text
3. analysis_results    — Risk score, severity, summary, overall findings
4. safety_findings     — Detected categories, evidence, confidence scores, context
5. action_items        — Extracted action items, topics, keywords
6. processing_status   — Pipeline status, stage, started_at, completed_at, errors
7. audit_logs          — All events, user actions, system logs
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_client = None
_db     = None


# ── Connection ────────────────────────────────────────────────────────────────

def get_mongo_db():
    """Lazy singleton — returns None gracefully if MongoDB is unavailable."""
    global _client, _db
    if _db is not None:
        return _db
    try:
        from dotenv import load_dotenv
        load_dotenv(override=True)

        from pymongo import MongoClient, ASCENDING, DESCENDING
        from pymongo.server_api import ServerApi

        uri  = os.getenv("MONGO_URI", "")
        name = os.getenv("MONGO_DB_NAME", "audio_safety_db")

        if not uri:
            logger.warning("MONGO_URI not set — MongoDB disabled")
            return None

        _client = MongoClient(uri, server_api=ServerApi("1"),
                              serverSelectionTimeoutMS=5000)
        _client.admin.command("ping")
        _db = _client[name]

        # Ensure indexes on first connect
        _ensure_indexes(_db)
        logger.info(f"MongoDB connected -> {name}")
        return _db

    except Exception as e:
        logger.warning(f"MongoDB unavailable: {e}")
        return None


def _ensure_indexes(db) -> None:
    """Create indexes once on first connection."""
    from pymongo import ASCENDING, DESCENDING
    try:
        db["meeting_metadata"].create_index([("meeting_id", ASCENDING)], unique=True)
        db["transcripts"].create_index([("meeting_id", ASCENDING)])
        db["analysis_results"].create_index([("meeting_id", ASCENDING)])
        db["analysis_results"].create_index([("risk_score", DESCENDING)])
        db["safety_findings"].create_index([("meeting_id", ASCENDING)])
        db["safety_findings"].create_index([("category", ASCENDING)])
        db["action_items"].create_index([("meeting_id", ASCENDING)])
        db["processing_status"].create_index([("meeting_id", ASCENDING)], unique=True)
        db["audit_logs"].create_index([("meeting_id", ASCENDING)])
        db["audit_logs"].create_index([("timestamp", DESCENDING)])
    except Exception as e:
        logger.warning(f"MongoDB index creation warning: {e}")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_insert(collection_name: str, doc: dict) -> bool:
    """Insert a document, return True on success."""
    db = get_mongo_db()
    if db is None:
        return False
    try:
        db[collection_name].insert_one(doc)
        return True
    except Exception as e:
        logger.warning(f"MongoDB insert failed [{collection_name}]: {e}")
        return False


def _safe_upsert(collection_name: str, filter_: dict, doc: dict) -> bool:
    """Upsert a document, return True on success."""
    db = get_mongo_db()
    if db is None:
        return False
    try:
        db[collection_name].update_one(filter_, {"$set": doc}, upsert=True)
        return True
    except Exception as e:
        logger.warning(f"MongoDB upsert failed [{collection_name}]: {e}")
        return False


# ── 1. Meeting Metadata ───────────────────────────────────────────────────────

def save_meeting_metadata(
    meeting_id: int,
    filename: str,
    file_size_bytes: Optional[int] = None,
    duration_seconds: Optional[float] = None,
    participants: Optional[List[str]] = None,
    s3_url: Optional[str] = None,
    status: str = "PROCESSING",
) -> bool:
    """
    Collection: meeting_metadata
    Fields: meeting_id, title, date, duration, participants,
            s3_recording_url, status
    """
    doc = {
        "meeting_id":       meeting_id,
        "title":            filename,
        "date":             _now(),
        "duration_seconds": duration_seconds,
        "participants":     participants or [],
        "s3_recording_url": s3_url,
        "file_size_bytes":  file_size_bytes,
        "status":           status,
        "created_at":       _now(),
        "updated_at":       _now(),
    }
    return _safe_upsert("meeting_metadata", {"meeting_id": meeting_id}, doc)


def update_meeting_status(meeting_id: int, status: str) -> bool:
    db = get_mongo_db()
    if db is None:
        return False
    try:
        db["meeting_metadata"].update_one(
            {"meeting_id": meeting_id},
            {"$set": {"status": status, "updated_at": _now()}}
        )
        return True
    except Exception as e:
        logger.warning(f"MongoDB update_meeting_status failed: {e}")
        return False


# ── 2. Transcripts ────────────────────────────────────────────────────────────

def save_transcript(
    meeting_id: int,
    full_transcript: str,
    timeline: List[Dict[str, Any]],
) -> bool:
    """
    Collection: transcripts
    Fields: meeting_id, full_transcript, speaker_segments (timeline),
            timestamps, word_count
    """
    # Extract unique speakers from timeline
    speakers = list({seg.get("speaker") for seg in timeline
                     if seg.get("speaker")})

    # Build speaker_segments with timestamps
    speaker_segments = [
        {
            "start":   seg.get("start"),
            "end":     seg.get("end"),
            "text":    seg.get("text", ""),
            "speaker": seg.get("speaker"),
        }
        for seg in timeline
    ]

    doc = {
        "meeting_id":       meeting_id,
        "full_transcript":  full_transcript,
        "speaker_segments": speaker_segments,
        "speakers":         speakers,
        "word_count":       len(full_transcript.split()),
        "char_count":       len(full_transcript),
        "segment_count":    len(timeline),
        "created_at":       _now(),
    }
    return _safe_upsert("transcripts", {"meeting_id": meeting_id}, doc)


# ── 3. Analysis Results ───────────────────────────────────────────────────────

def save_analysis_results(
    meeting_id: int,
    risk_score: float,
    severity: str,
    llm_summary: str,
    rule_summary: str,
    stats: Dict[str, Any],
    finding_count: int,
    unique_categories: int,
) -> bool:
    """
    Collection: analysis_results
    Fields: meeting_id, risk_score, severity, summary,
            overall_findings (stats), analyzed_at
    """
    doc = {
        "meeting_id":        meeting_id,
        "risk_score":        risk_score,
        "severity":          severity,
        "llm_summary":       llm_summary,
        "rule_summary":      rule_summary,
        "finding_count":     finding_count,
        "unique_categories": unique_categories,
        "category_breakdown": stats.get("categories", {}),
        "confidence_stats":  stats.get("confidence_stats", {}),
        "severity_distribution": stats.get("severity_distribution", {}),
        "context_type_distribution": stats.get("context_type_distribution", {}),
        "ml_stats":          stats.get("ml_stats", {}),
        "word_count":        stats.get("word_count"),
        "analyzed_at":       _now(),
    }
    return _safe_upsert("analysis_results", {"meeting_id": meeting_id}, doc)


# ── 4. Safety Findings ────────────────────────────────────────────────────────

def save_safety_findings(
    meeting_id: int,
    findings: List[Dict[str, Any]],
) -> bool:
    """
    Collection: safety_findings
    Fields: meeting_id, category, evidence, confidence,
            context_type, severity, speaker, timestamp
    """
    db = get_mongo_db()
    if db is None:
        return False

    if not findings:
        return True

    try:
        # Delete old findings for this meeting before re-inserting
        db["safety_findings"].delete_many({"meeting_id": meeting_id})

        docs = []
        for f in findings:
            cats = f.get("categories") or ([f["category"]] if f.get("category") else [])
            docs.append({
                "meeting_id":   meeting_id,
                "categories":   cats,
                "category":     cats[0] if cats else "unknown",
                "evidence":     f.get("evidence") or f.get("text", ""),
                "confidence":   f.get("confidence") or f.get("max_confidence") or 0,
                "context_type": f.get("context_type") or
                                (f.get("context", {}) or {}).get("primary", "NEUTRAL"),
                "severity":     f.get("severity", "unknown"),
                "speaker":      f.get("speaker"),
                "timestamp":    f.get("timestamp"),
                "matched_text": f.get("matched_text"),
                "is_negated":   (f.get("filters") or {}).get("is_negated", False),
                "is_joke":      (f.get("filters") or {}).get("is_joke", False),
                "ml_label":     (f.get("ml") or {}).get("top_label"),
                "ml_confidence":(f.get("ml") or {}).get("top_confidence"),
                "ml_agreement": (f.get("ml") or {}).get("agreement"),
                "created_at":   _now(),
            })

        if docs:
            db["safety_findings"].insert_many(docs)
        logger.info(f"MongoDB: {len(docs)} safety findings saved for meeting #{meeting_id}")
        return True

    except Exception as e:
        logger.warning(f"MongoDB save_safety_findings failed: {e}")
        return False


# ── 5. Action Items & Topics ──────────────────────────────────────────────────

def save_action_items(
    meeting_id: int,
    findings: List[Dict[str, Any]],
    stats: Dict[str, Any],
) -> bool:
    """
    Collection: action_items
    Fields: meeting_id, action_items (critical findings requiring action),
            topics (detected categories), keywords
    """
    # Action items = critical/high severity findings
    action_items = [
        {
            "category": (f.get("categories") or [f.get("category", "")])[0],
            "evidence":  f.get("evidence") or f.get("text", ""),
            "confidence": f.get("confidence") or f.get("max_confidence") or 0,
            "severity":  f.get("severity", "unknown"),
            "speaker":   f.get("speaker"),
            "priority":  "HIGH" if f.get("severity") in ("critical", "high") else "MEDIUM",
        }
        for f in findings
        if f.get("severity") in ("critical", "high")
    ]

    # Topics = unique detected categories
    topics = list(stats.get("categories", {}).keys())

    # Keywords = matched_text snippets (deduplicated)
    keywords = list({
        f.get("matched_text")
        for f in findings
        if f.get("matched_text")
    })

    doc = {
        "meeting_id":   meeting_id,
        "action_items": action_items,
        "topics":       topics,
        "keywords":     keywords,
        "action_count": len(action_items),
        "created_at":   _now(),
    }
    return _safe_upsert("action_items", {"meeting_id": meeting_id}, doc)


# ── 6. Processing Status ──────────────────────────────────────────────────────

def save_processing_status(
    meeting_id: int,
    status: str,
    stage: str,
    started_at: Optional[datetime] = None,
    completed_at: Optional[datetime] = None,
    error: Optional[str] = None,
) -> bool:
    """
    Collection: processing_status
    Fields: meeting_id, status, stage, started_at, completed_at, errors
    """
    doc = {
        "meeting_id":    meeting_id,
        "status":        status,
        "stage":         stage,
        "started_at":    started_at or _now(),
        "completed_at":  completed_at,
        "error":         error,
        "updated_at":    _now(),
    }
    return _safe_upsert("processing_status", {"meeting_id": meeting_id}, doc)


# ── 7. Audit Logs ─────────────────────────────────────────────────────────────

def audit_log(
    event: str,
    meeting_id: Optional[int] = None,
    user_action: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
) -> bool:
    """
    Collection: audit_logs
    Fields: event, meeting_id, user_action, details, timestamp
    """
    doc = {
        "event":       event,
        "meeting_id":  meeting_id,
        "user_action": user_action,
        "details":     details or {},
        "timestamp":   _now(),
    }
    return _safe_insert("audit_logs", doc)


# ── Convenience: save all 7 at once ──────────────────────────────────────────

def save_full_analysis(
    meeting_id: int,
    filename: str,
    transcript: str,
    timeline: List[Dict[str, Any]],
    findings: List[Dict[str, Any]],
    risk_score: float,
    severity: str,
    llm_summary: str,
    rule_summary: str,
    stats: Dict[str, Any],
    started_at: Optional[datetime] = None,
    s3_url: Optional[str] = None,
) -> Dict[str, bool]:
    """
    Write all 7 collections in one call.
    Returns a dict of {collection: success} for observability.
    """
    now = _now()
    results = {}

    results["meeting_metadata"] = save_meeting_metadata(
        meeting_id=meeting_id,
        filename=filename,
        duration_seconds=timeline[-1]["end"] if timeline else None,
        participants=list({s.get("speaker") for s in timeline if s.get("speaker")}),
        s3_url=s3_url,
        status="COMPLETED",
    )

    results["transcripts"] = save_transcript(
        meeting_id=meeting_id,
        full_transcript=transcript,
        timeline=timeline,
    )

    results["analysis_results"] = save_analysis_results(
        meeting_id=meeting_id,
        risk_score=risk_score,
        severity=severity,
        llm_summary=llm_summary,
        rule_summary=rule_summary,
        stats=stats,
        finding_count=len(findings),
        unique_categories=stats.get("unique_categories", 0),
    )

    results["safety_findings"] = save_safety_findings(
        meeting_id=meeting_id,
        findings=findings,
    )

    results["action_items"] = save_action_items(
        meeting_id=meeting_id,
        findings=findings,
        stats=stats,
    )

    results["processing_status"] = save_processing_status(
        meeting_id=meeting_id,
        status="COMPLETED",
        stage="done",
        started_at=started_at,
        completed_at=now,
    )

    results["audit_logs"] = audit_log(
        event="analysis_completed",
        meeting_id=meeting_id,
        details={
            "severity":    severity,
            "risk_score":  risk_score,
            "findings":    len(findings),
        },
    )

    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.warning(f"MongoDB: some collections failed for #{meeting_id}: {failed}")
    else:
        logger.info(f"MongoDB: all 7 collections saved for meeting #{meeting_id}")

    return results


# ── Alert Logging ─────────────────────────────────────────────────────────────

def log_alert(
    meeting_id: int,
    filename: str,
    severity: str,
    risk_score: float,
    recipients: List[str],
    email_type: str = "alert",
) -> bool:
    """
    Collection: audit_logs
    Log an email alert/summary that was sent for a meeting.
    """
    return audit_log(
        event=f"email_{email_type}_sent",
        meeting_id=meeting_id,
        details={
            "filename":   filename,
            "severity":   severity,
            "risk_score": risk_score,
            "recipients": recipients,
            "email_type": email_type,
        },
    )


# ── Health ────────────────────────────────────────────────────────────────────

def ping() -> bool:
    return get_mongo_db() is not None
