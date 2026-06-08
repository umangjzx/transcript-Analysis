"""
Notification Routes
===================
Prefix: /api/v1

Endpoints:
  POST /notify/alert/{report_id}   → send parent-friendly alert email
  POST /notify/summary/{report_id} → send admin/internal summary email (full detail)
  POST /notify/admin/{report_id}   → send admin/internal report email (full detail)
"""

import json
import logging
from typing import Optional, Dict, Any, List

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from auth import get_current_user
from database.mongo import get_full_report, audit_log, log_alert
from modules.email_notifier import send_alert_email, send_summary_email, send_admin_report
from config import APP_URL

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Notifications"],
)


class NotifyRequest(BaseModel):
    recipients: Optional[list] = None


def _load_report_for_notify(report_id: int) -> Dict[str, Any]:
    report = get_full_report(report_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


def _parse_json_field(val, default):
    if val is None:
        return default
    if isinstance(val, (list, dict)):
        return val
    try:
        return json.loads(val)
    except Exception:
        return default


@router.post("/notify/alert/{report_id}")
def notify_alert(
    report_id: int,
    body: NotifyRequest = NotifyRequest(),
    current_user: dict = Depends(get_current_user),
):
    """Send a parent-friendly alert email for this report (simplified, no internal data)."""
    report = _load_report_for_notify(report_id)
    findings   = _parse_json_field(report.get("findings"), [])
    stats      = _parse_json_field(report.get("stats"), {})
    transcript = report.get("transcript") or None
    result = send_alert_email(
        report_id=report_id,
        filename=report.get("filename", ""),
        severity=report.get("severity") or "Unknown",
        risk_score=report.get("risk_score") or 0,
        findings=findings,
        summary=report.get("llm_summary") or report.get("summary") or "",
        stats=stats,
        pdf_path=report.get("pdf_path"),
        recipients=body.recipients or None,
        app_url=APP_URL,
        transcript=transcript,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.get("filename", ""), report.get("severity") or "",
              report.get("risk_score") or 0, result["recipients"], email_type="alert")
    audit_log("alert_email_manual", meeting_id=report_id, user_action="send_alert",
              details={"recipients": result["recipients"]})
    return result


@router.post("/notify/summary/{report_id}")
def notify_summary(
    report_id: int,
    body: NotifyRequest = NotifyRequest(),
    current_user: dict = Depends(get_current_user),
):
    """Send a full-detail admin/internal summary email for this report."""
    report = _load_report_for_notify(report_id)
    findings   = _parse_json_field(report.get("findings"), [])
    stats      = _parse_json_field(report.get("stats"), {})
    transcript = report.get("transcript") or None
    result = send_summary_email(
        report_id=report_id,
        filename=report.get("filename", ""),
        severity=report.get("severity") or "Unknown",
        risk_score=report.get("risk_score") or 0,
        findings=findings,
        llm_summary=report.get("llm_summary") or "",
        rule_summary=report.get("summary") or "",
        stats=stats,
        pdf_path=report.get("pdf_path"),
        recipients=body.recipients or None,
        app_url=APP_URL,
        transcript=transcript,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.get("filename", ""), report.get("severity") or "",
              report.get("risk_score") or 0, result["recipients"], email_type="summary")
    audit_log("summary_email_sent", meeting_id=report_id, user_action="send_summary",
              details={"recipients": result["recipients"]})
    return result


@router.post("/notify/admin/{report_id}")
def notify_admin(
    report_id: int,
    body: NotifyRequest = NotifyRequest(),
    current_user: dict = Depends(get_current_user),
):
    """
    Send a full-detail admin/internal report email for this report.

    Includes complete AI analysis, risk indicators, confidence stats,
    category breakdown, findings detail, and technical metadata.
    Only send to internal staff — never to parents.
    """
    report = _load_report_for_notify(report_id)
    findings   = _parse_json_field(report.get("findings"), [])
    stats      = _parse_json_field(report.get("stats"), {})
    transcript = report.get("transcript") or None
    from modules.email_notifier import send_admin_report
    result = send_admin_report(
        report_id=report_id,
        filename=report.get("filename", ""),
        severity=report.get("severity") or "Unknown",
        risk_score=report.get("risk_score") or 0,
        findings=findings,
        llm_summary=report.get("llm_summary") or "",
        rule_summary=report.get("summary") or "",
        stats=stats,
        pdf_path=report.get("pdf_path"),
        recipients=body.recipients or None,
        app_url=APP_URL,
        transcript=transcript,
    )
    if not result["success"]:
        raise HTTPException(status_code=500, detail=result["message"])
    log_alert(report_id, report.get("filename", ""), report.get("severity") or "",
              report.get("risk_score") or 0, result["recipients"], email_type="admin_report")
    audit_log("admin_report_email_sent", meeting_id=report_id, user_action="send_admin_report",
              details={"recipients": result["recipients"]})
    return result
