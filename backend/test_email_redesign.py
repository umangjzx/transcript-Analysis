"""
Email Redesign Test Script
==========================
Tests every email type in the new two-track system:

  PARENT TRACK  (send_alert_email)
    1. Safe      → rtrumang16@gmail.com
    2. Low       → rtrumang16@gmail.com
    3. Moderate  → rtrumang16@gmail.com
    4. High      → rtrumang16@gmail.com
    5. Critical  → rtrumang16@gmail.com

  ADMIN TRACK  (send_admin_report / send_summary_email)
    6. Admin report (High)   → 71762333052@cit.edu.in
    7. Summary email (alias) → 71762333052@cit.edu.in

Run from the backend directory:
    python test_email_redesign.py
"""

import os
import sys
import smtplib
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Terminal colour helpers ───────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BLUE   = "\033[94m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"

def ok(msg):     print(f"  {GREEN}✓{RESET}  {msg}")
def fail(msg):   print(f"  {RED}✗{RESET}  {msg}")
def warn(msg):   print(f"  {YELLOW}⚠{RESET}  {msg}")
def info(msg):   print(f"  {CYAN}→{RESET}  {msg}")
def header(msg): print(f"\n{BOLD}{BLUE}{'━'*55}{RESET}\n{BOLD}  {msg}{RESET}\n{DIM}{'━'*55}{RESET}")
def sub(msg):    print(f"\n  {BOLD}{msg}{RESET}")

# ── Mock data ─────────────────────────────────────────────────────────────────
MOCK_ID        = 9999
MOCK_FILE      = "test_session_audio.mp3"
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
    "SECTION 1 — EXECUTIVE SUMMARY\n"
    "This session exhibits multiple high-severity grooming indicators. "
    "The subject attempts to arrange an in-person meeting, requests location "
    "information, and explicitly instructs the target to keep conversations "
    "secret from parents. Immediate escalation is strongly recommended.\n\n"
    "SECTION 2 — KEY CONCERNS\n"
    "Physical meeting was requested along with location details. "
    "Secrecy was reinforced multiple times across the conversation. "
    "Psychological manipulation tactics were identified.\n\n"
    "SECTION 3 — RISK ASSESSMENT\n"
    "Risk score 87.5/100. Critical severity confirmed. "
    "Pattern consistent with grooming behaviour. Requires immediate review."
)
MOCK_RULE_SUMMARY = (
    "Detected 5 findings across 5 categories. Risk score: 87.5/100 (Critical). "
    "Categories flagged: Meeting Requests (×2), Secrecy (×1), Address/Location (×1), "
    "Trust Building (×1), Manipulation (×1). ML classifier agreement: 94%."
)
MOCK_TRANSCRIPT = """[00:00] Tutor: Hi, how are you today?
[00:05] Student: I'm okay I guess.
[00:10] Tutor: Can we meet after school today? I know a quiet place.
[00:18] Student: I don't know...
[00:22] Tutor: Don't tell your parents about our conversations, okay?
[00:28] Student: Why not?
[00:31] Tutor: I feel like I understand you better than anyone else does.
[00:38] Tutor: What street do you live on? I can pick you up.
[00:44] Student: I'm not sure I should say...
[00:49] Tutor: If you really trusted me you would do this."""

APP_URL = os.getenv("APP_URL", "http://localhost:5173")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Configuration check
# ─────────────────────────────────────────────────────────────────────────────
header("Step 1 — Configuration Check")

smtp_host   = os.getenv("SMTP_HOST", "smtp.gmail.com")
smtp_port   = int(os.getenv("SMTP_PORT", "587"))
smtp_user   = os.getenv("SMTP_USER", "")
smtp_pass   = os.getenv("SMTP_PASSWORD", "")
from_name   = os.getenv("SMTP_FROM_NAME", "MelodyWings Safety")
p_from_name = os.getenv("PARENT_FROM_NAME", "MelodyWings Safety Team")

admin_raw  = os.getenv("ALERT_RECIPIENTS", "")
parent_raw = os.getenv("PARENT_RECIPIENTS", "")

admin_recipients  = [r.strip() for r in admin_raw.split(",")  if r.strip()]
parent_recipients = [r.strip() for r in parent_raw.split(",") if r.strip()]
# Fall back to admin if no parent list
if not parent_recipients:
    parent_recipients = admin_recipients
    warn("PARENT_RECIPIENTS not set — will use ALERT_RECIPIENTS as fallback")

