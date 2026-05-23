"""
Email Notifier — Test Script
Run from the backend directory:
    python test_email.py

Tests:
  1. Config check  — are SMTP_USER, SMTP_PASSWORD, ALERT_RECIPIENTS set?
  2. SMTP connect  — can we reach the server and authenticate?
  3. Alert email   — sends a real red-alert email with mock data
  4. Summary email — sends a real summary email with mock data
"""

import os
import sys
import smtplib
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Colour helpers for terminal output ───────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"

def ok(msg):   print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg): print(f"  {RED}✗{RESET}  {msg}")
def warn(msg): print(f"  {YELLOW}⚠{RESET}  {msg}")
def info(msg): print(f"  {CYAN}→{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{msg}{RESET}\n{'─'*50}")

# ── Mock report data ──────────────────────────────────────────────────────────
MOCK_REPORT_ID = 0
MOCK_FILENAME  = "test_audio_sample.mp3"
MOCK_SEVERITY  = "Critical"
MOCK_RISK      = 87.5
MOCK_FINDINGS  = [
    {
        "categories": ["meeting"],
        "category":   "meeting",
        "confidence": 0.94,
        "evidence":   "Can we meet after school today? I know a quiet place.",
        "severity":   "critical",
        "context_type": "GROOMING",
    },
    {
        "categories": ["secrecy"],
        "category":   "secrecy",
        "confidence": 0.88,
        "evidence":   "Don't tell your parents about our conversations.",
        "severity":   "high",
        "context_type": "GROOMING",
    },
    {
        "categories": ["address"],
        "category":   "address",
        "confidence": 0.81,
        "evidence":   "What street do you live on? I can pick you up.",
        "severity":   "critical",
        "context_type": "GROOMING",
    },
    {
        "categories": ["trust_building"],
        "category":   "trust_building",
        "confidence": 0.72,
        "evidence":   "I feel like I understand you better than anyone else does.",
        "severity":   "medium",
        "context_type": "NEUTRAL",
    },
    {
        "categories": ["manipulation"],
        "category":   "manipulation",
        "confidence": 0.65,
        "evidence":   "If you really trusted me you would do this.",
        "severity":   "high",
        "context_type": "GROOMING",
    },
]
MOCK_STATS = {
    "word_count": 312,
    "character_count": 1840,
    "finding_count": 5,
    "unique_categories": 5,
    "categories": {
        "meeting": 2, "secrecy": 1, "address": 1,
        "trust_building": 1, "manipulation": 1,
    },
    "confidence_stats": {"average": 0.80, "maximum": 0.94, "minimum": 0.65},
    "severity_distribution": {"critical": 2, "high": 2, "medium": 1},
}
MOCK_LLM_SUMMARY = (
    "This conversation exhibits multiple high-severity grooming indicators. "
    "The subject attempts to arrange an in-person meeting, requests location information, "
    "and explicitly instructs the target to maintain secrecy from parents. "
    "Immediate escalation is recommended."
)
MOCK_RULE_SUMMARY = (
    "Detected 5 findings across 5 categories. Risk score: 87.5/100 (Critical). "
    "Categories flagged: Meeting Requests, Secrecy, Address/Location, "
    "Trust Building, Manipulation."
)


# ── Step 1: Config check ──────────────────────────────────────────────────────
header("Step 1 — Configuration Check")

smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
smtp_port = int(os.getenv("SMTP_PORT", "587"))
smtp_user = os.getenv("SMTP_USER", "")
smtp_pass = os.getenv("SMTP_PASSWORD", "")
recipients_raw = os.getenv("ALERT_RECIPIENTS", "")
recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

info(f"SMTP_HOST      : {smtp_host}:{smtp_port}")
info(f"SMTP_USER      : {smtp_user or '(not set)'}")
info(f"SMTP_PASSWORD  : {'(set)' if smtp_pass else '(not set)'}")
info(f"RECIPIENTS     : {recipients or '(none)'}")

config_ok = True
if not smtp_user:
    fail("SMTP_USER is not set — add it to backend/.env")
    config_ok = False
