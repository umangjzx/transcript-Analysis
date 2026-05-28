"""
Test Script Runner
==================
Feeds test transcripts directly into the grooming detection pipeline
(bypasses audio transcription) and prints a full report for each.

Usage:
    cd backend
    python examples/run_test_scripts.py

Test Categories:
    Core Scripts:
        test_script_bad.txt    → CRITICAL risk, many findings across all categories
        test_script_medium.txt → MODERATE risk, some concerning patterns
        test_script_good.txt   → SAFE / LOW risk, zero or near-zero findings

    Edge Cases (obfuscation & subtle grooming):
        test_edge_leetspeak.txt         → Moderate+ (leetspeak obfuscation)
        test_edge_leetspeak2.txt        → Moderate+ (leetspeak + image solicitation)
        test_edge_subtle.txt            → High+ (subtle behavioral grooming)
        test_edge_coded_language.txt    → Critical (coded language, meeting planning)
        test_edge_slow_burn.txt         → High+ (slow-burn gaming grooming)
        test_edge_buried_flags.txt      → Moderate+ (buried red flags in friendly chat)
        test_edge_negation_jokes.txt    → Moderate+ (starts safe, escalates via "hypotheticals")
        test_edge_unicode_bypass.txt    → Moderate+ (unicode homoglyph bypass)
        test_edge_false_positive_mentor.txt → Safe/Low (legitimate mentorship)

    Safe Files (false positive check):
        test_safe_*.txt → Must remain Safe or Low
"""

import sys
import os
import json

# Make sure the backend root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.grooming_detector import GroomingDetector
from modules.risk_scorer import WeightedRiskScorer
from modules.severity_classifier import classify_severity
from modules.evidence_extractor import extract_evidence
from modules.stats import generate_stats

# ── Config ──────────────────────────────────────────────────────────────────

SCRIPTS = {
    "BAD    (high-risk grooming)": os.path.join(
        os.path.dirname(__file__), "test_script_bad.txt"
    ),
    "MEDIUM (ambiguous online chat)": os.path.join(
        os.path.dirname(__file__), "test_script_medium.txt"
    ),
    "GOOD   (safe classroom)": os.path.join(
        os.path.dirname(__file__), "test_script_good.txt"
    ),
}

# Edge cases — test obfuscation, subtle grooming, and behavioral patterns.
EDGE_CASES = {
    "EDGE   (leetspeak obfuscation)": os.path.join(
        os.path.dirname(__file__), "test_edge_leetspeak.txt"
    ),
    "EDGE   (leetspeak + solicitation)": os.path.join(
        os.path.dirname(__file__), "test_edge_leetspeak2.txt"
    ),
    "EDGE   (subtle grooming)": os.path.join(
        os.path.dirname(__file__), "test_edge_subtle.txt"
    ),
    "EDGE   (coded language)": os.path.join(
        os.path.dirname(__file__), "test_edge_coded_language.txt"
    ),
    "EDGE   (slow burn)": os.path.join(
        os.path.dirname(__file__), "test_edge_slow_burn.txt"
    ),
    "EDGE   (buried flags)": os.path.join(
        os.path.dirname(__file__), "test_edge_buried_flags.txt"
    ),
    "EDGE   (negation/jokes bypass)": os.path.join(
        os.path.dirname(__file__), "test_edge_negation_jokes.txt"
    ),
    "EDGE   (unicode bypass)": os.path.join(
        os.path.dirname(__file__), "test_edge_unicode_bypass.txt"
    ),
    "EDGE   (false positive mentor)": os.path.join(
        os.path.dirname(__file__), "test_edge_false_positive_mentor.txt"
    ),
}

# Safe files — must remain Safe or Low to avoid false positives.
SAFE_FILES = {
    "SAFE   (counselor session)": os.path.join(
        os.path.dirname(__file__), "test_safe_counselor_session.txt"
    ),
    "SAFE   (doctor visit)": os.path.join(
        os.path.dirname(__file__), "test_safe_doctor_visit.txt"
    ),
    "SAFE   (gaming friends)": os.path.join(
        os.path.dirname(__file__), "test_safe_gaming_friends.txt"
    ),
    "SAFE   (parent child)": os.path.join(
        os.path.dirname(__file__), "test_safe_parent_child.txt"
    ),
    "SAFE   (sports coach)": os.path.join(
        os.path.dirname(__file__), "test_safe_sports_coach.txt"
    ),
    "SAFE   (teacher conference)": os.path.join(
        os.path.dirname(__file__), "test_safe_teacher_conference.txt"
    ),
    "SAFE   (youth group)": os.path.join(
        os.path.dirname(__file__), "test_safe_youth_group.txt"
    ),
}

# Disable ML classifier for fast local testing.
# Set to True if you have the model cached (~1.6 GB).
ENABLE_ML = False

# ── Helpers ──────────────────────────────────────────────────────────────────

