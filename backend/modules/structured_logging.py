"""
Structured JSON logging for production observability.

Usage:
    from modules.structured_logging import setup_logging
    setup_logging()

When ENV=production or LOG_FORMAT=json, all log output is emitted as
single-line JSON objects suitable for ingestion by ELK, CloudWatch, Datadog, etc.

JSON log fields:
    timestamp, level, logger, message, request_id (if available),
    module, funcName, lineno, exc_info (if exception)

In development mode (default), standard human-readable format is used.

Centralized Log Shipping:
    Set LOG_SHIP_TARGET=cloudwatch (requires boto3 + AWS creds) or
    LOG_SHIP_TARGET=stdout_json (container logging driver picks it up).
    For ELK/Datadog, use stdout_json + configure your container log driver
    (e.g. fluentd, awslogs, or datadog agent).
"""

import json
import logging
import os
import sys
import traceback
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "funcName": record.funcName,
            "lineno": record.lineno,
        }

        # Add request_id if available (set by RequestIDMiddleware)
        if hasattr(record, "request_id"):
            log_entry["request_id"] = record.request_id

        # Add extra fields passed via logger.info("msg", extra={...})
        for key in ("meeting_id", "user", "action", "duration_ms", "status_code"):
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        # Add exception info
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exc_type"] = record.exc_info[0].__name__
            log_entry["exc_message"] = str(record.exc_info[1])
            log_entry["exc_traceback"] = traceback.format_exception(*record.exc_info)

        return json.dumps(log_entry, default=str, ensure_ascii=False)


def setup_logging() -> None:
    """
    Configure logging based on environment.

    - ENV=production or LOG_FORMAT=json → JSON structured logging
    - Otherwise → human-readable format (development)

    Respects existing LOG_MAX_SIZE_MB and LOG_BACKUP_COUNT env vars.
    """
    env = os.getenv("ENV", os.getenv("ENVIRONMENT", "development")).lower()
    log_format = os.getenv("LOG_FORMAT", "").lower()
    use_json = log_format == "json" or env in ("production", "prod", "staging")

    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_max_bytes = int(os.getenv("LOG_MAX_SIZE_MB", "50")) * 1024 * 1024
    log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))

    os.makedirs("logs", exist_ok=True)

    # Clear existing handlers
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(getattr(logging, log_level, logging.INFO))

    if use_json:
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter(
            "%(asctime)s [%(name)s] %(levelname)s %(message)s"
        )

    # File handler
    file_handler = RotatingFileHandler(
        "logs/app.log",
        maxBytes=log_max_bytes,
        backupCount=log_backup_count,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    root.addHandler(console_handler)

    # Reduce noise from third-party libraries
    for noisy_logger in ("urllib3", "botocore", "boto3", "s3transfer", "pymongo"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # ── Centralized log shipping ─────────────────────────────────────────────
    log_ship_target = os.getenv("LOG_SHIP_TARGET", "").lower()

    if log_ship_target == "cloudwatch":
        _setup_cloudwatch_handler(root, log_level)
    elif log_ship_target == "stdout_json":
        # Force JSON to stdout — container log drivers (awslogs, fluentd, datadog)
        # will pick it up automatically. This avoids needing in-app SDKs.
        if not use_json:
            # Replace console handler with JSON formatter for shipping
            root.removeHandler(console_handler)
            json_console = logging.StreamHandler(sys.stdout)
            json_console.setFormatter(JSONFormatter())
            root.addHandler(json_console)

    logging.getLogger(__name__).info(
        f"Logging configured: format={'json' if use_json else 'text'}, "
        f"level={log_level}, env={env}, ship_target={log_ship_target or 'none'}"
    )


def _setup_cloudwatch_handler(root_logger: logging.Logger, log_level: str) -> None:
    """
    Optionally attach a CloudWatch Logs handler.

    Requires: pip install watchtower
    Environment variables:
        AWS_REGION (or AWS_DEFAULT_REGION)
        LOG_GROUP_NAME (default: /rmsi/backend)
        LOG_STREAM_NAME (default: auto-generated from hostname)

    If watchtower is not installed, logs a warning and skips.
    """
    try:
        import watchtower
        import boto3

        log_group = os.getenv("LOG_GROUP_NAME", "/rmsi/backend")
        log_stream = os.getenv("LOG_STREAM_NAME", None)  # None = auto from host
        region = os.getenv("AWS_REGION", os.getenv("AWS_DEFAULT_REGION", "us-east-1"))

        cw_client = boto3.client("logs", region_name=region)
        cw_handler = watchtower.CloudWatchLogHandler(
            log_group_name=log_group,
            stream_name=log_stream,
            boto3_client=cw_client,
            send_interval=10,
            log_group_retention_days=30,
        )
        cw_handler.setFormatter(JSONFormatter())
        cw_handler.setLevel(getattr(logging, log_level, logging.INFO))
        root_logger.addHandler(cw_handler)

        logging.getLogger(__name__).info(
            f"CloudWatch log shipping enabled: group={log_group}, region={region}"
        )
    except ImportError:
        logging.getLogger(__name__).warning(
            "LOG_SHIP_TARGET=cloudwatch but 'watchtower' not installed. "
            "Install with: pip install watchtower. Skipping CloudWatch handler."
        )
    except Exception as e:
        logging.getLogger(__name__).error(
            f"Failed to configure CloudWatch handler: {e}. Skipping."
        )
