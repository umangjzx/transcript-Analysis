"""
MongoDB Database Migrations.

Implements a simple migration system for MongoDB schema changes.
Migrations are tracked in a `_migrations` collection.

Usage:
    from database.migrations import run_migrations
    run_migrations()  # Called on app startup

Each migration is a function decorated with @migration("version_id").
Migrations run in order and are idempotent (tracked by version_id).
"""

import logging
from datetime import datetime, timezone
from typing import Callable, List, Dict, Any, Optional

logger = logging.getLogger(__name__)

# Registry of all migrations
_migrations: List[Dict[str, Any]] = []


def migration(version: str, description: str = ""):
    """
    Decorator to register a database migration.

    Args:
        version: Unique version identifier (e.g., "001_add_indexes")
        description: Human-readable description of the migration
    """
    def decorator(func: Callable):
        _migrations.append({
            "version": version,
            "description": description or func.__doc__ or "",
            "func": func,
        })
        return func
    return decorator


def run_migrations() -> Dict[str, Any]:
    """
    Run all pending migrations.

    Returns:
        {
            "applied": List[str],  # Newly applied migration versions
            "skipped": List[str],  # Already applied migrations
            "failed": List[str],   # Failed migrations
            "total": int,
        }
    """
    from database.mongo import get_mongo_db

    db = get_mongo_db()
    if db is None:
        logger.warning("MongoDB unavailable — skipping migrations")
        return {"applied": [], "skipped": [], "failed": [], "total": 0}

    migrations_col = db["_migrations"]
    applied = []
    skipped = []
    failed = []

    # Get already-applied migrations
    applied_versions = set()
    try:
        for doc in migrations_col.find({}, {"version": 1, "_id": 0}):
            applied_versions.add(doc["version"])
    except Exception as e:
        logger.warning(f"Could not read migration history: {e}")

    # Sort migrations by version
    sorted_migrations = sorted(_migrations, key=lambda m: m["version"])

    for mig in sorted_migrations:
        version = mig["version"]

        if version in applied_versions:
            skipped.append(version)
            continue

        try:
            logger.info(f"Running migration: {version} — {mig['description']}")
            mig["func"](db)

            # Record successful migration
            migrations_col.insert_one({
                "version": version,
                "description": mig["description"],
                "applied_at": datetime.now(timezone.utc),
            })
            applied.append(version)
            logger.info(f"Migration {version} applied successfully")

        except Exception as e:
            logger.error(f"Migration {version} FAILED: {e}", exc_info=True)
            failed.append(version)
            # Stop on first failure to prevent cascading issues
            break

    result = {
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "total": len(sorted_migrations),
    }

    if applied:
        logger.info(f"Migrations complete: {len(applied)} applied, {len(skipped)} skipped")
    elif not failed:
        logger.debug("All migrations already applied")

    return result


# ══════════════════════════════════════════════════════════════════════════════
# MIGRATION DEFINITIONS
# ══════════════════════════════════════════════════════════════════════════════


@migration("001_initial_indexes", "Create initial indexes for all collections")
def _001_initial_indexes(db):
    """Ensure all required indexes exist (idempotent)."""
    from pymongo import ASCENDING, DESCENDING
    from pymongo.errors import OperationFailure

    def safe_create_index(collection, keys, **kwargs):
        """Create index, handling conflicts by dropping and recreating."""
        try:
            db[collection].create_index(keys, **kwargs)
        except OperationFailure as e:
            if e.code == 86:  # IndexKeySpecsConflict
                # Drop the conflicting index and recreate
                index_name = kwargs.get("name") or "_".join(
                    f"{k}_{v}" for k, v in keys
                )
                try:
                    db[collection].drop_index(index_name)
                    db[collection].create_index(keys, **kwargs)
                except Exception:
                    pass  # Index already correct, just different options
            else:
                raise

    safe_create_index("meeting_metadata", [("meeting_id", ASCENDING)], unique=True)
    safe_create_index("meeting_metadata", [("created_at", DESCENDING)])
    safe_create_index("meeting_metadata", [("status", ASCENDING)])

    safe_create_index("transcripts", [("meeting_id", ASCENDING)], unique=True)
    safe_create_index("analysis_results", [("meeting_id", ASCENDING)], unique=True)
    safe_create_index("analysis_results", [("risk_score", DESCENDING)])
    safe_create_index("analysis_results", [("severity", ASCENDING)])

    safe_create_index("safety_findings", [("meeting_id", ASCENDING)])
    safe_create_index("safety_findings", [("category", ASCENDING)])

    safe_create_index("processing_status", [("meeting_id", ASCENDING)], unique=True)
    safe_create_index("processing_status", [("status", ASCENDING)])

    safe_create_index("audit_logs", [("meeting_id", ASCENDING)])
    safe_create_index("audit_logs", [("timestamp", DESCENDING)])
    db["audit_logs"].create_index([("event_type", ASCENDING)])

    db["users"].create_index([("username", ASCENDING)], unique=True)


