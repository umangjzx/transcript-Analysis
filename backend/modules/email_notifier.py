"""
Email Notifier — SMTP-based alert and summary emails.

Supports severity-tiered parent/guardian notification emails:
  - Safe     : No email sent (below threshold)
  - Low      : Low Severity Alert  — awareness notification, no action required
  - Moderate : Medium Severity Alert — parental awareness & follow-up encouraged
  - High     : High / Critical Severity Alert — immediate escalation
  - Critical : High / Critical Severity Alert — immediate escalation

Configuration (via .env or environment variables):
    SMTP_HOST        SMTP server hostname          (default: smtp.gmail.com)
    SMTP_PORT        SMTP port                     (default: 587)
    SMTP_USER        Sender email address
    SMTP_PASSWORD    Sender password / app password
    SMTP_FROM_NAME   Display name                  (default: MelodyWings Safety)
    ALERT_RECIPIENTS Comma-separated recipient list
    ALERT_SEVERITY   Minimum severity to auto-alert (default: High)
"""

import io
import os
import re
import smtplib
import logging
import tempfile
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

SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MelodyWings Safety")

def _get_recipients() -> List[str]:
    raw = os.getenv("ALERT_RECIPIENTS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]

ALERT_SEVERITY_THRESHOLD = os.getenv("ALERT_SEVERITY", "High").lower()
_SEVERITY_RANK = {"safe": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}

def should_auto_alert(severity: str) -> bool:
    """Return True if severity meets or exceeds the configured threshold."""
    return _SEVERITY_RANK.get((severity or "").lower(), 0) >= _SEVERITY_RANK.get(ALERT_SEVERITY_THRESHOLD, 3)


# ── Colour palette ────────────────────────────────────────────────────────────

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


# ── Severity helpers ──────────────────────────────────────────────────────────

def _severity_tier(severity: str) -> str:
    """Map severity string to a canonical tier: low | moderate | high | safe."""
    s = (severity or "").lower()
    if s in ("critical", "high"):
        return "high"
    if s in ("moderate", "medium"):
        return "moderate"
    if s == "low":
        return "low"
    return "safe"


# ── HTML shell ────────────────────────────────────────────────────────────────

def _wrap(inner: str) -> str:
    """Outer wrapper — white background, centred card."""
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MelodyWings Safety Alert</title>
</head>
<body style="margin:0;padding:0;background:#f3f4f6;
             font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" border="0"
       style="background:#f3f4f6;">
  <tr><td align="center" style="padding:32px 16px;">
    <table width="620" cellpadding="0" cellspacing="0" border="0"
           style="background:#ffffff;border-radius:12px;
                  box-shadow:0 4px 24px rgba(0,0,0,0.08);
                  overflow:hidden;max-width:620px;">
      {inner}
    </table>
  </td></tr>
</table>
</body></html>"""


# ── Reusable HTML blocks ──────────────────────────────────────────────────────

def _logo_row() -> str:
    return """
    <tr>
      <td style="background:#1e1b4b;padding:18px 28px 14px;text-align:center;">
        <span style="font-size:22px;font-weight:800;color:#ffffff;
                     letter-spacing:0.04em;">🎵 MelodyWings</span>
        <span style="display:block;font-size:11px;color:#a5b4fc;
                     margin-top:2px;letter-spacing:0.08em;text-transform:uppercase;">
          Safety &amp; Compliance
        </span>
      </td>
    </tr>"""


def _alert_banner(label: str, accent: str, icon: str) -> str:
    return f"""
    <tr>
      <td style="background:{accent};padding:14px 28px;text-align:center;">
        <span style="font-size:15px;font-weight:800;color:#ffffff;
                     letter-spacing:0.06em;text-transform:uppercase;">
          {icon}&nbsp;&nbsp;{label}
        </span>
      </td>
    </tr>"""


def _greeting_row() -> str:
    return """
    <tr>
      <td style="padding:28px 28px 0;">
        <p style="margin:0;font-size:15px;color:#1e293b;line-height:1.6;">
          Dear Parent/Guardian,
        </p>
      </td>
    </tr>"""


def _body_text(html_content: str) -> str:
    return f"""
    <tr>
      <td style="padding:16px 28px 0;">
        <p style="margin:0;font-size:14px;color:#334155;line-height:1.75;">
          {html_content}
        </p>
      </td>
    </tr>"""


def _divider() -> str:
    return """
    <tr>
      <td style="padding:20px 28px 0;">
        <hr style="border:none;border-top:1px solid #e2e8f0;margin:0;">
      </td>
    </tr>"""


def _section_heading(title: str, accent: str) -> str:
    return f"""
    <tr>
      <td style="padding:20px 28px 8px;">
        <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                    letter-spacing:0.1em;color:{accent};">
          {title}
        </div>
      </td>
    </tr>"""


def _content_box(text: str, bg: str = "#f8fafc", border: str = "#e2e8f0") -> str:
    safe = text.replace("\n", "<br>") if text else "Not available."
    return f"""
    <tr>
      <td style="padding:0 28px 0;">
        <div style="background:{bg};border:1px solid {border};border-radius:8px;
                    padding:16px;font-size:13px;color:#475569;line-height:1.7;">
          {safe}
        </div>
      </td>
    </tr>"""


def _key_concerns_list(findings: List[Dict[str, Any]], accent: str) -> str:
    """Render top findings as a bulleted key concerns list."""
    top = sorted(
        findings,
        key=lambda f: f.get("confidence") or f.get("max_confidence") or 0,
        reverse=True,
    )[:6]

    if not top:
        return _content_box("No specific concerns identified.")

    items = ""
    for f in top:
        cats  = f.get("categories") or ([f["category"]] if f.get("category") else [])
        cat   = ", ".join(c.replace("_", " ").title() for c in cats) or "Unknown"
        text  = (f.get("evidence") or f.get("text") or "")[:120]
        ellip = "…" if len(f.get("evidence") or f.get("text") or "") > 120 else ""
        conf  = (f.get("confidence") or f.get("max_confidence") or 0) * 100
        items += f"""
        <tr>
          <td style="padding:0 0 10px;vertical-align:top;">
            <table cellpadding="0" cellspacing="0" border="0" width="100%">
              <tr>
                <td width="6" style="vertical-align:top;padding-top:5px;">
                  <div style="width:6px;height:6px;border-radius:50%;
                              background:{accent};margin-top:1px;"></div>
                </td>
                <td style="padding-left:10px;">
                  <span style="font-size:12px;font-weight:700;color:#1e293b;
                               text-transform:uppercase;letter-spacing:0.04em;">
                    {cat}
                  </span>
                  <span style="font-size:11px;color:#94a3b8;margin-left:8px;">
                    ({conf:.0f}% confidence)
                  </span>
                  <div style="font-size:13px;color:#475569;margin-top:3px;
                              font-style:italic;">"{text}{ellip}"</div>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""

    return f"""
    <tr>
      <td style="padding:0 28px 0;">
        <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;
                    padding:16px;">
          <table cellpadding="0" cellspacing="0" border="0" width="100%">
            {items}
          </table>
        </div>
      </td>
    </tr>"""


def _actions_taken_box(actions: List[str], accent: str) -> str:
    items = "".join(
        f"""<tr>
          <td style="padding:0 0 8px;vertical-align:top;">
            <table cellpadding="0" cellspacing="0" border="0">
              <tr>
                <td width="20" style="vertical-align:top;padding-top:2px;">
                  <span style="color:{accent};font-size:14px;">&#10003;</span>
                </td>
                <td style="font-size:13px;color:#334155;line-height:1.6;">{a}</td>
              </tr>
            </table>
          </td>
        </tr>"""
        for a in actions
    )
    return f"""
    <tr>
      <td style="padding:0 28px 0;">
        <div style="background:#fff7ed;border:1px solid #fed7aa;
                    border-radius:8px;padding:16px;">
          <table cellpadding="0" cellspacing="0" border="0" width="100%">
            {items}
          </table>
        </div>
      </td>
    </tr>"""


def _meta_row(report_id: int, filename: str, risk_score: float,
              severity: str, accent: str) -> str:
    short = filename if len(filename) <= 45 else filename[:42] + "..."
    sc = _score_color(risk_score)
    return f"""
    <tr>
      <td style="padding:20px 28px 0;">
        <table cellpadding="0" cellspacing="4" border="0" width="100%">
          <tr>
            <td style="background:#f1f5f9;border-radius:8px;padding:12px 16px;
                       vertical-align:top;" width="50%">
              <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;
                          letter-spacing:0.08em;margin-bottom:4px;">Session File</div>
              <div style="font-size:13px;color:#1e293b;font-weight:600;
                          word-break:break-all;">{short}</div>
            </td>
            <td width="8"></td>
            <td style="background:#f1f5f9;border-radius:8px;padding:12px 16px;
                       vertical-align:top;" width="50%">
              <div style="font-size:10px;color:#94a3b8;text-transform:uppercase;
                          letter-spacing:0.08em;margin-bottom:4px;">Risk Score</div>
              <div>
                <span style="font-size:22px;font-weight:800;color:{sc};
                             line-height:1;">{risk_score:.0f}</span>
                <span style="font-size:12px;color:#94a3b8;">&nbsp;/ 100</span>
                &nbsp;
                <span style="display:inline-block;padding:2px 10px;border-radius:99px;
                             font-size:11px;font-weight:700;text-transform:uppercase;
                             background:{accent}18;color:{accent};
                             border:1px solid {accent}44;">
                  {severity.upper()}
                </span>
              </div>
              <div style="font-size:11px;color:#94a3b8;margin-top:4px;">
                Report #&nbsp;{report_id}
              </div>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def _report_btn(href: str, accent: str) -> str:
    if not href:
        return ""
    return f"""
    <tr>
      <td style="padding:24px 28px 0;">
        <a href="{href}"
           style="display:inline-block;padding:12px 28px;border-radius:8px;
                  background:{accent};color:#ffffff;font-size:13px;font-weight:700;
                  text-decoration:none;letter-spacing:0.02em;">
          View Full Report &rarr;
        </a>
      </td>
    </tr>"""


def _closing_row() -> str:
    return """
    <tr>
      <td style="padding:24px 28px 0;">
        <p style="margin:0;font-size:14px;color:#334155;line-height:1.75;">
          Thank you for your continued partnership in supporting a safe learning
          environment.
        </p>
      </td>
    </tr>"""


def _signature_row() -> str:
    return """
    <tr>
      <td style="padding:16px 28px 28px;">
        <p style="margin:0;font-size:14px;color:#1e293b;line-height:1.7;">
          <strong>MelodyWings Safety &amp; Compliance Team</strong>
        </p>
      </td>
    </tr>"""


def _footer_row(report_id: int) -> str:
    ts = datetime.now().strftime("%B %d, %Y at %H:%M UTC")
    return f"""
    <tr>
      <td style="padding:14px 28px;background:#f8fafc;
                 border-top:1px solid #e2e8f0;
                 font-size:11px;color:#94a3b8;text-align:center;">
        This notification was generated automatically by the MelodyWings Safety
        Monitoring System on {ts}. Report&nbsp;#{report_id}. Do&nbsp;not&nbsp;reply
        to this email.
      </td>
    </tr>"""


# ── Per-severity HTML builders ────────────────────────────────────────────────

def _low_alert_html(
    report_id: int,
    filename: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    summary: str,
    app_url: str = "",
) -> str:
    accent = _SEV_COLOR["low"]  # blue
    report_link = f"{app_url}/report/{report_id}" if app_url else ""

    inner = (
        _logo_row()
        + _alert_banner("Low Severity Alert", accent, "🔵")
        + _greeting_row()
        + _body_text(
            "We are reaching out to inform you that our automated safety monitoring "
            "system identified content during a recent MelodyWings session that met "
            "our low-level review threshold."
        )
        + _body_text(
            "The content detected does not currently indicate a significant safety "
            "concern. However, it involved topics or language that we believe should "
            "be documented and shared for awareness. These alerts are generated as "
            "part of our commitment to maintaining a safe and supportive learning "
            "environment."
        )
        + _meta_row(report_id, filename, risk_score, "Low", accent)
        + _divider()
        + _section_heading("Summary of Findings", accent)
        + _content_box(summary or "Not available.")
        + _section_heading("Key Observations", accent)
        + _key_concerns_list(findings, accent)
        + _divider()
        + _body_text(
            "At this time, <strong>no immediate action is required</strong>. This "
            "notification is being provided for transparency and to keep you informed "
            "about your learner's interactions on the platform."
        )
        + (_report_btn(report_link, accent) if report_link else "")
        + _closing_row()
        + _signature_row()
        + _footer_row(report_id)
    )
    return _wrap(inner)


def _moderate_alert_html(
    report_id: int,
    filename: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    summary: str,
    app_url: str = "",
) -> str:
    accent = _SEV_COLOR["moderate"]  # amber
    report_link = f"{app_url}/report/{report_id}" if app_url else ""

    inner = (
        _logo_row()
        + _alert_banner("Medium Severity Alert", accent, "🟡")
        + _greeting_row()
        + _body_text(
            "We are contacting you regarding a recent MelodyWings session that "
            "generated a <strong>medium-level safety alert</strong> during our "
            "routine monitoring process."
        )
        + _body_text(
            "The conversation included content that may warrant parental awareness "
            "and follow-up discussion. Examples may include repeated inappropriate "
            "language, sharing of limited personal information, boundary-related "
            "concerns, or other topics that fall outside the expected scope of "
            "educational interactions."
        )
        + _meta_row(report_id, filename, risk_score, "Moderate", accent)
        + _divider()
        + _section_heading("Summary of Findings", accent)
        + _content_box(summary or "Not available.")
        + _section_heading("Key Observations", accent)
        + _key_concerns_list(findings, accent)
        + _divider()
        + _body_text(
            "As a precaution, the interaction has been reviewed by our Safety Team "
            "and documented according to our safeguarding procedures. We encourage "
            "you to discuss the matter with your learner and contact us if you would "
            "like additional information or support."
        )
        + _body_text(
            "At this time, no immediate risk has been identified; however, we will "
            "continue to monitor future interactions as appropriate."
        )
        + (_report_btn(report_link, accent) if report_link else "")
        + _closing_row()
        + _signature_row()
        + _footer_row(report_id)
    )
    return _wrap(inner)


def _high_alert_html(
    report_id: int,
    filename: str,
    severity: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    summary: str,
    app_url: str = "",
) -> str:
    accent = _SEV_COLOR.get(severity.lower(), _SEV_COLOR["high"])  # red
    report_link = f"{app_url}/report/{report_id}" if app_url else ""

    actions = [
        "The interaction has been escalated for immediate safety review.",
        "Relevant session records have been secured and documented.",
        "Additional monitoring and protective measures may be implemented.",
        "Further action will be taken in accordance with MelodyWings safeguarding procedures.",
    ]

    inner = (
        _logo_row()
        + _alert_banner("High / Critical Severity Alert", accent, "🚨")
        + _greeting_row()
        + _body_text(
            "We are writing to inform you that a recent MelodyWings session generated "
            "a <strong>high-priority safety alert</strong> and has been escalated for "
            "immediate review by our Safety Team."
        )
        + _body_text(
            "The conversation contained content that may represent a significant safety "
            "concern requiring prompt attention. Depending on the circumstances, this "
            "may include the disclosure of sensitive personal information, inappropriate "
            "sexual content, grooming indicators, threats, self-harm discussions, "
            "coercive behavior, or other serious violations of our safeguarding policies."
        )
        + _meta_row(report_id, filename, risk_score, severity, accent)
        + _divider()
        + _section_heading("Summary of Findings", accent)
        + _content_box(summary or "Not available.")
        + _section_heading("Key Observations", accent)
        + _key_concerns_list(findings, accent)
        + _divider()
        + _section_heading("Actions Taken by MelodyWings", accent)
        + _actions_taken_box(actions, accent)
        + _divider()
        + _body_text(
            "We recommend <strong>reviewing this matter with your learner as soon as "
            "possible</strong>. A member of our Safety Team may contact you if "
            "additional follow-up is required."
        )
        + _body_text(
            "<strong>The safety and well-being of our learners remain our highest "
            "priority.</strong>"
        )
        + (_report_btn(report_link, accent) if report_link else "")
        + _signature_row()
        + _footer_row(report_id)
    )
    return _wrap(inner)


# ── Summary email (internal / on-demand) ─────────────────────────────────────

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
    accent = _sev_color(severity)
    sc = _score_color(risk_score)
    report_link = f"{app_url}/report/{report_id}" if app_url else ""

    conf_stats = stats.get("confidence_stats") or {}
    avg_conf   = conf_stats.get("average", 0)
    avg_str    = f"{avg_conf*100:.0f}%" if avg_conf else "—"
    categories = stats.get("categories") or stats.get("category_breakdown") or {}

    # Category table
    cat_rows = ""
    for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
        cat_rows += f"""
        <tr style="border-bottom:1px solid #e2e8f0;">
          <td style="padding:8px 12px;font-size:13px;color:#334155;">
            {cat.replace('_',' ').title()}
          </td>
          <td style="padding:8px 12px;font-size:13px;font-weight:700;
                     color:#1e293b;text-align:right;">{count}</td>
        </tr>"""

    cat_section = ""
    if cat_rows:
        cat_section = f"""
        <tr>
          <td style="padding:20px 28px 0;">
            <div style="font-size:11px;font-weight:700;text-transform:uppercase;
                        letter-spacing:0.1em;color:#6366f1;margin-bottom:8px;">
              Category Breakdown
            </div>
            <table cellpadding="0" cellspacing="0" border="0" width="100%"
                   style="background:#f8fafc;border:1px solid #e2e8f0;
                          border-radius:8px;overflow:hidden;">
              <tr style="background:#f1f5f9;">
                <th style="padding:8px 12px;font-size:10px;text-align:left;
                           color:#64748b;text-transform:uppercase;
                           letter-spacing:0.08em;font-weight:600;">Category</th>
                <th style="padding:8px 12px;font-size:10px;text-align:right;
                           color:#64748b;text-transform:uppercase;
                           letter-spacing:0.08em;font-weight:600;">Count</th>
              </tr>
              {cat_rows}
            </table>
          </td>
        </tr>"""

    inner = (
        _logo_row()
        + _alert_banner("Analysis Summary Report", "#6366f1", "📋")
        + _greeting_row()
        + _meta_row(report_id, filename, risk_score, severity, accent)
        + f"""
        <tr>
          <td style="padding:12px 28px 0;">
            <table cellpadding="0" cellspacing="4" border="0" width="100%">
              <tr>
                <td style="background:#f1f5f9;border-radius:8px;padding:12px 16px;
                           text-align:center;" width="33%">
                  <div style="font-size:22px;font-weight:800;color:{sc};">
                    {risk_score:.0f}
                  </div>
                  <div style="font-size:11px;color:#94a3b8;margin-top:2px;">
                    Risk Score
                  </div>
                </td>
                <td width="6"></td>
                <td style="background:#f1f5f9;border-radius:8px;padding:12px 16px;
                           text-align:center;" width="33%">
                  <div style="font-size:22px;font-weight:800;color:#1e293b;">
                    {stats.get("finding_count", len(findings))}
                  </div>
                  <div style="font-size:11px;color:#94a3b8;margin-top:2px;">
                    Findings
                  </div>
                </td>
                <td width="6"></td>
                <td style="background:#f1f5f9;border-radius:8px;padding:12px 16px;
                           text-align:center;" width="33%">
                  <div style="font-size:22px;font-weight:800;color:#1e293b;">
                    {avg_str}
                  </div>
                  <div style="font-size:11px;color:#94a3b8;margin-top:2px;">
                    Avg Confidence
                  </div>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""
        + _divider()
        + _section_heading("AI Executive Summary", "#6366f1")
        + _content_box(llm_summary or "Not available.")
        + _section_heading("Rule-Based Summary", "#6366f1")
        + _content_box(rule_summary or "Not available.")
        + cat_section
        + (_report_btn(report_link, "#6366f1") if report_link else "")
        + _closing_row()
        + _signature_row()
        + _footer_row(report_id)
    )
    return _wrap(inner)


