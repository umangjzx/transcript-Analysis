"""
Email Notifier — SMTP-based alert and summary emails.

Supports two email types:
  1. Red Alert  — sent automatically when severity is Critical or High
  2. Meeting Summary — sent on demand with full analysis breakdown

Configuration (via .env or environment variables):
    SMTP_HOST        SMTP server hostname          (default: smtp.gmail.com)
    SMTP_PORT        SMTP port                     (default: 587)
    SMTP_USER        Sender email address
    SMTP_PASSWORD    Sender password / app password
    SMTP_FROM_NAME   Display name                  (default: Melody Wings Safety)
    ALERT_RECIPIENTS Comma-separated recipient list
    ALERT_SEVERITY   Minimum severity to auto-alert (default: High)
"""

import os
import smtplib
import logging
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

# Override OS env vars with .env file values
load_dotenv(override=True)

# ── Config ────────────────────────────────────────────────────────────────────

SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT     = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER     = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "Melody Wings Safety")

def _get_recipients() -> List[str]:
    raw = os.getenv("ALERT_RECIPIENTS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]

ALERT_SEVERITY_THRESHOLD = os.getenv("ALERT_SEVERITY", "High").lower()
_SEVERITY_RANK = {"safe": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}

def should_auto_alert(severity: str) -> bool:
    """Return True if severity meets or exceeds the configured threshold."""
    return _SEVERITY_RANK.get((severity or "").lower(), 0) >= _SEVERITY_RANK.get(ALERT_SEVERITY_THRESHOLD, 3)


# ── Colour palette (matches the UI) ──────────────────────────────────────────

_SEV_COLOR = {
    "critical": "#dc2626",
    "high":     "#ef4444",
    "moderate": "#f59e0b",
    "medium":   "#f59e0b",
    "low":      "#3b82f6",
    "safe":     "#10b981",
}

def _sev_color(severity: str) -> str:
    return _SEV_COLOR.get((severity or "").lower(), "#6b7280")

def _score_color(score: float) -> str:
    if score >= 80: return "#dc2626"
    if score >= 61: return "#ef4444"
    if score >= 41: return "#f59e0b"
    if score >= 21: return "#3b82f6"
    return "#10b981"


# ── HTML helpers ──────────────────────────────────────────────────────────────

def _wrap(inner: str, bg: str = "#0f0f13") -> str:
    """Outer wrapper table — centres content, sets background."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Melody Wings Safety</title>
</head>
<body style="margin:0;padding:0;background:{bg};font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0" style="background:{bg};">
  <tr><td align="center" style="padding:32px 16px;">
    <table width="600" cellpadding="0" cellspacing="0" border="0"
           style="background:#1a1a2e;border-radius:12px;border:1px solid #2d2d44;overflow:hidden;max-width:600px;">
      {inner}
    </table>
  </td></tr>
</table>
</body></html>"""


def _header_row(title: str, subtitle: str, accent: str) -> str:
    return f"""
      <tr>
        <td style="background:linear-gradient(135deg,{accent}18,#1a1a2e);
                   border-bottom:2px solid {accent};padding:24px 28px;">
          <div style="font-size:20px;font-weight:700;color:#f1f5f9;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;
                      max-width:540px;">{title}</div>
          <div style="font-size:12px;color:#94a3b8;margin-top:4px;">{subtitle}</div>
        </td>
      </tr>"""


def _score_info_row(filename: str, severity: str, risk_score: float,
                    report_id: int, sev_color: str, score_color: str) -> str:
    short_name = filename if len(filename) <= 40 else filename[:37] + "..."
    return f"""
      <tr>
        <td style="padding:24px 28px 16px;">
          <table cellpadding="0" cellspacing="0" border="0" width="100%">
            <tr>
              <!-- Score circle -->
              <td width="90" valign="middle">
                <table cellpadding="0" cellspacing="0" border="0"
                       style="width:80px;height:80px;border-radius:50%;
                              border:3px solid {score_color};
                              background:{score_color}18;">
                  <tr>
                    <td align="center" valign="middle"
                        style="width:80px;height:80px;border-radius:50%;">
                      <div style="font-size:28px;font-weight:800;
                                  color:{score_color};line-height:1;">
                        {risk_score:.0f}
                      </div>
                      <div style="font-size:10px;color:#94a3b8;margin-top:2px;">
                        / 100
                      </div>
                    </td>
                  </tr>
                </table>
              </td>
              <!-- Info -->
              <td valign="middle" style="padding-left:20px;">
                <div style="font-size:15px;font-weight:600;color:#f1f5f9;
                            margin-bottom:8px;word-break:break-all;">
                  {short_name}
                </div>
                <span style="display:inline-block;padding:3px 12px;
                             border-radius:99px;font-size:12px;font-weight:700;
                             text-transform:uppercase;letter-spacing:.06em;
                             background:{sev_color}22;color:{sev_color};
                             border:1px solid {sev_color}55;">
                  {severity.upper()}
                </span>
                <div style="font-size:11px;color:#64748b;margin-top:6px;">
                  Report ID: #{report_id}
                </div>
              </td>
            </tr>
          </table>
        </td>
      </tr>"""


def _stat_row_3(v1: str, k1: str, c1: str,
                v2: str, k2: str,
                v3: str, k3: str) -> str:
    cell = lambda v, k, c: f"""
      <td width="33%" align="center" valign="top"
          style="background:#0d0d1a;border-radius:8px;padding:14px 8px;">
        <div style="font-size:24px;font-weight:700;color:{c};line-height:1;">{v}</div>
        <div style="font-size:11px;color:#64748b;margin-top:4px;">{k}</div>
      </td>"""
    return f"""
      <tr>
        <td style="padding:0 28px 20px;">
          <table cellpadding="0" cellspacing="4" border="0" width="100%">
            <tr>
              {cell(v1,k1,c1)}
              <td width="4"></td>
              {cell(v2,k2,'#e2e8f0')}
              <td width="4"></td>
              {cell(v3,k3,'#e2e8f0')}
            </tr>
          </table>
        </td>
      </tr>"""


def _section(title: str, content: str) -> str:
    return f"""
      <tr>
        <td style="padding:0 28px 20px;">
          <div style="font-size:10px;font-weight:700;text-transform:uppercase;
                      letter-spacing:.1em;color:#475569;margin-bottom:8px;">
            {title}
          </div>
          {content}
        </td>
      </tr>"""


def _summary_box(text: str, color: str = "#cbd5e1") -> str:
    return f"""<div style="background:#0d0d1a;border-radius:8px;padding:14px 16px;
                           font-size:13px;color:{color};line-height:1.65;">
      {text or 'Not available.'}
    </div>"""


def _finding_rows(findings: List[Dict[str, Any]]) -> str:
    top = sorted(findings,
                 key=lambda f: f.get("confidence") or f.get("max_confidence") or 0,
                 reverse=True)[:5]
    rows = ""
    for f in top:
        cats   = f.get("categories") or ([f["category"]] if f.get("category") else [])
        cat    = ", ".join(c.replace("_", " ").title() for c in cats) or "Unknown"
        text   = (f.get("evidence") or f.get("text") or "")[:110]
        ellip  = "…" if len(f.get("evidence") or f.get("text") or "") > 110 else ""
        conf   = f.get("confidence") or f.get("max_confidence") or 0
        fc     = _score_color(conf * 100)
        rows += f"""
        <tr>
          <td style="padding:0 0 6px;">
            <table cellpadding="0" cellspacing="0" border="0" width="100%"
                   style="background:#0d0d1a;border-radius:8px;
                          border-left:3px solid {fc};overflow:hidden;">
              <tr>
                <td style="padding:10px 14px;">
                  <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                              letter-spacing:.05em;color:{fc};">{cat}</div>
                  <div style="font-size:13px;color:#94a3b8;margin-top:3px;
                              font-style:italic;">"{text}{ellip}"</div>
                  <div style="font-size:11px;color:#475569;margin-top:3px;">
                    Confidence: {conf*100:.1f}%
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""
    return f"""<table cellpadding="0" cellspacing="0" border="0" width="100%">
      {rows or '<tr><td style="color:#64748b;font-size:13px;">No findings available.</td></tr>'}
    </table>"""


def _cat_table(categories: dict) -> str:
    if not categories:
        return ""
    rows = ""
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        rows += f"""
        <tr style="border-bottom:1px solid #1e2a3a;">
          <td style="padding:8px 12px;font-size:13px;color:#cbd5e1;">
            {cat.replace('_',' ').title()}
          </td>
          <td style="padding:8px 12px;font-size:13px;font-weight:700;
                     color:#e2e8f0;text-align:right;">{count}</td>
        </tr>"""
    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%"
           style="background:#0d0d1a;border-radius:8px;overflow:hidden;">
      <tr style="background:#111827;">
        <th style="padding:8px 12px;font-size:10px;text-align:left;
                   color:#475569;text-transform:uppercase;letter-spacing:.08em;
                   font-weight:600;">Category</th>
        <th style="padding:8px 12px;font-size:10px;text-align:right;
                   color:#475569;text-transform:uppercase;letter-spacing:.08em;
                   font-weight:600;">Count</th>
      </tr>
      {rows}
    </table>"""


def _btn_row(href: str, label: str, bg: str) -> str:
    return f"""
      <tr>
        <td style="padding:4px 28px 28px;">
          <a href="{href}"
             style="display:inline-block;padding:11px 24px;border-radius:8px;
                    background:{bg};color:#ffffff;font-size:13px;font-weight:600;
                    text-decoration:none;letter-spacing:.02em;">
            {label}
          </a>
        </td>
      </tr>"""


def _footer_row(text: str) -> str:
    return f"""
      <tr>
        <td style="padding:14px 28px;border-top:1px solid #2d2d44;
                   font-size:11px;color:#475569;text-align:center;">
          {text}
        </td>
      </tr>"""


# ── Template builders ─────────────────────────────────────────────────────────

def _alert_html(
    report_id: int,
    filename: str,
    severity: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    summary: str,
    stats: Dict[str, Any],
    app_url: str = "",
) -> str:
    color = _sev_color(severity)
    sc    = _score_color(risk_score)

    word_count    = stats.get("word_count", "—")
    finding_count = stats.get("finding_count", len(findings))
    unique_cats   = stats.get("unique_categories", "—")

    report_link = f"{app_url}/report/{report_id}" if app_url else ""

    inner = (
        _header_row(f"🚨 Safety Alert — {severity.upper()} Risk",
                    f"Melody Wings Safety · {datetime.now().strftime('%B %d, %Y at %H:%M')}",
                    color)
        + _score_info_row(filename, severity, risk_score, report_id, color, sc)
        + _stat_row_3(f"{risk_score:.0f}", "Risk Score", sc,
                      str(finding_count), "Findings",
                      str(unique_cats), "Categories")
        + _section("AI Summary", _summary_box(summary))
        + _section("Top Findings", _finding_rows(findings))
        + (_btn_row(report_link, "View Full Report →", color) if report_link else "")
        + _footer_row("This alert was generated automatically by Melody Wings Safety · Do not reply")
    )
    return _wrap(inner)


def _summary_html(
    report_id: int,
    filename: str,
    severity: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    llm_summary: str,
    rule_summary: str,
    stats: Dict[str, Any],
    app_url: str = "",
) -> str:
    color = _sev_color(severity)
    sc    = _score_color(risk_score)

    conf_stats = stats.get("confidence_stats") or {}
    avg_conf   = conf_stats.get("average", 0)
    avg_str    = f"{avg_conf*100:.0f}%" if avg_conf else "—"

    categories  = stats.get("categories") or stats.get("category_breakdown") or {}
    report_link = f"{app_url}/report/{report_id}" if app_url else ""

    inner = (
        _header_row(f"📋 Analysis Summary",
                    f"{filename} · Melody Wings Safety · {datetime.now().strftime('%B %d, %Y at %H:%M')}",
                    "#6366f1")
        + _score_info_row(filename, severity, risk_score, report_id, color, sc)
        + _stat_row_3(str(stats.get("word_count", "—")), "Words", "#e2e8f0",
                      str(stats.get("finding_count", len(findings))), "Findings",
                      avg_str, "Avg Confidence")
        + _section("AI Executive Summary", _summary_box(llm_summary))
        + _section("Rule-Based Summary",   _summary_box(rule_summary, "#94a3b8"))
        + (_section("Category Breakdown",  _cat_table(categories)) if categories else "")
        + (_btn_row(report_link, "Open Full Report →", "#6366f1") if report_link else "")
        + _footer_row(f"Generated by Melody Wings Safety · Report #{report_id} · {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    )
    return _wrap(inner)


# ── Core send function ────────────────────────────────────────────────────────

def send_email(
    subject: str,
    html_body: str,
    recipients: List[str],
    pdf_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send an HTML email via SMTP with optional PDF attachment.

    Returns:
        {"success": bool, "message": str, "recipients": list}
    """
    if not SMTP_USER or not SMTP_PASSWORD:
        msg = "SMTP not configured — set SMTP_USER and SMTP_PASSWORD in .env"
        logger.warning(msg)
        return {"success": False, "message": msg, "recipients": []}

    if not recipients:
        msg = "No recipients configured — set ALERT_RECIPIENTS in .env"
        logger.warning(msg)
        return {"success": False, "message": msg, "recipients": []}

    try:
        mime = MIMEMultipart("alternative")
        mime["Subject"] = subject
        mime["From"]    = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        mime["To"]      = ", ".join(recipients)

        mime.attach(MIMEText(html_body, "html", "utf-8"))

        # Attach PDF if provided and exists
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            pdf_filename = os.path.basename(pdf_path)
            part.add_header("Content-Disposition", f'attachment; filename="{pdf_filename}"')
            mime.attach(part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, mime.as_string())

        logger.info(f"Email sent: '{subject}' → {recipients}")
        return {"success": True, "message": "Email sent successfully", "recipients": recipients}

    except smtplib.SMTPAuthenticationError:
        msg = "SMTP authentication failed — check SMTP_USER and SMTP_PASSWORD"
        logger.error(msg)
        return {"success": False, "message": msg, "recipients": []}
    except smtplib.SMTPException as e:
        msg = f"SMTP error: {str(e)}"
        logger.error(msg)
        return {"success": False, "message": msg, "recipients": []}
    except Exception as e:
        msg = f"Unexpected email error: {str(e)}"
        logger.error(msg, exc_info=True)
        return {"success": False, "message": msg, "recipients": []}


# ── Public API ────────────────────────────────────────────────────────────────

def send_alert_email(
    report_id: int,
    filename: str,
    severity: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    summary: str,
    stats: Dict[str, Any],
    pdf_path: Optional[str] = None,
    recipients: Optional[List[str]] = None,
    app_url: str = "",
) -> Dict[str, Any]:
    """Send a red-alert email for high/critical severity reports."""
    targets = recipients or _get_recipients()
    subject = f"🚨 [{severity.upper()}] Safety Alert — {filename} (Score: {risk_score:.0f}/100)"
    html    = _alert_html(report_id, filename, severity, risk_score, findings, summary, stats, app_url)
    return send_email(subject, html, targets, pdf_path)


def send_summary_email(
    report_id: int,
    filename: str,
    severity: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    llm_summary: str,
    rule_summary: str,
    stats: Dict[str, Any],
    pdf_path: Optional[str] = None,
    recipients: Optional[List[str]] = None,
    app_url: str = "",
) -> Dict[str, Any]:
    """Send a full analysis summary email."""
    targets = recipients or _get_recipients()
    subject = f"📋 Analysis Summary — {filename} [{severity.upper()}]"
    html    = _summary_html(report_id, filename, severity, risk_score, findings, llm_summary, rule_summary, stats, app_url)
    return send_email(subject, html, targets, pdf_path)
