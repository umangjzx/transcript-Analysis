"""
AWS S3 Storage — 5-type file storage for AuraSafety.

Bucket layout
-------------
  recordings/<YYYY>/<MM>/<report_id>_<filename>   ← original + extracted audio
  reports/<YYYY>/<MM>/report_<report_id>.pdf       ← generated PDF reports
  exports/<YYYY>/<MM>/<report_id>_<name>.<ext>     ← CSV / JSON / XLSX exports
  backups/<YYYY>/<MM>/<report_id>_<filename>       ← long-term archives

Storage types
-------------
  1. Original Meeting Recordings  (.mp4)
  2. Extracted Audio Files        (.wav / .mp3 / .m4a / .aac / .ogg)
  3. Generated Reports            (.pdf)
  4. Exported Files               (.csv / .json / .xlsx)
  5. Backups & Archives           (any)

Configuration (via .env)
------------------------
  AWS_ACCESS_KEY_ID
  AWS_SECRET_ACCESS_KEY
  AWS_REGION    (default: us-east-1)
  S3_BUCKET
"""

import io
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_s3_client = None

# ── Content-type map ──────────────────────────────────────────────────────────
_CONTENT_TYPES: Dict[str, str] = {
    ".mp4":  "video/mp4",
    ".mp3":  "audio/mpeg",
    ".wav":  "audio/wav",
    ".m4a":  "audio/mp4",
    ".aac":  "audio/aac",
    ".ogg":  "audio/ogg",
    ".flac": "audio/flac",
    ".pdf":  "application/pdf",
    ".csv":  "text/csv",
    ".json": "application/json",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


# ── Client ────────────────────────────────────────────────────────────────────

def _get_client():
    """Lazy singleton boto3 S3 client."""
    global _s3_client
    if _s3_client is not None:
        return _s3_client
    try:
        from dotenv import dotenv_values
        import boto3

        v      = dotenv_values(os.path.join(os.path.dirname(__file__), '..', '.env'))
        key    = v.get("AWS_ACCESS_KEY_ID", "") or os.getenv("AWS_ACCESS_KEY_ID", "")
        secret = v.get("AWS_SECRET_ACCESS_KEY", "") or os.getenv("AWS_SECRET_ACCESS_KEY", "")
        region = v.get("AWS_REGION", "") or os.getenv("AWS_REGION", "us-east-1")

        if not key or not secret:
            logger.warning("AWS credentials not set — S3 disabled")
            return None

        _s3_client = boto3.client(
            "s3",
            aws_access_key_id=key,
            aws_secret_access_key=secret,
            region_name=region,
        )
        return _s3_client
    except ImportError:
        logger.warning("boto3 not installed — run: pip install boto3")
        return None
    except Exception as e:
        logger.warning(f"S3 client init failed: {e}")
        return None


def _get_bucket() -> str:
    from dotenv import dotenv_values
    v = dotenv_values(os.path.join(os.path.dirname(__file__), '..', '.env'))
    return v.get("S3_BUCKET", "") or os.getenv("S3_BUCKET", "")


def _get_region() -> str:
    from dotenv import dotenv_values
    v = dotenv_values(os.path.join(os.path.dirname(__file__), '..', '.env'))
    return v.get("AWS_REGION", "") or os.getenv("AWS_REGION", "us-east-1")


def _now_prefix() -> str:
    n = datetime.now(timezone.utc)
    return f"{n.year}/{n.month:02d}"


def _content_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return _CONTENT_TYPES.get(ext, "application/octet-stream")


def _upload(local_path: str, key: str, content_type: str) -> Optional[str]:
    """Core upload — returns public-style URL or None."""
    s3     = _get_client()
    bucket = _get_bucket()
    region = _get_region()

    if s3 is None or not bucket:
        return None
    if not os.path.exists(local_path):
        logger.warning(f"S3: file not found: {local_path}")
        return None
    try:
        s3.upload_file(
            local_path, bucket, key,
            ExtraArgs={
                "ContentType": content_type,
                "ServerSideEncryption": "AES256",
            },
        )
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
        logger.info(f"S3 uploaded: {url}")
        return url
    except Exception as e:
        logger.error(f"S3 upload failed [{key}]: {e}")
        return None


def _upload_bytes(data: bytes, key: str, content_type: str) -> Optional[str]:
    """Upload from bytes buffer — for in-memory exports."""
    s3     = _get_client()
    bucket = _get_bucket()
    region = _get_region()

    if s3 is None or not bucket:
        return None
    try:
        s3.put_object(
            Bucket=bucket, Key=key,
            Body=data,
            ContentType=content_type,
            ServerSideEncryption="AES256",
        )
        url = f"https://{bucket}.s3.{region}.amazonaws.com/{key}"
        logger.info(f"S3 uploaded (bytes): {url}")
        return url
    except Exception as e:
        logger.error(f"S3 put_object failed [{key}]: {e}")
        return None


# ── 1 & 2. Audio files (recordings + extracted audio) ────────────────────────

def upload_audio(
    local_path: str,
    report_id: int,
    filename: str,
) -> Optional[str]:
    """
    Upload original meeting recording or extracted audio file.
    Stored under: recordings/YYYY/MM/<report_id>_<filename>
    """
    key = f"recordings/{_now_prefix()}/{report_id}_{filename}"
    return _upload(local_path, key, _content_type(filename))


# ── 3. Generated PDF reports ──────────────────────────────────────────────────

def upload_pdf_report(
    local_path: str,
    report_id: int,
) -> Optional[str]:
    """
    Upload a generated PDF analysis report.
    Stored under: reports/YYYY/MM/report_<report_id>.pdf
    """
    key = f"reports/{_now_prefix()}/report_{report_id}.pdf"
    return _upload(local_path, key, "application/pdf")


# ── 4. Exported files (CSV / JSON / XLSX) ────────────────────────────────────

def upload_export_json(
    report_id: int,
    data: Dict[str, Any],
    label: str = "report",
) -> Optional[str]:
    """
    Upload a JSON export of report data.
    Stored under: exports/YYYY/MM/<report_id>_<label>.json
    """
    key     = f"exports/{_now_prefix()}/{report_id}_{label}.json"
    payload = json.dumps(data, indent=2, default=str).encode("utf-8")
    return _upload_bytes(payload, key, "application/json")


def upload_export_csv(
    report_id: int,
    csv_content: str,
    label: str = "findings",
) -> Optional[str]:
    """
    Upload a CSV export.
    Stored under: exports/YYYY/MM/<report_id>_<label>.csv
    """
    key = f"exports/{_now_prefix()}/{report_id}_{label}.csv"
    return _upload_bytes(csv_content.encode("utf-8"), key, "text/csv")


def upload_export_file(
    local_path: str,
    report_id: int,
    filename: str,
) -> Optional[str]:
    """
    Upload any export file (xlsx, csv, json) from disk.
    Stored under: exports/YYYY/MM/<report_id>_<filename>
    """
    key = f"exports/{_now_prefix()}/{report_id}_{filename}"
    return _upload(local_path, key, _content_type(filename))


# ── 5. Backups & Archives ─────────────────────────────────────────────────────

def upload_backup(
    local_path: str,
    report_id: int,
    filename: str,
) -> Optional[str]:
    """
    Upload a long-term backup/archive file.
    Stored under: backups/YYYY/MM/<report_id>_<filename>
    """
    key = f"backups/{_now_prefix()}/{report_id}_{filename}"
    return _upload(local_path, key, _content_type(filename))


# ── Presigned URL ─────────────────────────────────────────────────────────────

def get_presigned_url(s3_url: str, expires_in: int = 3600) -> Optional[str]:
    """
    Generate a presigned download URL from a stored S3 URL.
    expires_in: seconds (default 1 hour)
    """
    s3     = _get_client()
    bucket = _get_bucket()

    if s3 is None or not bucket or not s3_url:
        return None

    # Extract key from URL: https://bucket.s3.region.amazonaws.com/<key>
    try:
        key = s3_url.split(".amazonaws.com/", 1)[1]
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
        return url
    except Exception as e:
        logger.warning(f"S3 presigned URL failed: {e}")
        return None


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_file(s3_url: str) -> bool:
    """Delete a file from S3 by its URL. Returns True on success."""
    s3     = _get_client()
    bucket = _get_bucket()

    if s3 is None or not bucket or not s3_url:
        return False
    try:
        key = s3_url.split(".amazonaws.com/", 1)[1]
        s3.delete_object(Bucket=bucket, Key=key)
        logger.info(f"S3 deleted: {key}")
        return True
    except Exception as e:
        logger.warning(f"S3 delete failed: {e}")
        return False


# ── Health check ──────────────────────────────────────────────────────────────

def ping() -> Dict[str, Any]:
    """Check S3 connectivity. Returns status dict."""
    s3     = _get_client()
    bucket = _get_bucket()

    if s3 is None:
        return {"connected": False, "bucket": bucket,
                "message": "S3 client not initialised — check AWS credentials"}
    if not bucket:
        return {"connected": False, "bucket": "",
                "message": "S3_BUCKET not set in .env"}
    try:
        s3.head_bucket(Bucket=bucket)
        return {"connected": True, "bucket": bucket,
                "message": f"Bucket '{bucket}' accessible"}
    except Exception as e:
        return {"connected": False, "bucket": bucket, "message": str(e)}