# ── Core send function ────────────────────────────────────────────────────────

def send_email(
    subject: str,
    html_body: str,
    recipients: List[str],
    pdf_path: Optional[str] = None,
    transcript: Optional[str] = None,
    transcript_filename: str = "session_transcript.txt",
) -> Dict[str, Any]:
    """
    Send an HTML email via SMTP with optional PDF and transcript attachments.

    Args:
        subject:              Email subject line.
        html_body:            HTML body content.
        recipients:           List of recipient email addresses.
        pdf_path:             Optional path to a PDF report file to attach.
        transcript:           Optional raw transcript text to attach as .txt.
        transcript_filename:  Filename for the transcript attachment.

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
        # Use "mixed" so we can attach files alongside the HTML body
        mime = MIMEMultipart("mixed")
        mime["Subject"] = subject
        mime["From"]    = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        mime["To"]      = ", ".join(recipients)

        # Wrap body in "alternative" sub-part (plain-text fallback + HTML)
        alt = MIMEMultipart("alternative")
        plain_text = re.sub(r"<[^>]+>", "", html_body)  # strip tags for plain fallback
        alt.attach(MIMEText(plain_text, "plain", "utf-8"))
        alt.attach(MIMEText(html_body,  "html",  "utf-8"))
        mime.attach(alt)

        # ── Attachment 1: PDF report ─────────────────────────────────
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "pdf")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            pdf_fname = os.path.basename(pdf_path)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{pdf_fname}"',
            )
            mime.attach(part)

        # ── Attachment 2: Meeting transcript (.txt) ──────────────────
        if transcript and transcript.strip():
            # Build a nicely formatted transcript file
            transcript_content = _build_transcript_attachment(
                transcript, transcript_filename
            )
            txt_part = MIMEText(transcript_content, "plain", "utf-8")
            safe_fname = re.sub(r"[^\w\-. ]", "_", transcript_filename)
            txt_part.add_header(
                "Content-Disposition",
                f'attachment; filename="{safe_fname}"',
            )
            mime.attach(txt_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, mime.as_string())

        attach_note = []
        if pdf_path and os.path.exists(pdf_path):
            attach_note.append("PDF")
        if transcript and transcript.strip():
            attach_note.append("transcript")
        attachment_str = f" (+{', '.join(attach_note)})" if attach_note else ""

        logger.info(f"Email sent{attachment_str}: '{subject}' → {recipients}")
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


def _build_transcript_attachment(transcript: str, filename: str) -> str:
    """
    Format the raw transcript into a clean, readable .txt attachment.
    Includes a header block with metadata.
    """
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    border  = "=" * 60

    header = (
        f"{border}\n"
        f"  MELODYWINGS — MEETING TRANSCRIPT\n"
        f"  Generated : {now_str}\n"
        f"  File      : {filename}\n"
        f"  CONFIDENTIAL — For safeguarding use only\n"
        f"{border}\n\n"
    )

    # Lightly clean the transcript: strip excessive blank lines
    cleaned = re.sub(r"\n{3,}", "\n\n", transcript.strip())

    footer = (
        f"\n\n{border}\n"
        f"  End of transcript\n"
        f"  This document was automatically generated by the\n"
        f"  MelodyWings Safety Monitoring System.\n"
        f"{border}\n"
    )

    return header + cleaned + footer


# ── Sanitisation ──────────────────────────────────────────────────────────────

def _sanitize_for_subject(text: str) -> str:
    """Strip newlines/control chars to prevent header injection."""
    sanitized = re.sub(r'[\r\n\x00-\x1f\x7f]', '', text)
    return sanitized[:200]


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
    transcript: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Send a severity-appropriate alert email to parents/guardians.

    Routes to the correct template based on severity tier:
      Low      → Low Severity Alert
      Moderate → Medium Severity Alert
      High     → High / Critical Severity Alert
      Critical → High / Critical Severity Alert

    If transcript is provided it is attached as a .txt file.
    """
    targets = recipients or _get_recipients()
    safe_filename = _sanitize_for_subject(filename)
    safe_severity = _sanitize_for_subject(severity)
    tier = _severity_tier(severity)

    # Build a clean transcript filename based on the session filename
    base_name = os.path.splitext(filename)[0] if filename else f"report_{report_id}"
    transcript_fname = f"{base_name}_transcript.txt"

    if tier == "low":
        subject = f"[LOW SEVERITY ALERT] MelodyWings Safety Notification — {safe_filename}"
        html = _low_alert_html(report_id, filename, risk_score, findings, summary, app_url)

    elif tier == "moderate":
        subject = f"[MEDIUM SEVERITY ALERT] MelodyWings Safety Notification — {safe_filename}"
        html = _moderate_alert_html(report_id, filename, risk_score, findings, summary, app_url)

    else:  # high / critical
        subject = (
            f"[{safe_severity.upper()} SEVERITY ALERT] 🚨 MelodyWings Safety Notification "
            f"— {safe_filename} (Score: {risk_score:.0f}/100)"
        )
        html = _high_alert_html(report_id, filename, severity, risk_score, findings, summary, app_url)

    return send_email(
        subject, html, targets,
        pdf_path=pdf_path,
        transcript=transcript,
        transcript_filename=transcript_fname,
    )


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
    transcript: Optional[str] = None,
) -> Dict[str, Any]:
    """Send a full analysis summary email (internal / on-demand use).

    If transcript is provided it is attached as a .txt file.
    """
    targets = recipients or _get_recipients()
    safe_filename = _sanitize_for_subject(filename)
    safe_severity = _sanitize_for_subject(severity)
    subject = f"📋 Analysis Summary — {safe_filename} [{safe_severity.upper()}]"

    base_name = os.path.splitext(filename)[0] if filename else f"report_{report_id}"
    transcript_fname = f"{base_name}_transcript.txt"

    html = _summary_html(
        report_id, filename, severity, risk_score,
        findings, llm_summary, rule_summary, stats, app_url,
    )
    return send_email(
        subject, html, targets,
        pdf_path=pdf_path,
        transcript=transcript,
        transcript_filename=transcript_fname,
    )
