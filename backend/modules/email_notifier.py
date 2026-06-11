"""
Email Notifier — MelodyWings Safety Platform
=============================================

Redesigned email system with two separate report tracks:

  PARENT TRACK  (send_alert_email)
  ─────────────────────────────────
  Clean, friendly, parent-facing emails. No internal system data,
  no raw scores, no technical metadata. Tier-appropriate content:
    Safe     → Routine session report, no concerns
    Low      → Awareness notification, no action required
    Moderate → Parental awareness & follow-up encouraged
    High     → Immediate escalation with clear next steps
    Critical → Same as High, maximum urgency

  ADMIN TRACK  (send_admin_report / send_summary_email)
  ──────────────────────────────────────────────────────
  Full-detail internal report for staff monitoring. Includes:
  complete transcript, AI analysis, risk indicators, session
  metrics, confidence stats, category breakdown, and metadata.

Design System
─────────────
  All templates share a unified token set:
    Brand indigo  #5B6BF8  (primary, CTAs, accents)
    Off-white     #FAFAFA  (email background)
    White card    #FFFFFF  (content card)
    Text primary  #0F172A  (headings)
    Text body     #374151  (body copy)
    Text muted    #6B7280  (captions, labels)
    Border        #E5E7EB  (dividers, card borders)
    Success       #10B981  green
    Warning       #F59E0B  amber
    Danger        #EF4444  red
    Info          #3B82F6  blue

Configuration (via .env or environment variables):
    SMTP_HOST        SMTP server hostname          (default: smtp.gmail.com)
    SMTP_PORT        SMTP port                     (default: 587)
    SMTP_USER        Sender email address
    SMTP_PASSWORD    Sender password / app password
    SMTP_FROM_NAME   Display name                  (default: MelodyWings Safety)
    ALERT_RECIPIENTS Comma-separated recipient list
    ALERT_SEVERITY   Minimum severity to auto-alert (default: High)
"""

import os
import re
import smtplib
import logging
import tempfile
from dotenv import load_dotenv
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
from email import encoders
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

load_dotenv(override=True)

# ── Logo — CID inline attachment ──────────────────────────────────────────────
# Stored in backend/static/logo.png — copied from admin-next/public/unnamed.png
_LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "static", "logo.png")
_LOGO_CID  = "melodywings_logo"   # referenced as cid:melodywings_logo in HTML

def _logo_mime_part() -> Optional[MIMEImage]:
    """Return a MIMEImage part for the logo, or None if the file is missing."""
    try:
        with open(_LOGO_PATH, "rb") as fh:
            img = MIMEImage(fh.read(), _subtype="png")
        img.add_header("Content-ID", f"<{_LOGO_CID}>")
        img.add_header("Content-Disposition", "inline", filename="logo.png")
        return img
    except Exception:
        logger.debug("Logo file not found at %s — header will use text fallback", _LOGO_PATH)
        return None

# ── SMTP Configuration ────────────────────────────────────────────────────────

SMTP_HOST      = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT      = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER      = os.getenv("SMTP_USER", "")
SMTP_PASSWORD  = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "MelodyWings Safety")

# Admin recipients — full-detail internal reports
def _get_recipients() -> List[str]:
    raw = os.getenv("ALERT_RECIPIENTS", "")
    return [r.strip() for r in raw.split(",") if r.strip()]

# Parent recipients — simplified parent-facing emails
PARENT_FROM_NAME = os.getenv("PARENT_FROM_NAME", "MelodyWings Safety Team")

def _get_parent_recipients() -> List[str]:
    raw = os.getenv("PARENT_RECIPIENTS", "")
    recipients = [r.strip() for r in raw.split(",") if r.strip()]
    # Fall back to admin recipients if no parent list is configured
    return recipients if recipients else _get_recipients()

ALERT_SEVERITY_THRESHOLD        = os.getenv("ALERT_SEVERITY", "High").lower()
PARENT_ALERT_SEVERITY_THRESHOLD = os.getenv("PARENT_ALERT_SEVERITY", "Low").lower()
_SEVERITY_RANK = {"safe": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}

def should_auto_alert(severity: str) -> bool:
    """Return True if severity meets or exceeds the admin alert threshold."""
    return _SEVERITY_RANK.get((severity or "").lower(), 0) >= _SEVERITY_RANK.get(ALERT_SEVERITY_THRESHOLD, 3)

def should_parent_alert(severity: str) -> bool:
    """Return True if severity meets or exceeds the parent alert threshold."""
    return _SEVERITY_RANK.get((severity or "").lower(), 0) >= _SEVERITY_RANK.get(PARENT_ALERT_SEVERITY_THRESHOLD, 1)


# ── Design Tokens ─────────────────────────────────────────────────────────────

_T = {
    "brand":      "#5B6BF8",   # indigo — primary brand
    "brand_dark": "#4655E8",   # indigo darker for hover
    "bg":         "#F3F4F6",   # page background
    "card":       "#FFFFFF",   # card surface
    "text":       "#0F172A",   # primary text
    "body":       "#374151",   # body text
    "muted":      "#6B7280",   # captions / labels
    "border":     "#E5E7EB",   # borders / dividers
    "safe":       "#10B981",   # green
    "low":        "#3B82F6",   # blue
    "moderate":   "#F59E0B",   # amber
    "high":       "#EF4444",   # red
    "critical":   "#DC2626",   # deep red
    "header_bg":  "#0F172A",   # email header background
    "footer_bg":  "#F9FAFB",   # footer background
}

_SEV_COLOR = {
    "safe":     _T["safe"],
    "low":      _T["low"],
    "moderate": _T["moderate"],
    "medium":   _T["moderate"],
    "high":     _T["high"],
    "critical": _T["critical"],
}

def _sev_color(severity: str) -> str:
    return _SEV_COLOR.get((severity or "").lower(), _T["muted"])

def _score_color(score: float) -> str:
    if score >= 80: return _T["critical"]
    if score >= 61: return _T["high"]
    if score >= 41: return _T["moderate"]
    if score >= 21: return _T["low"]
    return _T["safe"]

def _severity_tier(severity: str) -> str:
    s = (severity or "").lower()
    if s in ("critical", "high"):   return "high"
    if s in ("moderate", "medium"): return "moderate"
    if s == "low":                  return "low"
    return "safe"

