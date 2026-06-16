"""
Webhook Routes (outbound callbacks)
====================================
Prefix: /api/v1

This module handles sending webhook notifications to the MW backend
when analysis completes or fails. It also provides an endpoint for
the MW backend to register/configure callback URLs.

Endpoints:
  POST /api/v1/webhook/test    → test the webhook connection (admin only)
"""

import os
import hmac
import hashlib
import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Webhook"],
)

# ── Configuration ─────────────────────────────────────────────────────────────

MW_BACKEND_URL = os.getenv("MW_BACKEND_URL", "")
MW_CALLBACK_SECRET = os.getenv("MW_CALLBACK_SECRET", "")
MW_CALLBACK_PATH = "/api/v1/admin/safety/webhook"


# ── Outbound webhook sender ──────────────────────────────────────────────────

async def notify_mw_backend(
    meeting_id: int,
    status: str,
    severity: Optional[str] = None,
    risk_score: Optional[float] = None,
    error: Optional[str] = None,
) -> bool:
    """
    Send a webhook notification to the MW backend when analysis is done.
    Returns True if the callback was successful, False otherwise.
    
    If MW_BACKEND_URL is not configured, this is a no-op (returns True).
    """
    if not MW_BACKEND_URL:
        logger.debug("MW_BACKEND_URL not set — skipping webhook callback")
        return True

    payload = {
        "meeting_id": meeting_id,
        "status": status,
        "severity": severity,
        "risk_score": risk_score,
        "error": error,
    }

    # Generate HMAC signature
    signature = ""
    if MW_CALLBACK_SECRET:
        import json
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        signature = hmac.HMAC(
            key=MW_CALLBACK_SECRET.encode(),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        payload["hmac_signature"] = signature

    url = f"{MW_BACKEND_URL.rstrip('/')}{MW_CALLBACK_PATH}"

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(url, json=payload)
            if response.status_code == 200:
                logger.info(
                    f"Webhook sent to MW backend: meeting_id={meeting_id}, status={status}"
                )
                return True
            else:
                logger.warning(
                    f"MW webhook callback returned {response.status_code}: {response.text}"
                )
                return False
    except Exception as e:
        logger.warning(f"MW webhook callback failed: {e}")
        return False


# ── Sync version for use in background threads ────────────────────────────────

def notify_mw_backend_sync(
    meeting_id: int,
    status: str,
    severity: Optional[str] = None,
    risk_score: Optional[float] = None,
    error: Optional[str] = None,
) -> bool:
    """
    Synchronous version of notify_mw_backend for use in Celery tasks
    and background threads where asyncio isn't available.
    """
    if not MW_BACKEND_URL:
        return True

    import json
    payload = {
        "meeting_id": meeting_id,
        "status": status,
        "severity": severity,
        "risk_score": risk_score,
        "error": error,
    }

    if MW_CALLBACK_SECRET:
        payload_bytes = json.dumps(payload, sort_keys=True).encode()
        signature = hmac.HMAC(
            key=MW_CALLBACK_SECRET.encode(),
            msg=payload_bytes,
            digestmod=hashlib.sha256,
        ).hexdigest()
        payload["hmac_signature"] = signature

    url = f"{MW_BACKEND_URL.rstrip('/')}{MW_CALLBACK_PATH}"

    try:
        import requests
        response = requests.post(url, json=payload, timeout=10)
        if response.status_code == 200:
            logger.info(
                f"Webhook sent to MW backend (sync): meeting_id={meeting_id}, status={status}"
            )
            return True
        else:
            logger.warning(
                f"MW webhook callback returned {response.status_code}: {response.text}"
            )
            return False
    except Exception as e:
        logger.warning(f"MW webhook callback failed (sync): {e}")
        return False


# ── Test endpoint ─────────────────────────────────────────────────────────────

class WebhookTestResponse(BaseModel):
    success: bool
    message: str
    target_url: str


@router.post("/webhook/test", response_model=WebhookTestResponse)
async def test_webhook(current_user: dict = Depends(get_current_user)):
    """
    Test the webhook connection to the MW backend.
    Sends a test payload with meeting_id=-1.
    """
    if not MW_BACKEND_URL:
        return WebhookTestResponse(
            success=False,
            message="MW_BACKEND_URL is not configured in .env",
            target_url="",
        )

    url = f"{MW_BACKEND_URL.rstrip('/')}{MW_CALLBACK_PATH}"
    success = await notify_mw_backend(
        meeting_id=-1,
        status="TEST",
        severity="Safe",
        risk_score=0.0,
    )

    return WebhookTestResponse(
        success=success,
        message="Webhook test sent successfully" if success else "Webhook test failed",
        target_url=url,
    )