info(f"SMTP              : {smtp_host}:{smtp_port}")
info(f"SMTP_USER         : {smtp_user or '(not set)'}")
info(f"SMTP_PASSWORD     : {'(set ✓)' if smtp_pass else '(NOT SET)'}")
info(f"SMTP_FROM_NAME    : {from_name}")
info(f"PARENT_FROM_NAME  : {p_from_name}")
info(f"Admin recipients  : {admin_recipients or '(none)'}")
info(f"Parent recipients : {parent_recipients or '(none)'}")
info(f"ALERT_SEVERITY    : {os.getenv('ALERT_SEVERITY', 'High')}")
info(f"PARENT_ALERT_SEV  : {os.getenv('PARENT_ALERT_SEVERITY', 'Low')}")
info(f"APP_URL           : {APP_URL}")

cfg_ok = True
if not smtp_user:
    fail("SMTP_USER is not set"); cfg_ok = False
else:
    ok("SMTP_USER is set")

if not smtp_pass:
    fail("SMTP_PASSWORD is not set"); cfg_ok = False
else:
    ok("SMTP_PASSWORD is set")

if not admin_recipients:
    fail("ALERT_RECIPIENTS is not set"); cfg_ok = False
else:
    ok(f"Admin recipients  : {', '.join(admin_recipients)}")

if parent_recipients:
    ok(f"Parent recipients : {', '.join(parent_recipients)}")
else:
    fail("No recipient addresses available at all"); cfg_ok = False

