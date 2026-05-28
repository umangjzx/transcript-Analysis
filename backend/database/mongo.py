"""
MongoDB client — 7-collection schema for Melody Wings Safety.

Collections
-----------
1. meeting_metadata    — Meeting ID, title, date, duration, participants,
                         s3 recording url, status, pdf_path, s3_pdf_url
2. transcripts         — Full transcript, speaker segments, timestamps, text
3. analysis_results    — Risk score, severity, summary, overall findings
4. safety_findings     — Detected categories, evidence, confidence scores, context
5. action_items        — Extracted action items, topics, keywords
6. processing_status   — Pipeline status, stage, started_at, completed_at, errors
7. audit_logs          — All events, user actions, system logs

Read helpers (for SQLite-free operation)
-----------------------------------------
list_meetings()          — paginated history list
get_meeting()            — single meeting metadata
get_transcript()         — transcript + timeline for a meeting
get_analysis()           — full analysis result for a meeting
get_findings()           — safety findings list for a meeting
get_evidence()           — evidence list for a meeting
get_analytics_summary()  — aggregate analytics across all meetings
update_s3_urls()         — store s3_audio_url / s3_pdf_url after upload
update_pdf_path()        — store local pdf_path after generation
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
    """Lazy singleton — returns None gracefully if MongoDB is unavailable.

    Connection pooling is configured via environment variables:
    - MONGO_POOL_MIN_SIZE: Minimum connections in pool (default: 5)
    - MONGO_POOL_MAX_SIZE: Maximum connections in pool (default: 50)
    - MONGO_MAX_IDLE_TIME_MS: Max idle time before connection is closed (default: 30000)
    - MONGO_WAIT_QUEUE_TIMEOUT_MS: Max wait for a connection from pool (default: 5000)
    """
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

        # Connection pool configuration
        pool_min = int(os.getenv("MONGO_POOL_MIN_SIZE", "5"))
        pool_max = int(os.getenv("MONGO_POOL_MAX_SIZE", "50"))
        max_idle_ms = int(os.getenv("MONGO_MAX_IDLE_TIME_MS", "30000"))
        wait_queue_ms = int(os.getenv("MONGO_WAIT_QUEUE_TIMEOUT_MS", "5000"))

        _client = MongoClient(
            uri,
            server_api=ServerApi("1"),
            serverSelectionTimeoutMS=5000,
            # Connection pooling
            minPoolSize=pool_min,
            maxPoolSize=pool_max,
            maxIdleTimeMS=max_idle_ms,
            waitQueueTimeoutMS=wait_queue_ms,
            # Connection resilience
            retryWrites=True,
            retryReads=True,
            connectTimeoutMS=10000,
            socketTimeoutMS=30000,
        )
        _client.admin.command("ping")
        _db = _client[name]

        # Ensure indexes on first connect
        _ensure_indexes(_db)
        logger.info(
            f"MongoDB connected -> {name} "
            f"(pool: {pool_min}-{pool_max}, idle: {max_idle_ms}ms)"
        )
        return _db

    except Exception as e:
        logger.warning(f"MongoDB unavailable: {e}")
        return None


def _ensure_indexes(db) -> None:
    """Create indexes once on first connection (idempotent)."""
    from pymongo import ASCENDING, DESCENDING
    from pymongo.errors import OperationFailure

    def _safe_create_index(collection_name, keys, **kwargs):
        """Create an index, skipping gracefully if it already exists with different options."""
        try:
            db[collection_name].create_index(keys, **kwargs)
        except OperationFailure as e:
            # Code 86 = IndexKeySpecsConflict — index already exists with same name
            # Code 85 = IndexOptionsConflict — index exists with different options
            if e.code in (85, 86):
                logger.debug(
                    f"Index already exists on {collection_name} "
                    f"(keys={keys}, kwargs={kwargs}), skipping."
                )
            else:
                raise

    try:
        _safe_create_index("meeting_metadata", [("meeting_id", ASCENDING)], unique=True)
        _safe_create_index("transcripts", [("meeting_id", ASCENDING)])
        _safe_create_index("analysis_results", [("meeting_id", ASCENDING)])
        _safe_create_index("analysis_results", [("risk_score", DESCENDING)])
        _safe_create_index("safety_findings", [("meeting_id", ASCENDING)])
        _safe_create_index("safety_findings", [("category", ASCENDING)])
        _safe_create_index("action_items", [("meeting_id", ASCENDING)])
        _safe_create_index("processing_status", [("meeting_id", ASCENDING)], unique=True)
        _safe_create_index("audit_logs", [("meeting_id", ASCENDING)])
        _safe_create_index("audit_logs", [("timestamp", DESCENDING)])
        # users — unique username index for fast login lookups
        _safe_create_index("users", [("username", ASCENDING)], unique=True)
        # counters collection — no extra index needed (_id is already indexed)

        # TTL indexes — auto-expire old documents
        # Audit logs: expire after 90 days (configurable via AUDIT_LOG_TTL_DAYS)
        audit_ttl_days = int(os.getenv("AUDIT_LOG_TTL_DAYS", "90"))
        _safe_create_index(
            "audit_logs",
            [("timestamp", ASCENDING)],
            expireAfterSeconds=audit_ttl_days * 86400,
            name="ttl_audit_logs_timestamp",
        )
        # Processing status: expire completed/failed records after 30 days
        processing_ttl_days = int(os.getenv("PROCESSING_STATUS_TTL_DAYS", "30"))
        _safe_create_index(
            "processing_status",
            [("updated_at", ASCENDING)],
            expireAfterSeconds=processing_ttl_days * 86400,
            name="ttl_processing_status_updated_at",
        )
        # Dead letter queue — index for status-based queries and replay
        _safe_create_index("dead_letter_queue", [("status", ASCENDING)])
        _safe_create_index("dead_letter_queue", [("failed_at", DESCENDING)])
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
    pdf_path: Optional[str] = None,
    s3_pdf_url: Optional[str] = None,
) -> bool:
    """
    Collection: meeting_metadata
    Fields: meeting_id, title, date, duration, participants,
            s3_recording_url, s3_pdf_url, pdf_path, status
    """
    doc = {
        "meeting_id":       meeting_id,
        "title":            filename,
        "date":             _now(),
        "duration_seconds": duration_seconds,
        "participants":     participants or [],
        "s3_recording_url": s3_url,
        "s3_pdf_url":       s3_pdf_url,
        "pdf_path":         pdf_path,
        "file_size_bytes":  file_size_bytes,
        "status":           status,
        "created_at":       _now(),
        "updated_at":       _now(),
    }
    return _safe_upsert("meeting_metadata", {"meeting_id": meeting_id}, doc)


def next_meeting_id() -> int:
    """
    Atomic auto-increment counter stored in MongoDB.
    Uses the 'counters' collection with findOneAndUpdate + upsert.
    Returns the next integer ID (starts at 1).
    """
    from pymongo import ReturnDocument
    db = get_mongo_db()
    if db is None:
        raise RuntimeError("MongoDB unavailable — cannot generate meeting ID")
    try:
        result = db["counters"].find_one_and_update(
            {"_id": "meeting_id"},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return result["seq"]
    except Exception as e:
        logger.error(f"MongoDB next_meeting_id failed: {e}")
        raise


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
    Fields: meeting_id, full_transcript, segments (timeline),
            timestamps, word_count
    """
    # Store raw segments (no speaker diarization in this system)
    segments = [
        {
            "start":   seg.get("start"),
            "end":     seg.get("end"),
            "text":    seg.get("text", ""),
        }
        for seg in timeline
    ]

    doc = {
        "meeting_id":       meeting_id,
        "full_transcript":  full_transcript,
        "segments":         segments,
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
    evidence: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """
    Collection: analysis_results
    Fields: meeting_id, risk_score, severity, summary,
            overall_findings (stats), evidence, analyzed_at
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
        "evidence":          evidence or [],
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
    evidence: Optional[List[Dict[str, Any]]] = None,
    pdf_path: Optional[str] = None,
    s3_pdf_url: Optional[str] = None,
) -> Dict[str, bool]:
    """
    Write all 7 collections in one call using a MongoDB transaction.
    If any write fails, the entire operation is rolled back.
    Returns a dict of {collection: success} for observability.
    """
    now = _now()
    db = get_mongo_db()
    if db is None:
        return {col: False for col in [
            "meeting_metadata", "transcripts", "analysis_results",
            "safety_findings", "action_items", "processing_status", "audit_logs"
        ]}

    # Attempt transactional write (requires replica set)
    try:
        with _client.start_session() as session:
            with session.start_transaction():
                _save_full_analysis_in_session(
                    db, session, meeting_id, filename, transcript, timeline,
                    findings, risk_score, severity, llm_summary, rule_summary,
                    stats, started_at, now, s3_url, evidence, pdf_path, s3_pdf_url,
                )
        logger.info(f"MongoDB: all 7 collections saved (transactional) for meeting #{meeting_id}")
        return {col: True for col in [
            "meeting_metadata", "transcripts", "analysis_results",
            "safety_findings", "action_items", "processing_status", "audit_logs"
        ]}
    except Exception as tx_err:
        # Transaction not supported (standalone MongoDB) — fall back to non-transactional
        logger.warning(
            f"MongoDB transaction failed (falling back to non-transactional): {tx_err}"
        )
        return _save_full_analysis_no_transaction(
            meeting_id, filename, transcript, timeline, findings, risk_score,
            severity, llm_summary, rule_summary, stats, started_at, now,
            s3_url, evidence, pdf_path, s3_pdf_url,
        )


def _save_full_analysis_in_session(
    db, session, meeting_id, filename, transcript, timeline,
    findings, risk_score, severity, llm_summary, rule_summary,
    stats, started_at, now, s3_url, evidence, pdf_path, s3_pdf_url,
):
    """Execute all 7 collection writes within a MongoDB session/transaction."""
    # 1. meeting_metadata
    meta_doc = {
        "meeting_id": meeting_id,
        "title": filename,
        "date": now,
        "duration_seconds": timeline[-1]["end"] if timeline else None,
        "participants": list({s.get("speaker") for s in timeline if s.get("speaker")}),
        "s3_recording_url": s3_url,
        "s3_pdf_url": s3_pdf_url,
        "pdf_path": pdf_path,
        "file_size_bytes": None,
        "status": "COMPLETED",
        "created_at": now,
        "updated_at": now,
    }
    db["meeting_metadata"].update_one(
        {"meeting_id": meeting_id}, {"$set": meta_doc}, upsert=True, session=session
    )

    # 2. transcripts
    segments = [{"start": s.get("start"), "end": s.get("end"), "text": s.get("text", "")} for s in timeline]
    transcript_doc = {
        "meeting_id": meeting_id,
        "full_transcript": transcript,
        "segments": segments,
        "word_count": len(transcript.split()),
        "char_count": len(transcript),
        "segment_count": len(timeline),
        "created_at": now,
    }
    db["transcripts"].update_one(
        {"meeting_id": meeting_id}, {"$set": transcript_doc}, upsert=True, session=session
    )

    # 3. analysis_results
    analysis_doc = {
        "meeting_id": meeting_id,
        "risk_score": risk_score,
        "severity": severity,
        "llm_summary": llm_summary,
        "rule_summary": rule_summary,
        "finding_count": len(findings),
        "unique_categories": stats.get("unique_categories", 0),
        "category_breakdown": stats.get("categories", {}),
        "confidence_stats": stats.get("confidence_stats", {}),
        "severity_distribution": stats.get("severity_distribution", {}),
        "context_type_distribution": stats.get("context_type_distribution", {}),
        "ml_stats": stats.get("ml_stats", {}),
        "word_count": stats.get("word_count"),
        "evidence": evidence or [],
        "analyzed_at": now,
    }
    db["analysis_results"].update_one(
        {"meeting_id": meeting_id}, {"$set": analysis_doc}, upsert=True, session=session
    )

    # 4. safety_findings
    db["safety_findings"].delete_many({"meeting_id": meeting_id}, session=session)
    if findings:
        docs = []
        for f in findings:
            cats = f.get("categories") or ([f["category"]] if f.get("category") else [])
            docs.append({
                "meeting_id": meeting_id,
                "categories": cats,
                "category": cats[0] if cats else "unknown",
                "evidence": f.get("evidence") or f.get("text", ""),
                "confidence": f.get("confidence") or f.get("max_confidence") or 0,
                "context_type": f.get("context_type") or (f.get("context", {}) or {}).get("primary", "NEUTRAL"),
                "severity": f.get("severity", "unknown"),
                "speaker": f.get("speaker"),
                "timestamp": f.get("timestamp"),
                "matched_text": f.get("matched_text"),
                "is_negated": (f.get("filters") or {}).get("is_negated", False),
                "is_joke": (f.get("filters") or {}).get("is_joke", False),
                "ml_label": (f.get("ml") or {}).get("top_label"),
                "ml_confidence": (f.get("ml") or {}).get("top_confidence"),
                "ml_agreement": (f.get("ml") or {}).get("agreement"),
                "created_at": now,
            })
        db["safety_findings"].insert_many(docs, session=session)

    # 5. action_items
    action_items = [
        {
            "category": (f.get("categories") or [f.get("category", "")])[0],
            "evidence": f.get("evidence") or f.get("text", ""),
            "confidence": f.get("confidence") or f.get("max_confidence") or 0,
            "severity": f.get("severity", "unknown"),
            "speaker": f.get("speaker"),
            "priority": "HIGH" if f.get("severity") in ("critical", "high") else "MEDIUM",
        }
        for f in findings if f.get("severity") in ("critical", "high")
    ]
    topics = list(stats.get("categories", {}).keys())
    keywords = list({f.get("matched_text") for f in findings if f.get("matched_text")})
    action_doc = {
        "meeting_id": meeting_id,
        "action_items": action_items,
        "topics": topics,
        "keywords": keywords,
        "action_count": len(action_items),
        "created_at": now,
    }
    db["action_items"].update_one(
        {"meeting_id": meeting_id}, {"$set": action_doc}, upsert=True, session=session
    )

    # 6. processing_status
    status_doc = {
        "meeting_id": meeting_id,
        "status": "COMPLETED",
        "stage": "done",
        "started_at": started_at or now,
        "completed_at": now,
        "error": None,
        "updated_at": now,
    }
    db["processing_status"].update_one(
        {"meeting_id": meeting_id}, {"$set": status_doc}, upsert=True, session=session
    )

    # 7. audit_logs
    audit_doc = {
        "event": "analysis_completed",
        "meeting_id": meeting_id,
        "user_action": None,
        "details": {"severity": severity, "risk_score": risk_score, "findings": len(findings)},
        "timestamp": now,
    }
    db["audit_logs"].insert_one(audit_doc, session=session)


def _save_full_analysis_no_transaction(
    meeting_id, filename, transcript, timeline, findings, risk_score,
    severity, llm_summary, rule_summary, stats, started_at, now,
    s3_url, evidence, pdf_path, s3_pdf_url,
) -> Dict[str, bool]:
    """Non-transactional fallback for standalone MongoDB instances."""
    results = {}

    results["meeting_metadata"] = save_meeting_metadata(
        meeting_id=meeting_id,
        filename=filename,
        duration_seconds=timeline[-1]["end"] if timeline else None,
        participants=list({s.get("speaker") for s in timeline if s.get("speaker")}),
        s3_url=s3_url,
        status="COMPLETED",
        pdf_path=pdf_path,
        s3_pdf_url=s3_pdf_url,
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
        evidence=evidence or [],
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
            "severity": severity,
            "risk_score": risk_score,
            "findings": len(findings),
        },
    )

    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.warning(f"MongoDB: some collections failed for #{meeting_id}: {failed}")
    else:
        logger.info(f"MongoDB: all 7 collections saved for meeting #{meeting_id}")

    return results


# ── Delete all data for a meeting ────────────────────────────────────────────

def delete_meeting_data(meeting_id: int) -> Dict[str, bool]:
    """
    Delete all MongoDB documents for a given meeting_id across all 6 collections.
    audit_logs are kept for compliance — only operational data is removed.
    Returns a dict of {collection: success}.
    """
    db = get_mongo_db()
    if db is None:
        return {}

    collections = [
        "meeting_metadata",
        "transcripts",
        "analysis_results",
        "safety_findings",
        "action_items",
        "processing_status",
    ]

    results = {}
    for col in collections:
        try:
            db[col].delete_many({"meeting_id": meeting_id})
            results[col] = True
        except Exception as e:
            logger.warning(f"MongoDB delete failed [{col}] for meeting #{meeting_id}: {e}")
            results[col] = False

    failed = [k for k, v in results.items() if not v]
    if failed:
        logger.warning(f"MongoDB: failed to delete from {failed} for meeting #{meeting_id}")
    else:
        logger.info(f"MongoDB: all collections cleaned up for meeting #{meeting_id}")

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


# ── Update helpers ────────────────────────────────────────────────────────────

def update_s3_urls(
    meeting_id: int,
    s3_audio_url: Optional[str] = None,
    s3_pdf_url: Optional[str] = None,
) -> bool:
    """Update S3 URLs in meeting_metadata after upload."""
    db = get_mongo_db()
    if db is None:
        return False
    fields: Dict[str, Any] = {"updated_at": _now()}
    if s3_audio_url is not None:
        fields["s3_recording_url"] = s3_audio_url
    if s3_pdf_url is not None:
        fields["s3_pdf_url"] = s3_pdf_url
    try:
        db["meeting_metadata"].update_one(
            {"meeting_id": meeting_id},
            {"$set": fields},
            upsert=True,
        )
        return True
    except Exception as e:
        logger.warning(f"MongoDB update_s3_urls failed for #{meeting_id}: {e}")
        return False


def update_pdf_path(meeting_id: int, pdf_path: str) -> bool:
    """Store local pdf_path in meeting_metadata after PDF generation."""
    db = get_mongo_db()
    if db is None:
        return False
    try:
        db["meeting_metadata"].update_one(
            {"meeting_id": meeting_id},
            {"$set": {"pdf_path": pdf_path, "updated_at": _now()}},
            upsert=True,
        )
        return True
    except Exception as e:
        logger.warning(f"MongoDB update_pdf_path failed for #{meeting_id}: {e}")
        return False


# ── Read helpers (SQLite-free operation) ──────────────────────────────────────

def list_meetings(
    skip: int = 0,
    limit: int = 100,
) -> Dict[str, Any]:
    """
    Paginated history list from meeting_metadata + analysis_results.
    Returns {"reports": [...], "total": int}.
    """
    db = get_mongo_db()
    if db is None:
        return {"reports": [], "total": 0}
    try:
        total = db["meeting_metadata"].count_documents({})
        cursor = (
            db["meeting_metadata"]
            .find({}, {
                "meeting_id": 1, "title": 1, "status": 1,
                "created_at": 1, "_id": 0,
            })
            .sort("meeting_id", -1)
            .skip(skip)
            .limit(limit)
        )
        meetings = list(cursor)

        # Enrich with risk_score + severity from analysis_results
        ids = [m["meeting_id"] for m in meetings]
        ar_cursor = db["analysis_results"].find(
            {"meeting_id": {"$in": ids}},
            {"meeting_id": 1, "risk_score": 1, "severity": 1, "_id": 0},
        )
        ar_map = {r["meeting_id"]: r for r in ar_cursor}

        reports = []
        for m in meetings:
            mid = m["meeting_id"]
            ar  = ar_map.get(mid, {})
            created = m.get("created_at")
            reports.append({
                "id":         mid,
                "filename":   m.get("title", ""),
                "severity":   ar.get("severity"),
                "risk_score": ar.get("risk_score"),
                "status":     m.get("status", "COMPLETED"),
                "created_at": (created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created).isoformat() if hasattr(created, "isoformat") else str(created) if created else None,
            })

        return {"reports": reports, "total": total}
    except Exception as e:
        logger.warning(f"MongoDB list_meetings failed: {e}")
        return {"reports": [], "total": 0}


def get_meeting(meeting_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single meeting's metadata."""
    db = get_mongo_db()
    if db is None:
        return None
    try:
        doc = db["meeting_metadata"].find_one(
            {"meeting_id": meeting_id}, {"_id": 0}
        )
        return doc
    except Exception as e:
        logger.warning(f"MongoDB get_meeting failed for #{meeting_id}: {e}")
        return None


def get_transcript(meeting_id: int) -> Optional[Dict[str, Any]]:
    """Fetch transcript + timeline for a meeting."""
    db = get_mongo_db()
    if db is None:
        return None
    try:
        return db["transcripts"].find_one({"meeting_id": meeting_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"MongoDB get_transcript failed for #{meeting_id}: {e}")
        return None


def get_analysis(meeting_id: int) -> Optional[Dict[str, Any]]:
    """Fetch full analysis result for a meeting."""
    db = get_mongo_db()
    if db is None:
        return None
    try:
        return db["analysis_results"].find_one({"meeting_id": meeting_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"MongoDB get_analysis failed for #{meeting_id}: {e}")
        return None


def get_findings(meeting_id: int) -> List[Dict[str, Any]]:
    """Fetch safety findings list for a meeting."""
    db = get_mongo_db()
    if db is None:
        return []
    try:
        return list(db["safety_findings"].find({"meeting_id": meeting_id}, {"_id": 0}))
    except Exception as e:
        logger.warning(f"MongoDB get_findings failed for #{meeting_id}: {e}")
        return []


def get_evidence(meeting_id: int) -> List[Dict[str, Any]]:
    """Fetch evidence list for a meeting from analysis_results."""
    db = get_mongo_db()
    if db is None:
        return []
    try:
        doc = db["analysis_results"].find_one(
            {"meeting_id": meeting_id}, {"evidence": 1, "_id": 0}
        )
        return doc.get("evidence", []) if doc else []
    except Exception as e:
        logger.warning(f"MongoDB get_evidence failed for #{meeting_id}: {e}")
        return []


def get_processing_status(meeting_id: int) -> Optional[Dict[str, Any]]:
    """Fetch processing status for a meeting."""
    db = get_mongo_db()
    if db is None:
        return None
    try:
        return db["processing_status"].find_one({"meeting_id": meeting_id}, {"_id": 0})
    except Exception as e:
        logger.warning(f"MongoDB get_processing_status failed for #{meeting_id}: {e}")
        return None


def get_full_report(meeting_id: int) -> Optional[Dict[str, Any]]:
    """
    Assemble a complete report dict from all collections.
    Equivalent to the old SQLite AudioAnalysis row.
    Returns None if the meeting does not exist.
    """
    meta = get_meeting(meeting_id)
    if meta is None:
        return None

    transcript_doc = get_transcript(meeting_id) or {}
    analysis_doc   = get_analysis(meeting_id) or {}
    findings       = get_findings(meeting_id)
    evidence       = get_evidence(meeting_id)
    status_doc     = get_processing_status(meeting_id) or {}

    created = meta.get("created_at")
    created_iso = (created.replace(tzinfo=timezone.utc) if created.tzinfo is None else created).isoformat() if hasattr(created, "isoformat") else str(created) if created else None

    # Timeline segments (no diarization)
    timeline = transcript_doc.get("segments", []) or transcript_doc.get("speaker_segments", [])

    return {
        "id":          meeting_id,
        "filename":    meta.get("title", ""),
        "transcript":  transcript_doc.get("full_transcript", ""),
        "findings":    findings,
        "evidence":    evidence,
        "stats": {
            "categories":               analysis_doc.get("category_breakdown", {}),
            "confidence_stats":         analysis_doc.get("confidence_stats", {}),
            "severity_distribution":    analysis_doc.get("severity_distribution", {}),
            "context_type_distribution":analysis_doc.get("context_type_distribution", {}),
            "ml_stats":                 analysis_doc.get("ml_stats", {}),
            "word_count":               analysis_doc.get("word_count"),
            "finding_count":            analysis_doc.get("finding_count", 0),
            "unique_categories":        analysis_doc.get("unique_categories", 0),
        },
        "summary":     analysis_doc.get("rule_summary", ""),
        "llm_summary": analysis_doc.get("llm_summary", ""),
        "severity":    analysis_doc.get("severity"),
        "risk_score":  analysis_doc.get("risk_score"),
        "pdf_path":    meta.get("pdf_path"),
        "s3_audio_url": meta.get("s3_recording_url"),
        "s3_pdf_url":  meta.get("s3_pdf_url"),
        "status":      status_doc.get("status", meta.get("status", "COMPLETED")),
        "error_message": status_doc.get("error"),
        "timeline":    timeline,
        "created_at":  created_iso,
    }


def get_analytics_summary() -> Dict[str, Any]:
    """
    Aggregate analytics across all meetings using MongoDB aggregation pipelines.
    """
    db = get_mongo_db()
    if db is None:
        return _empty_analytics()

    try:
        # Pipeline 1: Aggregate analysis_results
        ar_pipeline = [
            {
                "$group": {
                    "_id": None,
                    "total_reports": {"$sum": 1},
                    "total_findings": {"$sum": {"$ifNull": ["$finding_count", 0]}},
                    "avg_risk_score": {"$avg": {"$ifNull": ["$risk_score", 0]}},
                    "risk_scores": {"$push": "$risk_score"},
                    "severities": {"$push": "$severity"},
                    "category_breakdowns": {"$push": "$category_breakdown"},
                    "context_distributions": {"$push": "$context_type_distribution"},
                    "ml_stats_list": {"$push": "$ml_stats"},
                    "confidence_stats_list": {"$push": "$confidence_stats"},
                    "meeting_ids": {"$push": "$meeting_id"},
                }
            }
        ]
        ar_result = list(db["analysis_results"].aggregate(ar_pipeline))

        if not ar_result:
            return _empty_analytics()

        agg = ar_result[0]
        total_reports = agg.get("total_reports", 0)
        total_findings = agg.get("total_findings", 0)
        avg_risk = round(agg.get("avg_risk_score", 0) or 0, 2)

        # Severity distribution
        severity_dist: Dict[str, int] = {}
        for sev in (agg.get("severities") or []):
            s = (sev or "unknown").capitalize()
            severity_dist[s] = severity_dist.get(s, 0) + 1

        # Risk score histogram
        risk_histogram = {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0}
        for score in (agg.get("risk_scores") or []):
            s = score or 0
            if s <= 20:   risk_histogram["0-20"] += 1
            elif s <= 40: risk_histogram["21-40"] += 1
            elif s <= 60: risk_histogram["41-60"] += 1
            elif s <= 80: risk_histogram["61-80"] += 1
            else:         risk_histogram["81-100"] += 1

        # Category totals
        category_totals: Dict[str, int] = {}
        for breakdown in (agg.get("category_breakdowns") or []):
            if breakdown:
                for cat, cnt in breakdown.items():
                    category_totals[cat] = category_totals.get(cat, 0) + (cnt or 0)

        # Context type totals
        context_totals: Dict[str, int] = {}
        for dist in (agg.get("context_distributions") or []):
            if dist:
                for ctx, cnt in dist.items():
                    context_totals[ctx] = context_totals.get(ctx, 0) + (cnt or 0)

        # ML agreement totals
        ml_agreed = ml_disagreed = ml_total = 0
        for ml_s in (agg.get("ml_stats_list") or []):
            if ml_s:
                ml_agreed += ml_s.get("agreed", 0)
                ml_disagreed += ml_s.get("disagreed", 0)
                ml_total += ml_s.get("total_with_ml", 0)
        ml_rate = round(ml_agreed / ml_total, 4) if ml_total > 0 else None

        # Confidence histogram
        conf_histogram: Dict[str, int] = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
        for conf_s in (agg.get("confidence_stats_list") or []):
            if conf_s:
                avg_conf = conf_s.get("average")
                if avg_conf is not None:
                    pct = float(avg_conf) * 100
                    if pct <= 25:   conf_histogram["0-25"] += 1
                    elif pct <= 50: conf_histogram["25-50"] += 1
                    elif pct <= 75: conf_histogram["50-75"] += 1
                    else:           conf_histogram["75-100"] += 1

        # Pipeline 2: Status distribution from processing_status
        status_pipeline = [
            {"$group": {"_id": "$status", "count": {"$sum": 1}}}
        ]
        status_result = list(db["processing_status"].aggregate(status_pipeline))
        status_dist = {doc["_id"]: doc["count"] for doc in status_result if doc["_id"]}

        top_categories = sorted(
            [{"category": k, "count": v} for k, v in category_totals.items()],
            key=lambda x: x["count"], reverse=True,
        )
        high_confidence_count = conf_histogram.get("75-100", 0)

        return {
            "total_reports":       total_reports,
            "total_findings":      total_findings,
            "avg_risk_score":      avg_risk,
            "severity_distribution": severity_dist,
            "status_distribution": status_dist,
            "risk_score_histogram": risk_histogram,
            "top_categories":      top_categories,
            "context_type_totals": context_totals,
            "ml_agreement_totals": {
                "agreed":    ml_agreed,
                "disagreed": ml_disagreed,
                "total":     ml_total,
                "rate":      ml_rate,
            },
            "confidence_histogram":   conf_histogram,
            "high_confidence_count":  high_confidence_count,
        }
    except Exception as e:
        logger.warning(f"MongoDB get_analytics_summary failed: {e}")
        return _empty_analytics()


def _empty_analytics() -> Dict[str, Any]:
    return {
        "total_reports": 0, "total_findings": 0, "avg_risk_score": 0.0,
        "severity_distribution": {}, "status_distribution": {},
        "risk_score_histogram": {"0-20": 0, "21-40": 0, "41-60": 0, "61-80": 0, "81-100": 0},
        "top_categories": [], "context_type_totals": {},
        "ml_agreement_totals": {"agreed": 0, "disagreed": 0, "total": 0, "rate": None},
        "confidence_histogram": {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0},
        "high_confidence_count": 0,
    }


# ── Health ────────────────────────────────────────────────────────────────────

def ping() -> bool:
    return get_mongo_db() is not None