def _severity_label(severity: str) -> str:
    return {
        "safe":     "No Concerns",
        "low":      "Low Severity",
        "moderate": "Medium Severity",
        "medium":   "Medium Severity",
        "high":     "High Severity",
        "critical": "Critical Severity",
    }.get((severity or "").lower(), severity.title())

def _severity_icon(severity: str) -> str:
    return {
        "safe":     "✓",
        "low":      "ℹ",
        "moderate": "⚠",
        "medium":   "⚠",
        "high":     "!",
        "critical": "!!",
    }.get((severity or "").lower(), "•")


# ── Summary condensing ────────────────────────────────────────────────────────

def _condense_summary(summary: str, tier: str, max_chars: int = 600) -> str:
    """Extract a tier-appropriate excerpt from the full rule/LLM summary."""
    if not summary or not summary.strip():
        return "No summary available."

    text = summary.strip()

    def _strip_dividers(s: str) -> str:
        """Remove lines that are purely decorative dividers (─, ═, -, etc.)."""
        lines = s.split("\n")
        cleaned = [
            ln for ln in lines
            if not re.match(r"^\s*[─═\-_~]{4,}\s*$", ln)
        ]
        return "\n".join(cleaned).strip()

    def _extract_section(label: str) -> str:
        pattern = re.compile(
            rf"(?:SECTION\s+\d+\s+[—–\-]+\s+)?{re.escape(label)}\s*[—–\-]*\n+(.*?)(?=\nSECTION|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        m = pattern.search(text)
        if not m:
            return ""
        raw = m.group(1).strip()
        return _strip_dividers(raw)[:max_chars]

    exec_sum = _extract_section("EXECUTIVE SUMMARY")
    key_con  = _extract_section("KEY CONCERNS")
    risk_ass = _extract_section("RISK ASSESSMENT")

    if tier == "safe":
        base = exec_sum or text
        first = base.split(".")[0].strip()
        return (first + ".") if first else base[:300]

    if tier == "low":
        return (exec_sum or text)[:max_chars]

    if tier == "moderate":
        parts = []
        if exec_sum:  parts.append(exec_sum[:350])
        if key_con:   parts.append("Key concerns identified:\n" + key_con[:250])
        return "\n\n".join(parts) if parts else text[:max_chars]

    # high / critical
    parts = []
    if exec_sum:  parts.append(exec_sum[:300])
    if key_con:   parts.append("Key concerns:\n" + key_con[:250])
    if risk_ass:  parts.append("Risk assessment:\n" + risk_ass[:200])
    return "\n\n".join(parts) if parts else text[:max_chars]


# ════════════════════════════════════════════════════════════════════════════════
# UNIFIED DESIGN SYSTEM COMPONENTS
# ════════════════════════════════════════════════════════════════════════════════

def _ds_wrap(inner: str, preview_text: str = "") -> str:
    """Outer shell — off-white background, centred card, max-width 600px."""
    preview = f'<div style="display:none;max-height:0;overflow:hidden;mso-hide:all;">{preview_text}&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌&nbsp;‌</div>' if preview_text else ""
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <title>MelodyWings Safety</title>
  <!--[if mso]><xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml><![endif]-->
  <style>
    @media (prefers-color-scheme: dark) {{
      .email-bg   {{ background-color: #1a1a2e !important; }}
      .email-card {{ background-color: #16213e !important; border-color: #2d3748 !important; }}
      .email-header {{ background-color: #0d0d1a !important; }}
      .email-footer {{ background-color: #0d1117 !important; }}
      .text-primary  {{ color: #f1f5f9 !important; }}
      .text-body     {{ color: #cbd5e1 !important; }}
      .text-muted    {{ color: #94a3b8 !important; }}
      .stat-card     {{ background-color: #1e293b !important; border-color: #334155 !important; }}
      .content-box   {{ background-color: #1e293b !important; border-color: #334155 !important; }}
      .divider-line  {{ border-color: #334155 !important; }}
    }}
    @media only screen and (max-width: 600px) {{
      .email-card  {{ border-radius: 0 !important; }}
      .email-pad   {{ padding: 24px 20px !important; }}
      .stat-grid td {{ display: block !important; width: 100% !important; padding: 8px 0 !important; }}
    }}
  </style>
</head>
<body class="email-bg" style="margin:0;padding:0;background-color:{_T['bg']};
     font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif;
     -webkit-font-smoothing:antialiased;">
  {preview}
  <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
    <tr>
      <td align="center" style="padding:40px 16px;">
        <table class="email-card" width="600" cellpadding="0" cellspacing="0" border="0"
               role="presentation"
               style="background:{_T['card']};border-radius:16px;
                      border:1px solid {_T['border']};
                      max-width:600px;width:100%;
                      box-shadow:0 1px 3px rgba(0,0,0,0.08),0 8px 24px rgba(0,0,0,0.06);">
          {inner}
        </table>
        <table width="600" cellpadding="0" cellspacing="0" border="0" style="max-width:600px;width:100%;">
          <tr>
            <td style="padding:24px 0 0;text-align:center;
                       font-size:11px;color:{_T['muted']};line-height:1.6;">
              &copy; {datetime.now().year} MelodyWings. All rights reserved.<br>
              <a href="#" style="color:{_T['muted']};text-decoration:none;">Privacy Policy</a>
              &nbsp;&middot;&nbsp;
              <a href="#" style="color:{_T['muted']};text-decoration:none;">Terms of Service</a>
              &nbsp;&middot;&nbsp;
              <a href="#" style="color:{_T['muted']};text-decoration:none;">Unsubscribe</a>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _ds_header(subtitle: str = "Safety Monitoring") -> str:
    """Unified email header — dark background, logo image (CID inline), subtitle."""
    return f"""
    <tr>
      <td class="email-header"
          style="background:{_T['header_bg']};padding:28px 40px;border-radius:16px 16px 0 0;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
          <tr>
            <td style="vertical-align:middle;">
              <!--[if !vml]-->
              <img src="cid:{_LOGO_CID}"
                   alt="MelodyWings"
                   width="48" height="48"
                   style="display:inline-block;vertical-align:middle;
                          border-radius:10px;margin-right:14px;
                          border:0;outline:none;text-decoration:none;">
              <!--[if vml]><v:image xmlns:v="urn:schemas-microsoft-com:vml"
                src="cid:{_LOGO_CID}" style="width:48px;height:48px;" /></[if]-->
              <span style="display:inline-block;vertical-align:middle;">
                <span style="display:block;font-size:20px;font-weight:700;
                             color:#FFFFFF;letter-spacing:-0.3px;line-height:1.2;">
                  MelodyWings
                </span>
                <span style="display:block;font-size:11px;color:#94A3B8;
                             margin-top:3px;letter-spacing:0.8px;
                             text-transform:uppercase;">
                  {subtitle}
                </span>
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def _ds_severity_badge(severity: str) -> str:
    """Full-width severity indicator strip below the header."""
    color = _sev_color(severity)
    label = _severity_label(severity)
    icon  = _severity_icon(severity)
    return f"""
    <tr>
      <td style="background:{color};padding:14px 40px;">
        <table width="100%" cellpadding="0" cellspacing="0" border="0" role="presentation">
          <tr>
            <td style="vertical-align:middle;">
              <span style="display:inline-block;width:22px;height:22px;border-radius:50%;
                           background:rgba(255,255,255,0.25);text-align:center;
                           font-size:12px;font-weight:900;color:#FFFFFF;
                           line-height:22px;margin-right:10px;vertical-align:middle;">
                {icon}
              </span>
              <span style="font-size:13px;font-weight:700;color:#FFFFFF;
                           letter-spacing:0.8px;text-transform:uppercase;
                           vertical-align:middle;">
                {label}
              </span>
            </td>
          </tr>
        </table>
      </td>
    </tr>"""


def _ds_body_open() -> str:
    """Opens the padded body section."""
    return """
    <tr>
      <td class="email-pad" style="padding:36px 40px 0;">"""


def _ds_body_close() -> str:
    return """
      </td>
    </tr>"""


def _ds_greeting(name: str = "Parent/Guardian") -> str:
    return f'<p style="margin:0 0 20px;font-size:15px;color:{_T["text"]};font-weight:600;line-height:1.5;">Dear {name},</p>'


def _ds_paragraph(text: str, margin_bottom: str = "16px") -> str:
    return f'<p style="margin:0 0 {margin_bottom};font-size:14px;color:{_T["body"]};line-height:1.75;">{text}</p>'


def _ds_divider() -> str:
    return f"""
    <tr>
      <td style="padding:0 40px;">
        <hr class="divider-line" style="border:none;border-top:1px solid {_T['border']};margin:28px 0 0;">
      </td>
    </tr>"""


def _ds_section_label(title: str, color: str = None) -> str:
    c = color or _T["muted"]
    return f'<p style="margin:28px 0 10px;font-size:11px;font-weight:700;color:{c};letter-spacing:1px;text-transform:uppercase;">{title}</p>'


def _ds_content_box(text: str, bg: str = None, border: str = None) -> str:
    bg     = bg or "#F8FAFC"
    border = border or _T["border"]
    raw    = text or "Not available."
    # Strip decorative divider lines (─, ═, -, etc.) before rendering
    lines  = raw.split("\n")
    lines  = [ln for ln in lines if not re.match(r"^\s*[─═\-_~]{4,}\s*$", ln)]
    safe   = "<br>".join(lines)
    return f"""<div class="content-box"
                    style="background:{bg};border:1px solid {border};border-radius:10px;
                           padding:18px 20px;font-size:13px;color:{_T['body']};
                           line-height:1.75;margin-bottom:0;">
      {safe}
    </div>"""


def _ds_stat_row(stats: List[Dict[str, str]]) -> str:
    """
    Render a row of stat tiles. Each stat dict: {value, label, color (opt)}.
    Supports 2 or 3 tiles.
    """
    cols = len(stats)
    col_width = "50%" if cols == 2 else "33%"
    cells = ""
    for i, s in enumerate(stats):
        spacer = '<td width="8"></td>' if i < cols - 1 else ""
        color = s.get("color", _T["text"])
        cells += f"""
        <td class="stat-card" width="{col_width}"
            style="background:#F8FAFC;border:1px solid {_T['border']};border-radius:10px;
                   padding:16px 14px;text-align:center;vertical-align:middle;">
          <div style="font-size:24px;font-weight:800;color:{color};line-height:1;
                      letter-spacing:-0.5px;">{s['value']}</div>
          <div style="font-size:11px;color:{_T['muted']};margin-top:5px;
                      text-transform:uppercase;letter-spacing:0.5px;">{s['label']}</div>
        </td>
        {spacer}"""
    return f"""
    <table class="stat-grid" cellpadding="0" cellspacing="0" border="0"
           width="100%" role="presentation" style="margin:0 0 0;">
      <tr>{cells}</tr>
    </table>"""


def _ds_bullet_list(items: List[str], color: str = None) -> str:
    """Render a clean bullet list."""
    c = color or _T["brand"]
    rows = ""
    for item in items:
        rows += f"""
        <tr>
          <td style="padding:0 0 10px;vertical-align:top;width:18px;">
            <span style="display:inline-block;width:6px;height:6px;border-radius:50%;
                         background:{c};margin-top:7px;"></span>
          </td>
          <td style="padding:0 0 10px;">
            <span style="font-size:13px;color:{_T['body']};line-height:1.65;">{item}</span>
          </td>
        </tr>"""
    return f"""<table cellpadding="0" cellspacing="0" border="0" width="100%" role="presentation">
      {rows}
    </table>"""


def _ds_check_list(items: List[str], color: str = None) -> str:
    """Render a list with checkmark icons."""
    c = color or _T["safe"]
    rows = ""
    for item in items:
        rows += f"""
        <tr>
          <td style="padding:0 0 10px;vertical-align:top;width:22px;">
            <span style="display:inline-block;width:16px;height:16px;border-radius:50%;
                         background:{c};text-align:center;line-height:16px;
                         font-size:9px;font-weight:900;color:#FFFFFF;">✓</span>
          </td>
          <td style="padding:0 0 10px;">
            <span style="font-size:13px;color:{_T['body']};line-height:1.65;">{item}</span>
          </td>
        </tr>"""
    return f"""<table cellpadding="0" cellspacing="0" border="0" width="100%" role="presentation">
      {rows}
    </table>"""


def _ds_cta_button(label: str, href: str, color: str = None) -> str:
    """Single primary CTA button."""
    c = color or _T["brand"]
    if not href:
        return ""
    return f"""
    <tr>
      <td style="padding:32px 40px 0;text-align:left;">
        <a href="{href}" target="_blank"
           style="display:inline-block;padding:13px 28px;background:{c};
                  color:#FFFFFF;font-size:13px;font-weight:600;
                  text-decoration:none;border-radius:8px;
                  letter-spacing:0.2px;line-height:1;">
          {label}&nbsp; →
        </a>
      </td>
    </tr>"""


def _ds_footer(report_id: int = 0, show_report_id: bool = True) -> str:
    ts = datetime.now().strftime("%B %d, %Y at %H:%M UTC")
    rid_line = f"&nbsp;&middot;&nbsp; Report #{report_id}" if show_report_id and report_id else ""
    return f"""
    <tr>
      <td class="email-footer"
          style="padding:24px 40px;background:{_T['footer_bg']};
                 border-top:1px solid {_T['border']};border-radius:0 0 16px 16px;">
        <p style="margin:0;font-size:11px;color:{_T['muted']};line-height:1.6;text-align:center;">
          Sent automatically by the MelodyWings Safety Monitoring System
          {rid_line}<br>
          {ts} &nbsp;&middot;&nbsp; Do not reply to this email<br>
          <a href="mailto:support@melodywings.com"
             style="color:{_T['muted']};text-decoration:underline;">support@melodywings.com</a>
          &nbsp;&middot;&nbsp;
          <a href="#" style="color:{_T['muted']};text-decoration:underline;">melodywings.com</a>
        </p>
      </td>
    </tr>"""


def _ds_signature() -> str:
    return f"""
    <tr>
      <td style="padding:28px 40px 0;">
        <p style="margin:0;font-size:14px;color:{_T['body']};line-height:1.7;">
          Warm regards,<br>
          <strong style="color:{_T['text']};">The MelodyWings Safety Team</strong>
        </p>
      </td>
    </tr>"""


def _ds_spacer(height: int = 24) -> str:
    return f'<tr><td style="height:{height}px;line-height:{height}px;font-size:1px;">&nbsp;</td></tr>'


# ════════════════════════════════════════════════════════════════════════════════
# PARENT EMAIL TEMPLATES  (simplified, friendly, no technical data)
# ════════════════════════════════════════════════════════════════════════════════

def _parent_safe_html(
    report_id: int,
    filename: str,
    app_url: str = "",
) -> str:
    report_link = f"{app_url}/report/{report_id}" if app_url else ""
    inner = (
        _ds_header()
        + _ds_severity_badge("safe")
        + f"""
        <tr>
          <td class="email-pad" style="padding:36px 40px 0;">
            {_ds_greeting()}
            {_ds_paragraph(
                "We completed a routine safety review of a recent MelodyWings session "
                "and wanted to let you know — everything looks good."
            )}
            {_ds_paragraph(
                "No safety concerns were identified. The session appeared to be within "
                "normal educational boundaries, and your learner's interactions were "
                "appropriate throughout."
            )}
          </td>
        </tr>"""
        + _ds_divider()
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_section_label("Session Summary", _T['safe'])}
            {_ds_content_box(
                "✓ &nbsp;Session reviewed — no concerns detected.<br>"
                "✓ &nbsp;Conversation stayed within expected educational scope.<br>"
                "✓ &nbsp;This report is part of our standard safeguarding process.",
                bg="#F0FDF4", border="#A7F3D0"
            )}
          </td>
        </tr>"""
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_paragraph(
                "No action is required on your part. We send these reports to keep you "
                "fully informed about your learner's sessions on our platform.",
                margin_bottom="0"
            )}
          </td>
        </tr>"""
        + (_ds_cta_button("View Session Report", report_link, _T["safe"]) if report_link else "")
        + _ds_signature()
        + _ds_spacer(32)
        + _ds_footer(report_id)
    )
    return _ds_wrap(inner, preview_text="Session reviewed — no concerns detected.")


def _parent_low_html(
    report_id: int,
    filename: str,
    summary: str,
    findings: List[Dict[str, Any]],
    app_url: str = "",
) -> str:
    report_link = f"{app_url}/report/{report_id}" if app_url else ""

    # Build 3–5 simple key observations
    observations = _build_parent_observations(findings, max_items=5)

    inner = (
        _ds_header()
        + _ds_severity_badge("low")
        + f"""
        <tr>
          <td class="email-pad" style="padding:36px 40px 0;">
            {_ds_greeting()}
            {_ds_paragraph(
                "We completed a routine safety review of a recent MelodyWings session "
                "and wanted to share a brief awareness notification."
            )}
            {_ds_paragraph(
                "Our system identified some content that meets our low-level monitoring "
                "threshold. This does not indicate a significant safety concern — it is "
                "being shared as part of our commitment to full transparency."
            )}
          </td>
        </tr>"""
        + _ds_divider()
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_section_label("Session Overview", _T['low'])}
            {_ds_content_box(summary or "Session reviewed with minor observations noted.")}
          </td>
        </tr>"""
        + (f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Key Observations", _T['low'])}
            {_ds_content_box(observations)}
          </td>
        </tr>""" if observations else "")
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_section_label("Suggested Next Steps", _T['low'])}
            {_ds_content_box(
                "· &nbsp;No immediate action is required.<br>"
                "· &nbsp;You may wish to check in with your learner about their sessions.<br>"
                "· &nbsp;Contact us if you have any questions or concerns.",
                bg="#EFF6FF", border="#BFDBFE"
            )}
          </td>
        </tr>"""
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_paragraph(
                "We will continue to monitor future sessions as part of our standard "
                "safeguarding procedures.",
                margin_bottom="0"
            )}
          </td>
        </tr>"""
        + (_ds_cta_button("View Session Report", report_link, _T["low"]) if report_link else "")
        + _ds_signature()
        + _ds_spacer(32)
        + _ds_footer(report_id)
    )
    return _ds_wrap(inner, preview_text="A routine session review is ready for you.")


def _parent_moderate_html(
    report_id: int,
    filename: str,
    summary: str,
    findings: List[Dict[str, Any]],
    app_url: str = "",
) -> str:
    report_link = f"{app_url}/report/{report_id}" if app_url else ""
    observations = _build_parent_observations(findings, max_items=5)

    inner = (
        _ds_header()
        + _ds_severity_badge("moderate")
        + f"""
        <tr>
          <td class="email-pad" style="padding:36px 40px 0;">
            {_ds_greeting()}
            {_ds_paragraph(
                "We are reaching out regarding a recent MelodyWings session that "
                "generated a <strong>medium-level safety notification</strong>."
            )}
            {_ds_paragraph(
                "The session included content that may benefit from a brief follow-up "
                "conversation with your learner. This could involve topics or language "
                "that fall outside the normal scope of educational interactions."
            )}
          </td>
        </tr>"""
        + _ds_divider()
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_section_label("Session Overview", _T['moderate'])}
            {_ds_content_box(summary or "Content was identified that warrants parental awareness.")}
          </td>
        </tr>"""
        + (f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Key Findings", _T['moderate'])}
            {_ds_content_box(observations)}
          </td>
        </tr>""" if observations else "")
        + f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Areas for Follow-Up", _T['moderate'])}
            {_ds_content_box(
                "· &nbsp;Have a relaxed conversation with your learner about their online interactions.<br>"
                "· &nbsp;Reinforce boundaries around appropriate topics during sessions.<br>"
                "· &nbsp;Our team has reviewed and documented this session.",
                bg="#FFFBEB", border="#FDE68A"
            )}
          </td>
        </tr>"""
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_paragraph(
                "No immediate risk has been identified. Our Safety Team has reviewed "
                "and documented this session. Please reach out if you would like to "
                "discuss further.",
                margin_bottom="0"
            )}
          </td>
        </tr>"""
        + (_ds_cta_button("View Session Report", report_link, _T["moderate"]) if report_link else "")
        + _ds_signature()
        + _ds_spacer(32)
        + _ds_footer(report_id)
    )
    return _ds_wrap(inner, preview_text="A session safety notification is ready for your review.")


def _parent_high_html(
    report_id: int,
    filename: str,
    severity: str,
    summary: str,
    findings: List[Dict[str, Any]],
    app_url: str = "",
) -> str:
    report_link = f"{app_url}/report/{report_id}" if app_url else ""
    observations = _build_parent_observations(findings, max_items=5)
    accent = _sev_color(severity)

    inner = (
        _ds_header()
        + _ds_severity_badge(severity)
        + f"""
        <tr>
          <td class="email-pad" style="padding:36px 40px 0;">
            {_ds_greeting()}
            {_ds_paragraph(
                "We are writing to inform you that a recent MelodyWings session has been "
                "<strong>escalated for priority review</strong> by our Safety Team."
            )}
            {_ds_paragraph(
                "The session contained content that may represent a significant concern and "
                "we believe it is important to bring this to your attention promptly. Our "
                "team has already secured the session records and begun a review."
            )}
          </td>
        </tr>"""
        + _ds_divider()
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_section_label("Session Overview", accent)}
            {_ds_content_box(summary or "This session has been escalated for priority review.")}
          </td>
        </tr>"""
        + (f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Key Findings", accent)}
            {_ds_content_box(observations)}
          </td>
        </tr>""" if observations else "")
        + f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("What We Have Done", accent)}
            {_ds_content_box(
                "✓ &nbsp;Session has been escalated for immediate safety review.<br>"
                "✓ &nbsp;Session records have been secured and documented.<br>"
                "✓ &nbsp;Additional safeguarding measures are being considered.",
                bg="#FFF1F2", border="#FECDD3"
            )}
          </td>
        </tr>"""
        + f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Recommended Next Steps", accent)}
            {_ds_content_box(
                "· &nbsp;Review this notification with your learner as soon as possible.<br>"
                "· &nbsp;A member of our Safety Team may contact you for follow-up.<br>"
                "· &nbsp;Contact us immediately if you have additional concerns.",
                bg="#FFF1F2", border="#FECDD3"
            )}
          </td>
        </tr>"""
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_paragraph(
                "<strong>The safety and wellbeing of our learners is our highest priority.</strong> "
                "Please do not hesitate to contact our Safety Team directly.",
                margin_bottom="0"
            )}
          </td>
        </tr>"""
        + (_ds_cta_button("View Session Report", report_link, accent) if report_link else "")
        + _ds_signature()
        + _ds_spacer(32)
        + _ds_footer(report_id)
    )
    return _ds_wrap(inner, preview_text="Important: A session safety alert requires your attention.")


def _build_parent_observations(findings: List[Dict[str, Any]], max_items: int = 5) -> str:
    """
    Build a simple, plain-language observations list for parents.
    No confidence scores, no technical metadata, no category codes.
    """
    if not findings:
        return ""

    top = sorted(
        findings,
        key=lambda f: f.get("confidence") or f.get("max_confidence") or 0,
        reverse=True,
    )[:max_items]

    # Parent-friendly labels for categories
    _parent_labels = {
        "meeting":               "Request for an in-person meeting",
        "secrecy":               "Request to keep conversation secret",
        "address":               "Request for personal location/address",
        "trust_building":        "Unusual attempts to build personal closeness",
        "manipulation":          "Pressure or manipulative language",
        "sexual_content":        "Inappropriate or adult-themed language",
        "personal_info":         "Request for personal information",
        "isolation":             "Suggestions to exclude parents or other adults",
        "relationship_building": "Unusual personal relationship framing",
        "gift_offering":         "Offers of gifts or rewards",
        "desensitization":       "Gradual introduction of inappropriate topics",
        "identity_probing":      "Questions about personal identity or circumstances",
        "threat":                "Threatening or coercive language",
        "self_harm":             "Discussion of self-harm or distressing topics",
        "contact_escalation":    "Attempts to move contact off-platform",
        "boundary_testing":      "Testing of personal boundaries",
        "flattery":              "Excessive or inappropriate compliments",
        "exclusivity":           "Language suggesting a 'special' private relationship",
    }

    lines = []
    for f in top:
        cats = f.get("categories") or ([f["category"]] if f.get("category") else [])
        label = _parent_labels.get(cats[0].lower() if cats else "", None)
        if not label:
            label = (cats[0].replace("_", " ").title() if cats else "Concern identified")
        lines.append(f"· &nbsp;{label}")

    return "<br>".join(lines)


# ════════════════════════════════════════════════════════════════════════════════
# ADMIN / INTERNAL EMAIL TEMPLATES  (full detail, technical data included)
# ════════════════════════════════════════════════════════════════════════════════

def _admin_report_html(
    report_id: int,
    filename: str,
    severity: str,
    risk_score: float,
    findings: List[Dict[str, Any]],
    llm_summary: str,
    rule_summary: str,
    stats: Dict[str, Any],
    transcript: Optional[str] = None,
    app_url: str = "",
) -> str:
    """Full-detail admin/internal report email."""
    accent      = _sev_color(severity)
    report_link = f"{app_url}/report/{report_id}" if app_url else ""
    sc          = _score_color(risk_score)

    # Stats block
    conf_stats = stats.get("confidence_stats") or {}
    avg_conf   = conf_stats.get("average", 0)
    avg_str    = f"{avg_conf*100:.0f}%" if avg_conf else "—"
    finding_ct = stats.get("finding_count", len(findings))
    categories = stats.get("categories") or stats.get("category_breakdown") or {}

    stat_row = _ds_stat_row([
        {"value": f"{risk_score:.0f}", "label": "Risk Score / 100", "color": sc},
        {"value": str(finding_ct),      "label": "Total Findings",   "color": _T["text"]},
        {"value": avg_str,              "label": "Avg Confidence",   "color": _T["text"]},
    ])

    # Category breakdown table
    cat_rows_html = ""
    if categories:
        rows = ""
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            rows += f"""
            <tr style="border-bottom:1px solid {_T['border']};">
              <td style="padding:9px 14px;font-size:12px;color:{_T['body']};">
                {cat.replace('_', ' ').title()}
              </td>
              <td style="padding:9px 14px;font-size:12px;font-weight:700;
                         color:{_T['text']};text-align:right;">{count}</td>
            </tr>"""
        cat_rows_html = f"""
        <table cellpadding="0" cellspacing="0" border="0" width="100%"
               style="border:1px solid {_T['border']};border-radius:10px;overflow:hidden;">
          <tr style="background:#F1F5F9;">
            <th style="padding:9px 14px;font-size:10px;text-align:left;
                       color:{_T['muted']};text-transform:uppercase;
                       letter-spacing:0.5px;font-weight:600;">Category</th>
            <th style="padding:9px 14px;font-size:10px;text-align:right;
                       color:{_T['muted']};text-transform:uppercase;
                       letter-spacing:0.5px;font-weight:600;">Count</th>
          </tr>
          {rows}
        </table>"""

    # Top findings detail
    findings_html = _admin_findings_table(findings, accent)

    # Metadata
    ts_str = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    short_filename = filename if len(filename) <= 50 else filename[:47] + "..."

    inner = (
        _ds_header("Internal Safety Report")
        + _ds_severity_badge(severity)
        + f"""
        <tr>
          <td style="padding:32px 40px 0;">
            <!-- Meta block -->
            <table cellpadding="0" cellspacing="0" border="0" width="100%"
                   style="background:#F8FAFC;border:1px solid {_T['border']};
                          border-radius:10px;overflow:hidden;">
              <tr>
                <td style="padding:16px 20px;">
                  <table cellpadding="0" cellspacing="0" border="0" width="100%">
                    <tr>
                      <td style="font-size:11px;color:{_T['muted']};text-transform:uppercase;
                                 letter-spacing:0.5px;">Session File</td>
                      <td style="font-size:11px;color:{_T['muted']};text-transform:uppercase;
                                 letter-spacing:0.5px;text-align:right;">Report ID</td>
                    </tr>
                    <tr>
                      <td style="font-size:13px;font-weight:600;color:{_T['text']};
                                 padding-top:3px;word-break:break-all;">{short_filename}</td>
                      <td style="font-size:13px;font-weight:600;color:{_T['text']};
                                 padding-top:3px;text-align:right;">#{report_id}</td>
                    </tr>
                    <tr>
                      <td colspan="2" style="padding-top:10px;padding-bottom:0;">
                        <hr style="border:none;border-top:1px solid {_T['border']};margin:0;">
                      </td>
                    </tr>
                    <tr>
                      <td style="font-size:11px;color:{_T['muted']};
                                 padding-top:10px;">Generated</td>
                      <td style="font-size:11px;color:{_T['muted']};
                                 padding-top:10px;text-align:right;">{ts_str}</td>
                    </tr>
                  </table>
                </td>
              </tr>
            </table>
          </td>
        </tr>"""
        + _ds_divider()
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_section_label("Analysis Metrics", _T['muted'])}
            {stat_row}
          </td>
        </tr>"""
        + _ds_divider()
        + f"""
        <tr>
          <td style="padding:28px 40px 0;">
            {_ds_section_label("AI Executive Summary", accent)}
            {_ds_content_box(llm_summary or "Not available.")}
          </td>
        </tr>"""
        + f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Rule-Based Summary", _T['muted'])}
            {_ds_content_box(rule_summary or "Not available.")}
          </td>
        </tr>"""
        + (f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Category Breakdown", _T['muted'])}
            {cat_rows_html}
          </td>
        </tr>""" if cat_rows_html else "")
        + (f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Top Findings Detail", accent)}
            {findings_html}
          </td>
        </tr>""" if findings_html else "")
        + (f"""
        <tr>
          <td style="padding:20px 40px 0;">
            {_ds_section_label("Confidence &amp; Risk Indicators", _T['muted'])}
            {_admin_risk_indicators_html(stats, risk_score, severity, accent)}
          </td>
        </tr>""")
        + (_ds_cta_button("View Full Report in Dashboard", report_link, accent) if report_link else "")
        + _ds_spacer(28)
        + _ds_footer(report_id)
    )
    return _ds_wrap(inner, preview_text=f"[ADMIN] {_severity_label(severity)} — {short_filename} — Score {risk_score:.0f}/100")


def _admin_findings_table(findings: List[Dict[str, Any]], accent: str) -> str:
    """Render a detailed findings table for admins."""
    if not findings:
        return _ds_content_box("No findings recorded.")

    top = sorted(
        findings,
        key=lambda f: f.get("confidence") or f.get("max_confidence") or 0,
        reverse=True,
    )[:8]

    rows = ""
    for i, f in enumerate(top):
        cats     = f.get("categories") or ([f["category"]] if f.get("category") else [])
        cat_str  = ", ".join(c.replace("_", " ").title() for c in cats) or "Unknown"
        evidence = (f.get("evidence") or f.get("text") or "")[:150]
        ellip    = "…" if len(f.get("evidence") or f.get("text") or "") > 150 else ""
        conf     = (f.get("confidence") or f.get("max_confidence") or 0) * 100
        ctx_type = f.get("context_type", "")
        sev_tag  = f.get("severity", "")
        bg       = "#FFFBEB" if i % 2 == 0 else "#FFFFFF"

        rows += f"""
        <tr style="background:{bg};">
          <td style="padding:10px 14px;font-size:12px;color:{_T['text']};
                     font-weight:600;vertical-align:top;white-space:nowrap;">
            {cat_str}
          </td>
          <td style="padding:10px 14px;font-size:12px;color:{_T['body']};
                     font-style:italic;vertical-align:top;">
            "{evidence}{ellip}"
          </td>
          <td style="padding:10px 14px;font-size:11px;font-weight:700;
                     color:{accent};text-align:right;white-space:nowrap;vertical-align:top;">
            {conf:.0f}%
          </td>
        </tr>"""

    return f"""
    <table cellpadding="0" cellspacing="0" border="0" width="100%"
           style="border:1px solid {_T['border']};border-radius:10px;overflow:hidden;">
      <tr style="background:#F1F5F9;">
        <th style="padding:8px 14px;font-size:10px;text-align:left;color:{_T['muted']};
                   text-transform:uppercase;letter-spacing:0.5px;font-weight:600;
                   white-space:nowrap;">Category</th>
        <th style="padding:8px 14px;font-size:10px;text-align:left;color:{_T['muted']};
                   text-transform:uppercase;letter-spacing:0.5px;font-weight:600;">Evidence</th>
        <th style="padding:8px 14px;font-size:10px;text-align:right;color:{_T['muted']};
                   text-transform:uppercase;letter-spacing:0.5px;font-weight:600;
                   white-space:nowrap;">Confidence</th>
      </tr>
      {rows}
    </table>"""


def _admin_risk_indicators_html(
    stats: Dict[str, Any],
    risk_score: float,
    severity: str,
    accent: str,
) -> str:
    """Render technical risk indicator rows for the admin email."""
    conf_stats    = stats.get("confidence_stats") or {}
    avg_conf      = conf_stats.get("average", 0)
    max_conf      = conf_stats.get("maximum", 0)
    sev_dist      = stats.get("severity_distribution") or {}
    ml_agreement  = stats.get("ml_agreement") or {}

    lines = []
    lines.append(f"Risk Score: <strong>{risk_score:.1f} / 100</strong> &nbsp;·&nbsp; Severity: <strong>{severity.title()}</strong>")
    if avg_conf:
        lines.append(f"Average Confidence: <strong>{avg_conf*100:.0f}%</strong> &nbsp;·&nbsp; Max Confidence: <strong>{max_conf*100:.0f}%</strong>")
    if sev_dist:
        dist_str = " &nbsp;·&nbsp; ".join(f"{k}: <strong>{v}</strong>" for k, v in sev_dist.items())
        lines.append(f"Finding Severity Distribution: {dist_str}")
    word_count = stats.get("word_count")
    if word_count:
        lines.append(f"Transcript Word Count: <strong>{word_count}</strong>")
    uniq_cats = stats.get("unique_categories")
    if uniq_cats:
        lines.append(f"Unique Risk Categories: <strong>{uniq_cats}</strong>")

    return _ds_content_box("<br>".join(lines) if lines else "No additional metrics available.")


# ════════════════════════════════════════════════════════════════════════════════
# CORE SMTP SEND FUNCTION
# ════════════════════════════════════════════════════════════════════════════════

def _send_email_with_from(
    subject: str,
    html_body: str,
    recipients: List[str],
    from_name: str = "",
    pdf_path: Optional[str] = None,
    transcript: Optional[str] = None,
    transcript_filename: str = "session_transcript.txt",
) -> Dict[str, Any]:
    """Internal helper — sends email using a custom From display name."""
    display_name = from_name or SMTP_FROM_NAME
    if not SMTP_USER or not SMTP_PASSWORD:
        msg = "SMTP not configured — set SMTP_USER and SMTP_PASSWORD in .env"
        logger.warning(msg)
        return {"success": False, "message": msg, "recipients": []}

    if not recipients:
        msg = "No recipients configured — set PARENT_RECIPIENTS or ALERT_RECIPIENTS in .env"
        logger.warning(msg)
        return {"success": False, "message": msg, "recipients": []}

    try:
        mime = MIMEMultipart("mixed")
        mime["Subject"] = subject
        mime["From"]    = f"{display_name} <{SMTP_USER}>"
        mime["To"]      = ", ".join(recipients)
        mime["X-Mailer"]       = "MelodyWings Safety System"
        mime["Precedence"]     = "bulk"
        mime["Auto-Submitted"] = "auto-generated"

        # Build multipart/related so the logo CID image is part of the HTML body
        related = MIMEMultipart("related")

        alt = MIMEMultipart("alternative")
        plain_text = re.sub(r"<[^>]+>", "", html_body)
        plain_text = re.sub(r"\s+", " ", plain_text).strip()
        alt.attach(MIMEText(plain_text, "plain", "utf-8"))
        alt.attach(MIMEText(html_body,  "html",  "utf-8"))
        related.attach(alt)

        # Attach logo as inline CID image
        logo_part = _logo_mime_part()
        if logo_part:
            related.attach(logo_part)

        mime.attach(related)

        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "pdf")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{os.path.basename(pdf_path)}"')
            mime.attach(part)

        if transcript and transcript.strip():
            content  = _build_transcript_attachment(transcript, transcript_filename)
            txt_part = MIMEText(content, "plain", "utf-8")
            safe_fname = re.sub(r"[^\w\-. ]", "_", transcript_filename)
            txt_part.add_header("Content-Disposition", f'attachment; filename="{safe_fname}"')
            mime.attach(txt_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, mime.as_string())

        parts = []
        if pdf_path and os.path.exists(pdf_path):  parts.append("PDF")
        if transcript and transcript.strip():       parts.append("transcript")
        suffix = f" (+{', '.join(parts)})" if parts else ""
        logger.info(f"Email sent{suffix}: '{subject}' → {recipients}")
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
        mime = MIMEMultipart("mixed")
        mime["Subject"] = subject
        mime["From"]    = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        mime["To"]      = ", ".join(recipients)
        # Anti-spam headers
        mime["X-Mailer"] = "MelodyWings Safety System"
        mime["Precedence"] = "bulk"
        mime["Auto-Submitted"] = "auto-generated"

        # multipart/related wraps HTML + inline logo CID image
        related = MIMEMultipart("related")

        alt = MIMEMultipart("alternative")
        plain_text = re.sub(r"<[^>]+>", "", html_body)
        plain_text = re.sub(r"\s+", " ", plain_text).strip()
        alt.attach(MIMEText(plain_text, "plain", "utf-8"))
        alt.attach(MIMEText(html_body,  "html",  "utf-8"))
        related.attach(alt)

        # Attach logo as inline CID image
        logo_part = _logo_mime_part()
        if logo_part:
            related.attach(logo_part)

        mime.attach(related)

        # PDF attachment
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, "rb") as f:
                part = MIMEBase("application", "pdf")
                part.set_payload(f.read())
            encoders.encode_base64(part)
            pdf_fname = os.path.basename(pdf_path)
            part.add_header("Content-Disposition", f'attachment; filename="{pdf_fname}"')
            mime.attach(part)

        # Transcript attachment
        if transcript and transcript.strip():
            transcript_content = _build_transcript_attachment(transcript, transcript_filename)
            txt_part = MIMEText(transcript_content, "plain", "utf-8")
            safe_fname = re.sub(r"[^\w\-. ]", "_", transcript_filename)
            txt_part.add_header("Content-Disposition", f'attachment; filename="{safe_fname}"')
            mime.attach(txt_part)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipients, mime.as_string())

        attach_parts = []
        if pdf_path and os.path.exists(pdf_path):   attach_parts.append("PDF")
        if transcript and transcript.strip():        attach_parts.append("transcript")
        suffix = f" (+{', '.join(attach_parts)})" if attach_parts else ""

        logger.info(f"Email sent{suffix}: '{subject}' → {recipients}")
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
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M UTC")
    border  = "=" * 60
    header  = (
        f"{border}\n"
        f"  MELODYWINGS — SESSION TRANSCRIPT\n"
        f"  Generated : {now_str}\n"
        f"  File      : {filename}\n"
        f"  CONFIDENTIAL — For safeguarding use only\n"
        f"{border}\n\n"
    )
    cleaned = re.sub(r"\n{3,}", "\n\n", transcript.strip())
    footer  = (
        f"\n\n{border}\n"
        f"  End of Transcript\n"
        f"  Generated automatically by MelodyWings Safety Monitoring System\n"
        f"{border}\n"
    )
    return header + cleaned + footer


def _sanitize_for_subject(text: str) -> str:
    """Strip control characters to prevent email header injection."""
    return re.sub(r'[\r\n\x00-\x1f\x7f]', '', text)[:200]


# ════════════════════════════════════════════════════════════════════════════════
# PUBLIC API — PARENT TRACK
# ════════════════════════════════════════════════════════════════════════════════

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
    Send a parent-friendly alert email (simplified — no internal/technical data).

    Recipients default to PARENT_RECIPIENTS (falls back to ALERT_RECIPIENTS).
    From name defaults to PARENT_FROM_NAME.

    Routes to the correct tier template based on severity:
      Safe     → Routine session report, no concerns
      Low      → Awareness notification
      Moderate → Follow-up encouraged
      High     → Priority escalation
      Critical → Same as High, maximum urgency

    Transcript is attached as a .txt file if provided.
    """
    # Use parent recipients by default, not the admin list
    targets        = recipients or _get_parent_recipients()
    safe_filename  = _sanitize_for_subject(filename)
    safe_severity  = _sanitize_for_subject(severity)
    tier           = _severity_tier(severity)
    condensed      = _condense_summary(summary, tier)
    base_name      = os.path.splitext(filename)[0] if filename else f"report_{report_id}"
    transcript_fname = f"{base_name}_transcript.txt"

    if tier == "safe":
        subject = f"[MelodyWings] Session Safety Report — {safe_filename}"
        html    = _parent_safe_html(report_id, filename, app_url)

    elif tier == "low":
        subject = f"[MelodyWings] Session Notification — {safe_filename}"
        html    = _parent_low_html(report_id, filename, condensed, findings, app_url)

    elif tier == "moderate":
        subject = f"[MelodyWings] Safety Notification — {safe_filename}"
        html    = _parent_moderate_html(report_id, filename, condensed, findings, app_url)

    else:  # high / critical
        subject = f"[MelodyWings] PRIORITY Safety Alert — {safe_filename}"
        html    = _parent_high_html(report_id, filename, severity, condensed, findings, app_url)

    # Temporarily override the From name for parent emails
    original_from = SMTP_FROM_NAME
    return _send_email_with_from(
        subject=subject,
        html_body=html,
        recipients=targets,
        from_name=PARENT_FROM_NAME,
        pdf_path=pdf_path,
        transcript=transcript,
        transcript_filename=transcript_fname,
    )


# ════════════════════════════════════════════════════════════════════════════════
# PUBLIC API — ADMIN / INTERNAL TRACK
# ════════════════════════════════════════════════════════════════════════════════

def send_admin_report(
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
    """
    Send a full-detail admin/internal report email.

    Includes: complete transcript, AI analysis, risk indicators, session metrics,
    confidence stats, category breakdown, findings detail, and technical metadata.

    This should be sent to internal staff only — never to parents.
    """
    targets       = recipients or _get_recipients()
    safe_filename = _sanitize_for_subject(filename)
    safe_severity = _sanitize_for_subject(severity)
    subject       = f"[ADMIN REPORT] {safe_severity.upper()} — {safe_filename} (Score: {risk_score:.0f}/100)"
    base_name     = os.path.splitext(filename)[0] if filename else f"report_{report_id}"
    transcript_fname = f"{base_name}_transcript.txt"

    html = _admin_report_html(
        report_id, filename, severity, risk_score,
        findings, llm_summary, rule_summary, stats,
        transcript=transcript, app_url=app_url,
    )
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
    """
    Alias for send_admin_report — kept for backward compatibility.
    Sends the full-detail admin/internal summary email.
    """
    return send_admin_report(
        report_id=report_id,
        filename=filename,
        severity=severity,
        risk_score=risk_score,
        findings=findings,
        llm_summary=llm_summary,
        rule_summary=rule_summary,
        stats=stats,
        pdf_path=pdf_path,
        recipients=recipients,
        app_url=app_url,
        transcript=transcript,
    )