if not cfg_ok:
    print(f"\n{RED}{BOLD}Cannot proceed — fix the config above in backend/.env{RESET}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2: SMTP connection test
# ─────────────────────────────────────────────────────────────────────────────
header("Step 2 — SMTP Connection Test")
try:
    info(f"Connecting to {smtp_host}:{smtp_port} …")
    with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
        server.ehlo()
        server.starttls()
        ok("STARTTLS handshake successful")
        server.login(smtp_user, smtp_pass)
        ok("Authentication successful — SMTP credentials are valid")
except smtplib.SMTPAuthenticationError:
    fail("Authentication failed — check SMTP_USER and SMTP_PASSWORD")
    print(f"\n{YELLOW}Gmail tip:{RESET} Use a 16-character App Password, not your account password.")
    print("  Generate one at: https://myaccount.google.com/apppasswords")
    sys.exit(1)
except Exception as e:
    fail(f"SMTP connection error: {e}")
    sys.exit(1)


# ─────────────────────────────────────────────────────────────────────────────
# Import email functions
# ─────────────────────────────────────────────────────────────────────────────
try:
    from modules.email_notifier import (
        send_alert_email,
        send_admin_report,
        send_summary_email,
    )
    ok("email_notifier module loaded successfully")
except ImportError as e:
    fail(f"Failed to import email_notifier: {e}")
    sys.exit(1)


results = []

def run_test(label, fn, *args, **kwargs):
    """Run one email send and record pass/fail."""
    try:
        info(f"Sending: {label} …")
        result = fn(*args, **kwargs)
        if result["success"]:
            ok(f"Sent → {result['recipients']}")
            results.append((label, True, None))
        else:
            fail(f"Failed: {result['message']}")
            results.append((label, False, result["message"]))
    except Exception as e:
        fail(f"Exception: {e}")
        results.append((label, False, str(e)))


# ─────────────────────────────────────────────────────────────────────────────
# STEP 3: Parent track — all five severity tiers
# ─────────────────────────────────────────────────────────────────────────────
header("Step 3 — Parent Track (send_alert_email)")
print(f"  {DIM}Recipient: {', '.join(parent_recipients)}{RESET}")
print(f"  {DIM}These emails are simplified — no internal scores or technical data{RESET}\n")

sub("3a. Safe — No Concerns Detected")
run_test(
    "Parent — Safe",
    send_alert_email,
    report_id=MOCK_ID, filename=MOCK_FILE, severity="Safe",
    risk_score=8.0, findings=[], summary="Session was completely normal.",
    stats=MOCK_STATS, recipients=parent_recipients, app_url=APP_URL,
)

sub("3b. Low — Awareness Notification")
run_test(
    "Parent — Low",
    send_alert_email,
    report_id=MOCK_ID, filename=MOCK_FILE, severity="Low",
    risk_score=22.0, findings=MOCK_FINDINGS[:2],
    summary=MOCK_LLM_SUMMARY, stats=MOCK_STATS,
    recipients=parent_recipients, app_url=APP_URL,
)

sub("3c. Moderate — Follow-up Encouraged")
run_test(
    "Parent — Moderate",
    send_alert_email,
    report_id=MOCK_ID, filename=MOCK_FILE, severity="Moderate",
    risk_score=48.0, findings=MOCK_FINDINGS[:3],
    summary=MOCK_LLM_SUMMARY, stats=MOCK_STATS,
    recipients=parent_recipients, app_url=APP_URL,
)

sub("3d. High — Priority Alert")
run_test(
    "Parent — High",
    send_alert_email,
    report_id=MOCK_ID, filename=MOCK_FILE, severity="High",
    risk_score=76.0, findings=MOCK_FINDINGS,
    summary=MOCK_LLM_SUMMARY, stats=MOCK_STATS,
    recipients=parent_recipients, app_url=APP_URL,
    transcript=MOCK_TRANSCRIPT,
)

sub("3e. Critical — Priority Alert (highest urgency)")
run_test(
    "Parent — Critical",
    send_alert_email,
    report_id=MOCK_ID, filename=MOCK_FILE, severity="Critical",
    risk_score=87.5, findings=MOCK_FINDINGS,
    summary=MOCK_LLM_SUMMARY, stats=MOCK_STATS,
    recipients=parent_recipients, app_url=APP_URL,
    transcript=MOCK_TRANSCRIPT,
)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Admin track — full detail report
# ─────────────────────────────────────────────────────────────────────────────
header("Step 4 — Admin Track (send_admin_report)")
print(f"  {DIM}Recipient: {', '.join(admin_recipients)}{RESET}")
print(f"  {DIM}These emails include full AI analysis, scores, findings, and metadata{RESET}\n")

sub("4a. Admin Report — Critical severity")
run_test(
    "Admin — Critical Report",
    send_admin_report,
    report_id=MOCK_ID, filename=MOCK_FILE, severity="Critical",
    risk_score=87.5, findings=MOCK_FINDINGS,
    llm_summary=MOCK_LLM_SUMMARY, rule_summary=MOCK_RULE_SUMMARY,
    stats=MOCK_STATS, recipients=admin_recipients,
    app_url=APP_URL, transcript=MOCK_TRANSCRIPT,
)

sub("4b. Summary Email — backward-compat alias for send_admin_report")
run_test(
    "Admin — Summary (alias)",
    send_summary_email,
    report_id=MOCK_ID, filename=MOCK_FILE, severity="High",
    risk_score=76.0, findings=MOCK_FINDINGS,
    llm_summary=MOCK_LLM_SUMMARY, rule_summary=MOCK_RULE_SUMMARY,
    stats=MOCK_STATS, recipients=admin_recipients,
    app_url=APP_URL,
)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Results summary
# ─────────────────────────────────────────────────────────────────────────────
header("Step 5 — Results Summary")

passed = [r for r in results if r[1]]
failed = [r for r in results if not r[1]]

for label, success, err in results:
    if success:
        ok(label)
    else:
        fail(f"{label}  —  {err}")

print()
if failed:
    print(f"{YELLOW}{BOLD}  {len(passed)}/{len(results)} tests passed.  {len(failed)} failed.{RESET}")
    print(f"\n{YELLOW}  Check the errors above and verify your .env configuration.{RESET}")
    sys.exit(1)
else:
    print(f"{GREEN}{BOLD}  All {len(results)} emails sent successfully!{RESET}")
    print()
    print(f"  {BOLD}Check your inboxes:{RESET}")
    print(f"  {GREEN}→{RESET}  Parent inbox : {', '.join(parent_recipients)}")
    print(f"     Expected  : 5 emails (Safe, Low, Moderate, High, Critical)")
    print()
    print(f"  {GREEN}→{RESET}  Admin inbox  : {', '.join(admin_recipients)}")
    print(f"     Expected  : 2 emails (Admin Report, Summary alias)")
    print()
    print(f"  {DIM}High/Critical parent emails include a transcript attachment.{RESET}")
    print(f"  {DIM}Admin emails include the full AI analysis, category table, and findings detail.{RESET}")
    print()