@migration("002_schema_validation", "Add JSON Schema validation to collections")
def _002_schema_validation(db):
    """Apply MongoDB JSON Schema validation rules."""
    # Meeting metadata schema
    db.command("collMod", "meeting_metadata", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["meeting_id", "status"],
            "properties": {
                "meeting_id": {"bsonType": "int", "description": "Unique meeting identifier"},
                "title": {"bsonType": ["string", "null"], "description": "Original filename"},
                "status": {
                    "bsonType": "string",
                    "enum": ["PROCESSING", "COMPLETED", "FAILED"],
                    "description": "Processing status",
                },
                "file_size_bytes": {"bsonType": ["int", "long", "null"]},
                "created_at": {"bsonType": ["date", "null"]},
                "pdf_path": {"bsonType": ["string", "null"]},
                "s3_recording_url": {"bsonType": ["string", "null"]},
                "s3_pdf_url": {"bsonType": ["string", "null"]},
            },
        }
    }, validationLevel="moderate", validationAction="warn")

    # Analysis results schema
    db.command("collMod", "analysis_results", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["meeting_id"],
            "properties": {
                "meeting_id": {"bsonType": "int"},
                "risk_score": {"bsonType": ["double", "int", "null"]},
                "severity": {
                    "bsonType": ["string", "null"],
                    "enum": ["Safe", "Low", "Moderate", "High", "Critical", None],
                },
                "finding_count": {"bsonType": ["int", "null"]},
                "word_count": {"bsonType": ["int", "null"]},
                "llm_summary": {"bsonType": ["string", "null"]},
                "rule_summary": {"bsonType": ["string", "null"]},
            },
        }
    }, validationLevel="moderate", validationAction="warn")

    # Processing status schema
    db.command("collMod", "processing_status", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["meeting_id", "status"],
            "properties": {
                "meeting_id": {"bsonType": "int"},
                "status": {
                    "bsonType": "string",
                    "enum": ["PROCESSING", "COMPLETED", "FAILED"],
                },
                "stage": {"bsonType": ["string", "null"]},
                "error": {"bsonType": ["string", "null"]},
                "started_at": {"bsonType": ["date", "null"]},
                "completed_at": {"bsonType": ["date", "null"]},
                "updated_at": {"bsonType": ["date", "null"]},
            },
        }
    }, validationLevel="moderate", validationAction="warn")

    # Users schema
    db.command("collMod", "users", validator={
        "$jsonSchema": {
            "bsonType": "object",
            "required": ["username", "password_hash", "role"],
            "properties": {
                "username": {"bsonType": "string", "minLength": 1},
                "password_hash": {"bsonType": "string"},
                "role": {
                    "bsonType": "string",
                    "enum": ["admin", "analyst", "viewer"],
                },
                "created_at": {"bsonType": ["date", "null"]},
            },
        }
    }, validationLevel="moderate", validationAction="warn")


@migration("003_ttl_indexes", "Add TTL indexes for automatic document expiry")
def _003_ttl_indexes(db):
    """Add TTL indexes for audit logs and processing status."""
    import os
    from pymongo import ASCENDING

    audit_ttl_days = int(os.getenv("AUDIT_LOG_TTL_DAYS", "90"))
    processing_ttl_days = int(os.getenv("PROCESSING_STATUS_TTL_DAYS", "30"))

    # Drop existing TTL indexes if they exist (to update expiry)
    try:
        db["audit_logs"].drop_index("ttl_audit_logs_timestamp")
    except Exception:
        pass
    try:
        db["processing_status"].drop_index("ttl_processing_status_updated_at")
    except Exception:
        pass

    db["audit_logs"].create_index(
        [("timestamp", ASCENDING)],
        expireAfterSeconds=audit_ttl_days * 86400,
        name="ttl_audit_logs_timestamp",
    )
    db["processing_status"].create_index(
        [("updated_at", ASCENDING)],
        expireAfterSeconds=processing_ttl_days * 86400,
        name="ttl_processing_status_updated_at",
    )


@migration("004_add_temporal_fields", "Add temporal and escalation fields to analysis_results")
def _004_add_temporal_fields(db):
    """Add temporal_weighting and escalation_patterns fields to existing analysis results."""
    # This is a schema-level change — MongoDB is schemaless so we just ensure
    # the field exists in new documents. Existing docs will get it on next analysis.
    # No data migration needed.
    pass


@migration("005_connection_pool_config", "Document connection pool settings")
def _005_connection_pool_config(db):
    """
    This migration documents that connection pooling is now configured.
    The actual pooling config is in get_mongo_db() via MongoClient parameters.
    """
    pass