else:
    ok("SMTP_USER is set")

if not smtp_pass:
    fail("SMTP_PASSWORD is not set — add it to backend/.env")
    config_ok = False
else:
    ok("SMTP_PASSWORD is set")

if not recipients:
    fail("ALERT_RECIPIENTS is not set — add it to backend/.env")
    config_ok = False
else:
    ok(f"Recipients: {', '.join(recipients)}")

if not config_ok:
    print(f"\n{RED}{BOLD}Cannot proceed — fix the missing config above.{RESET}")
    print(f"\n{YELLOW}Quick setup:{RESET}")
    print("  1. Copy backend/.env.example  →  backend/.env")
    print("  2. Fill in SMTP_USER, SMTP_PASSWORD, ALERT_RECIPIENTS")
    print("  3. For Gmail: generate an App Password at")
    print("     https://myaccount.google.com/apppasswords")
    sys.exit(1)


# ── Step 2: SMTP connection test ──────────────────────────────────────────────
header("Step 2 — SMTP Connection Test")

try:
    info(f"Connecting to {smtp_host}:{smtp_port} …")
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
        server.ehlo()
        server.starttls()
        ok("STARTTLS handshake successful")
        server.login(smtp_user, smtp_pass)
        ok("Authentication successful")
except smtplib.SMTPAuthenticationError:
    fail("Authentication failed — check SMTP_USER and SMTP_PASSWORD")
    print(f"\n{YELLOW}Gmail tip:{RESET} Use an App Password, not your account password.")
    print("  Generate one at: https://myaccount.google.com/apppasswords")
    sys.exit(1)
except smtplib.SMTPConnectError as e:
    fail(f"Could not connect to {smtp_host}:{smtp_port} — {e}")
    sys.exit(1)
except Exception as e:
    fail(f"SMTP error: {e}")
    sys.exit(1)


# ── Step 3: Send alert email ──────────────────────────────────────────────────
header("Step 3 — Send Alert Email")

try:
    from modules.email_notifier import send_alert_email
    info(f"Sending alert email to: {', '.join(recipients)}")
    result = send_alert_email(
        report_id=MOCK_REPORT_ID,
        filename=MOCK_FILENAME,
        severity=MOCK_SEVERITY,
        risk_score=MOCK_RISK,
        findings=MOCK_FINDINGS,
        summary=MOCK_LLM_SUMMARY,
        stats=MOCK_STATS,
        pdf_path=None,
        recipients=recipients,
        app_url="http://localhost:5173",
    )
    if result["success"]:
        ok(f"Alert email sent → {result['recipients']}")
    else:
        fail(f"Alert email failed: {result['message']}")
        sys.exit(1)
except Exception as e:
    fail(f"Unexpected error: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)


# ── Step 4: Send summary email ────────────────────────────────────────────────
header("Step 4 — Send Summary Email")

try:
    from modules.email_notifier import send_summary_email
    info(f"Sending summary email to: {', '.join(recipients)}")
    result = send_summary_email(
        report_id=MOCK_REPORT_ID,
        filename=MOCK_FILENAME,
        severity=MOCK_SEVERITY,
        risk_score=MOCK_RISK,
        findings=MOCK_FINDINGS,
        llm_summary=MOCK_LLM_SUMMARY,
        rule_summary=MOCK_RULE_SUMMARY,
        stats=MOCK_STATS,
        pdf_path=None,
        recipients=recipients,
        app_url="http://localhost:5173",
    )
    if result["success"]:
        ok(f"Summary email sent → {result['recipients']}")
    else:
        fail(f"Summary email failed: {result['message']}")
        sys.exit(1)
except Exception as e:
    fail(f"Unexpected error: {e}")
    import traceback; traceback.print_exc()
    sys.exit(1)


# ── Done ──────────────────────────────────────────────────────────────────────
print(f"\n{GREEN}{BOLD}{'='*50}")
print("  All tests passed — check your inbox!")
print(f"{'='*50}{RESET}\n")