SEV_COLORS = {
    "critical": "\033[91m",   # bright red
    "high":     "\033[31m",   # red
    "medium":   "\033[33m",   # yellow
    "moderate": "\033[33m",
    "low":      "\033[32m",   # green
    "safe":     "\033[32m",
    "unknown":  "\033[37m",   # grey
}
RESET = "\033[0m"
BOLD  = "\033[1m"
DIM   = "\033[2m"
CYAN  = "\033[96m"
GREEN = "\033[92m"
RED   = "\033[91m"


def color(text, sev):
    c = SEV_COLORS.get((sev or "").lower(), "\033[37m")
    return f"{c}{text}{RESET}"


def bar(value, width=40):
    """ASCII progress bar for confidence / risk score."""
    filled = int(value * width)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {value*100:.1f}%"


def section(title):
    print(f"\n{BOLD}{CYAN}{'─' * 60}{RESET}")
    print(f"{BOLD}{CYAN}  {title}{RESET}")
    print(f"{BOLD}{CYAN}{'─' * 60}{RESET}")


def run_analysis(label, filepath):
    section(f"SCRIPT: {label}")

    # Load transcript
    with open(filepath, "r", encoding="utf-8") as f:
        transcript = f.read()

    print(f"\n{DIM}Transcript preview (first 200 chars):{RESET}")
    print(f"  {transcript[:200].replace(chr(10), ' ')}...")

    # ── Detection ────────────────────────────────────────────────────────────
    detector = GroomingDetector(
        min_confidence_threshold=0.15,
        enable_ml_classifier=ENABLE_ML,
    )
    results = detector.analyze_transcript(transcript, speaker_aware=True)

    grouped   = results["grouped_findings"]
    all_finds = results["findings"]
    summary   = results["summary"]

    # ── Risk + Severity ───────────────────────────────────────────────────────
    scorer    = WeightedRiskScorer()
    risk      = scorer.calculate_score(grouped)
    severity  = classify_severity(risk["score"])
    evidence  = extract_evidence(grouped)
    stats     = generate_stats(transcript, grouped, severity, risk["score"])

    # ── Print Summary ─────────────────────────────────────────────────────────
    print(f"\n{BOLD}RESULT SUMMARY{RESET}")
    risk_score_str = f"{risk['score']:.1f} / 100"
    print(f"  Risk Score  : {color(risk_score_str, severity)}")
    print(f"  Severity    : {color(severity.upper(), severity)}")
    print(f"  Findings    : {len(all_finds)} raw  →  {len(grouped)} grouped")
    print(f"  Evidence    : {len(evidence)} items")
    print(f"  Word Count  : {stats['word_count']}")
    print(f"  Categories  : {stats['unique_categories']} unique")

    # Risk bar
    print(f"\n  Risk  {bar(risk['score'] / 100)}")

    # ── Category Breakdown ────────────────────────────────────────────────────
    if summary["category_distribution"]:
        print(f"\n{BOLD}CATEGORY BREAKDOWN{RESET}")
        for cat, count in sorted(
            summary["category_distribution"].items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            sev = "high"
            for f in grouped:
                cats = f.get("categories") or ([f.get("category")] if f.get("category") else [])
                if cat in cats:
                    sev = f.get("severity", "low")
                    break
            print(f"  {color(f'{cat:<22}', sev)}  {count:>2} hit(s)")

    # ── Findings Detail ───────────────────────────────────────────────────────
    if grouped:
        print(f"\n{BOLD}FINDINGS (grouped){RESET}")
        for i, f in enumerate(grouped, 1):
            cats     = f.get("categories") or ([f.get("category")] if f.get("category") else [])
            conf     = f.get("confidence") or f.get("max_confidence") or 0
            sev      = f.get("severity", "unknown")
            text     = f.get("evidence", f.get("text", ""))
            speaker  = f.get("speaker", "")
            ctx_type = f.get("context_type", "")

            cat_str  = " + ".join(cats)
            spk_str  = f"  [{speaker}]" if speaker else ""
            ctx_str  = f"  ctx={ctx_type}" if ctx_type and ctx_type != "NEUTRAL" else ""

            print(f"\n  #{i:02d}  {color(cat_str, sev)}{spk_str}{ctx_str}")
            print(f"       conf={conf*100:.1f}%  sev={color(sev.upper(), sev)}")
            print(f"       \"{text[:100]}{'...' if len(text) > 100 else ''}\"")
    else:
        print(f"\n  {GREEN}✓ No findings — conversation appears safe.{RESET}")

    # ── Evidence Log ──────────────────────────────────────────────────────────
    if evidence:
        print(f"\n{BOLD}EVIDENCE LOG{RESET}")
        for ev in evidence:
            cats = ev.get("categories") or [ev.get("category", "unknown")]
            sev  = ev.get("severity", "LOW")
            conf = ev.get("confidence", 0)
            text = ev.get("evidence", "")
            print(f"  [{color(sev, sev)}] {', '.join(cats):<30}  {conf*100:.1f}%")
            print(f"         \"{text[:90]}{'...' if len(text) > 90 else ''}\"")

    # ── Pass / Fail ───────────────────────────────────────────────────────────
    print()
    if "BAD" in label:
        passed = risk["score"] >= 60 and len(grouped) >= 5
        verdict = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        print(f"  Test assertion (score ≥ 60, findings ≥ 5): {verdict}")
        if not passed:
            print(f"    Got score={risk['score']:.1f}, findings={len(grouped)}")
    elif "MEDIUM" in label:
        passed = 30 <= risk["score"] <= 70 and 3 <= len(grouped) <= 15
        verdict = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        print(f"  Test assertion (30 ≤ score ≤ 70, 3 ≤ findings ≤ 15): {verdict}")
        if not passed:
            print(f"    Got score={risk['score']:.1f}, findings={len(grouped)}")
    elif "EDGE" in label:
        # Edge cases with grooming content should score ≥ 40 (Moderate+)
        # False positive edge cases should score ≤ 40 (Safe/Low)
        if "false positive" in label.lower():
            passed = risk["score"] <= 40
            verdict = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
            print(f"  Test assertion (false positive: score ≤ 40): {verdict}")
        elif "negation" in label.lower():
            # Negation/jokes file starts safe but escalates — should detect the escalation
            passed = risk["score"] >= 30
            verdict = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
            print(f"  Test assertion (negation bypass: score ≥ 30): {verdict}")
        else:
            passed = risk["score"] >= 40
            verdict = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
            print(f"  Test assertion (edge grooming: score ≥ 40): {verdict}")
        if not passed:
            print(f"    Got score={risk['score']:.1f}, findings={len(grouped)}")
    elif "SAFE" in label:
        passed = risk["score"] <= 40 and severity in ("Safe", "Low")
        verdict = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        print(f"  Test assertion (safe: score ≤ 40, severity Safe/Low): {verdict}")
        if not passed:
            print(f"    Got score={risk['score']:.1f}, severity={severity}, findings={len(grouped)}")
    else:
        passed = risk["score"] <= 20 and len(grouped) <= 2
        verdict = f"{GREEN}✓ PASS{RESET}" if passed else f"{RED}✗ FAIL{RESET}"
        print(f"  Test assertion (score ≤ 20, findings ≤ 2): {verdict}")
        if not passed:
            print(f"    Got score={risk['score']:.1f}, findings={len(grouped)}")

    return {
        "label":     label,
        "risk_score": risk["score"],
        "severity":  severity,
        "findings":  len(grouped),
        "evidence":  len(evidence),
        "passed":    passed,
    }


# ── Main ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"\n{BOLD}{'=' * 60}{RESET}")
    print(f"{BOLD}  GROOMING DETECTION PIPELINE — TEST RUNNER{RESET}")
    print(f"{BOLD}{'=' * 60}{RESET}")
    print(f"  ML classifier : {'ENABLED' if ENABLE_ML else 'DISABLED (set ENABLE_ML=True to use)'}")

    results = []

    # ── Core scripts ──────────────────────────────────────────────────────────
    section("CORE SCRIPTS (BAD / MEDIUM / GOOD)")
    for label, path in SCRIPTS.items():
        try:
            r = run_analysis(label, path)
            results.append(r)
        except Exception as e:
            print(f"\n{RED}ERROR running '{label}': {e}{RESET}")
            import traceback
            traceback.print_exc()

    # ── Edge cases ────────────────────────────────────────────────────────────
    section("EDGE CASES (obfuscation, subtle grooming, behavioral)")
    for label, path in EDGE_CASES.items():
        if not os.path.exists(path):
            print(f"\n  {DIM}SKIP: {path} not found{RESET}")
            continue
        try:
            r = run_analysis(label, path)
            results.append(r)
        except Exception as e:
            print(f"\n{RED}ERROR running '{label}': {e}{RESET}")
            import traceback
            traceback.print_exc()

    # ── Safe files ────────────────────────────────────────────────────────────
    section("SAFE FILES (false positive check)")
    for label, path in SAFE_FILES.items():
        if not os.path.exists(path):
            print(f"\n  {DIM}SKIP: {path} not found{RESET}")
            continue
        try:
            r = run_analysis(label, path)
            results.append(r)
        except Exception as e:
            print(f"\n{RED}ERROR running '{label}': {e}{RESET}")
            import traceback
            traceback.print_exc()

    # ── Final Summary ─────────────────────────────────────────────────────────
    section("FINAL TEST SUMMARY")
    all_passed = True
    for r in results:
        status = f"{GREEN}PASS{RESET}" if r["passed"] else f"{RED}FAIL{RESET}"
        print(
            f"  [{status}]  {r['label']:<35}"
            f"  score={r['risk_score']:5.1f}  "
            f"sev={color(r['severity'].upper(), r['severity']):<20}  "
            f"findings={r['findings']}"
        )
        if not r["passed"]:
            all_passed = False

    print()
    total = len(results)
    passed_count = sum(1 for r in results if r["passed"])
    if all_passed:
        print(f"  {GREEN}{BOLD}All {total} tests passed ✓{RESET}")
    else:
        failed_count = total - passed_count
        print(f"  {RED}{BOLD}{failed_count}/{total} tests failed ✗{RESET}")
    print()
