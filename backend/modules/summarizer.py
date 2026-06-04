"""
Rule-Based Summarizer — rich, structured, real-time-quality output.

Generates a detailed, human-readable safety report from detection findings
without requiring an LLM. Used as:
  - The primary summary when LLM is disabled
  - Fallback when Ollama is unavailable
  - The rule_summary field in all emails and MongoDB

Design goals:
  - Reads like a real analyst wrote it
  - Structured sections: Executive Summary → Key Concerns → Evidence → Risk →
    Escalation → Recommendation
  - Severity-aware tone and language
  - Timeline-aware (highlights early vs late conversation patterns)
  - Speaker-aware (flags when a specific speaker is dominant)
  - Confidence-aware (distinguishes high-confidence from tentative findings)
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


# ── Category display names ────────────────────────────────────────────────────

_CAT_LABELS: Dict[str, str] = {
    "meeting":              "Physical Meeting Requests",
    "secrecy":              "Secrecy & Concealment",
    "address":              "Address / Location Solicitation",
    "trust_building":       "Trust Building & Rapport Manipulation",
    "manipulation":         "Psychological Manipulation",
    "sexual_content":       "Sexual Content / Inappropriate Language",
    "personal_info":        "Personal Information Requests",
    "isolation":            "Isolation Tactics",
    "relationship_building":"Relationship Building",
    "gift_offering":        "Gift / Incentive Offering",
    "desensitization":      "Desensitization",
    "identity_probing":     "Identity Probing",
    "threat":               "Threats / Coercive Behaviour",
    "self_harm":            "Self-Harm Discussion",
    "contact_escalation":   "Contact Escalation",
    "boundary_testing":     "Boundary Testing",
    "flattery":             "Flattery / Excessive Compliments",
    "exclusivity":          "Exclusivity / Special Relationship Framing",
}

def _cat_label(cat: str) -> str:
    return _CAT_LABELS.get(cat.lower(), cat.replace("_", " ").title())


# ── Severity-aware prose ──────────────────────────────────────────────────────

_EXEC_SUMMARY: Dict[str, str] = {
    "critical": (
        "This session has been assessed as CRITICAL risk. Multiple high-confidence "
        "grooming indicators were detected across several distinct categories. "
        "The conversation demonstrates a deliberate, structured pattern of predatory "
        "behaviour including attempts to arrange physical meetings, solicitation of "
        "personal information, and explicit instructions for secrecy. Immediate "
        "escalation and safeguarding intervention are required."
    ),
    "high": (
        "This session has been assessed as HIGH risk. Significant grooming indicators "
        "were identified that suggest a systematic attempt to manipulate or exploit "
        "the child. The findings include boundary violations, attempts to build "
        "inappropriate intimacy, and language designed to undermine parental oversight. "
        "Immediate review by a qualified analyst is strongly recommended."
    ),
    "moderate": (
        "This session has been assessed as MODERATE risk. Several potentially "
        "concerning indicators were identified that fall outside the expected scope of "
        "legitimate educational interaction. While no single finding constitutes "
        "definitive evidence of grooming, the combination and frequency of these "
        "patterns warrants careful attention and manual review."
    ),
    "low": (
        "This session has been assessed as LOW risk. A small number of minor "
        "indicators were flagged by the automated system. The detected content does "
        "not currently suggest active grooming behaviour, but has been logged for "
        "transparency and pattern-tracking purposes. No immediate action is required."
    ),
    "safe": (
        "This session was assessed as SAFE. No significant safety indicators were "
        "detected. The conversation appears to be within normal educational boundaries. "
        "This record has been retained as part of routine compliance monitoring."
    ),
}

_RISK_ASSESSMENT: Dict[str, str] = {
    "critical": (
        "The risk score of {score}/100 places this session firmly in the Critical "
        "tier. The convergence of multiple high-confidence findings across distinct "
        "grooming categories significantly elevates the probability that this "
        "conversation represents a genuine safeguarding threat. The automated system "
        "has escalated this record for immediate safety review."
    ),
    "high": (
        "The risk score of {score}/100 places this session in the High tier. "
        "The findings indicate a pattern of behaviour that requires prompt human "
        "review. While individual indicators can occasionally appear in benign "
        "contexts, their combination here is statistically associated with grooming "
        "attempts in historical case data."
    ),
    "moderate": (
        "The risk score of {score}/100 places this session in the Moderate tier. "
        "Some detected indicators may have innocent explanations, but the overall "
        "pattern merits closer examination. A qualified reviewer should assess "
        "whether the context of these findings is appropriate."
    ),
    "low": (
        "The risk score of {score}/100 places this session in the Low tier. "
        "Detected indicators are individually minor and may reflect benign "
        "conversational patterns. No escalation is warranted at this time, "
        "though the record should be retained for longitudinal monitoring."
    ),
    "safe": (
        "The risk score of {score}/100 places this session in the Safe tier. "
        "No meaningful risk signals were detected."
    ),
}

_RECOMMENDATION: Dict[str, str] = {
    "critical": (
        "IMMEDIATE ACTION REQUIRED: (1) Suspend access for the flagged participant "
        "pending investigation. (2) Preserve all session records and this report. "
        "(3) Notify the designated safeguarding lead within 1 hour. (4) Consider "
        "referral to law enforcement or child protection services in accordance with "
        "your organisation's safeguarding policy. (5) Provide pastoral support to "
        "the affected learner."
    ),
    "high": (
        "URGENT REVIEW REQUIRED: (1) A qualified analyst should review the full "
        "transcript and this report within 24 hours. (2) Consider temporarily "
        "limiting the flagged participant's access pending review. (3) Document "
        "actions taken in accordance with safeguarding procedures. (4) Notify the "
        "designated safeguarding lead."
    ),
    "moderate": (
        "REVIEW RECOMMENDED: (1) A safety team member should review the full "
        "transcript within 72 hours. (2) Monitor subsequent sessions from the same "
        "participants for escalation patterns. (3) Consider contacting the parent "
        "or guardian for awareness. (4) Document the review outcome."
    ),
    "low": (
        "MONITORING ADVISED: (1) Log this alert for pattern-tracking purposes. "
        "(2) Flag the participant for enhanced monitoring in future sessions. "
        "(3) No immediate intervention is required, but a brief review of the "
        "transcript is recommended at next opportunity."
    ),
    "safe": (
        "No action required. Record retained for compliance purposes."
    ),
}


# ── Helper utilities ──────────────────────────────────────────────────────────

def _divider(char: str = "─", width: int = 60) -> str:
    return char * width


def _fmt_confidence(conf: float) -> str:
    pct = conf * 100
    if pct >= 85:
        return f"{pct:.0f}% (HIGH)"
    if pct >= 60:
        return f"{pct:.0f}% (MODERATE)"
    return f"{pct:.0f}% (LOW)"


def _speaker_summary(findings: List[Dict[str, Any]]) -> Optional[str]:
    """Return a speaker breakdown string if speaker data is available."""
    speaker_counts: Dict[str, int] = {}
    for f in findings:
        spk = f.get("speaker")
        if spk:
            speaker_counts[spk] = speaker_counts.get(spk, 0) + 1
    if not speaker_counts:
        return None
    lines = []
    for spk, cnt in sorted(speaker_counts.items(), key=lambda x: x[1], reverse=True):
        lines.append(f"  • {spk}: {cnt} finding(s)")
    return "\n".join(lines)


def _escalation_note(findings: List[Dict[str, Any]], total_words: int) -> Optional[str]:
    """
    Detect temporal escalation: compare finding density in first vs second
    half of the transcript.
    """
    if not findings or total_words < 50:
        return None

    mid = total_words // 2
    # Use word-position proxy: split findings by timestamp if available,
    # else by position in list
    timed = [f for f in findings if f.get("timestamp") is not None]
    if timed:
        max_ts = max(f["timestamp"] for f in timed)
        if max_ts <= 0:
            return None
        mid_ts = max_ts / 2
        first_half  = [f for f in timed if f.get("timestamp", 0) <= mid_ts]
        second_half = [f for f in timed if f.get("timestamp", 0)  > mid_ts]
    else:
        mid_idx = len(findings) // 2
        first_half  = findings[:mid_idx]
        second_half = findings[mid_idx:]

    if not first_half and not second_half:
        return None

    first_density  = len(first_half)
    second_density = len(second_half)

    if second_density > first_density * 1.5 and second_density >= 3:
        return (
            f"⚠  ESCALATION DETECTED: Finding density increased significantly in the "
            f"second half of the conversation ({first_density} findings in first half → "
            f"{second_density} in second half). This pattern is consistent with "
            f"progressive boundary-pushing behaviour."
        )
    return None


def _high_confidence_findings(
    findings: List[Dict[str, Any]],
    threshold: float = 0.75,
) -> List[Dict[str, Any]]:
    return [
        f for f in findings
        if (f.get("confidence") or f.get("max_confidence") or 0) >= threshold
    ]


def _sort_findings(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Sort by confidence desc, then timestamp asc."""
    return sorted(
        findings,
        key=lambda f: (
            -(f.get("confidence") or f.get("max_confidence") or 0),
            f.get("timestamp") or 0,
        ),
    )


# ── Main generator ────────────────────────────────────────────────────────────

def generate_summary(
    transcript: str,
    findings: List[Dict[str, Any]],
    score: float,
    severity: str,
) -> str:
    """
    Generate a rich, structured rule-based safety summary.

    Returns a multi-section text report suitable for emails, PDFs,
    and the chatbot knowledge base.
    """
    sev_lower = (severity or "safe").lower()
    total_words = len(transcript.split()) if transcript else 0
    total_chars = len(transcript) if transcript else 0
    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    # ── Categorise findings ──────────────────────────────────────────
    all_cats: Dict[str, List[Dict]] = {}
    for f in findings:
        cats = (
            f.get("categories")
            or ([f["category"]] if f.get("category") else [])
            or ([f["type"]] if f.get("type") else [])
        )
        for cat in cats:
            if cat:
                all_cats.setdefault(cat, []).append(f)

    sorted_findings = _sort_findings(findings)
    high_conf = _high_confidence_findings(findings)
    escalation = _escalation_note(findings, total_words)

    # ── Build report ─────────────────────────────────────────────────
    lines: List[str] = []

    # Header
    lines += [
        _divider("═"),
        "  MELODYWINGS SAFETY ANALYSIS REPORT",
        f"  Generated: {now_str}",
        _divider("═"),
        "",
    ]

    # ── Section 1: Overview ──────────────────────────────────────────
    lines += [
        "SECTION 1 — OVERVIEW",
        _divider(),
        f"  Overall Severity   : {severity.upper()}",
        f"  Risk Score         : {score:.1f} / 100",
        f"  Total Words        : {total_words:,}",
        f"  Total Findings     : {len(findings)}",
        f"  High-Conf Findings : {len(high_conf)} (≥75% confidence)",
        f"  Categories Detected: {len(all_cats)}",
        "",
    ]

    # Category breakdown table
    if all_cats:
        lines.append("  Category Breakdown:")
        for cat, cat_findings in sorted(
            all_cats.items(),
            key=lambda x: len(x[1]),
            reverse=True,
        ):
            avg_conf = (
                sum(f.get("confidence") or f.get("max_confidence") or 0 for f in cat_findings)
                / len(cat_findings)
            )
            max_conf = max(
                f.get("confidence") or f.get("max_confidence") or 0
                for f in cat_findings
            )
            lines.append(
                f"    ▸ {_cat_label(cat):<40} "
                f"Count: {len(cat_findings):>3}  "
                f"Avg Conf: {avg_conf*100:.0f}%  "
                f"Max: {max_conf*100:.0f}%"
            )
    else:
        lines.append("  No suspicious categories detected.")
    lines.append("")

    # ── Section 2: Executive Summary ────────────────────────────────
    lines += [
        "SECTION 2 — EXECUTIVE SUMMARY",
        _divider(),
        "",
    ]
    exec_text = _EXEC_SUMMARY.get(sev_lower, _EXEC_SUMMARY["safe"])
    # Wrap at ~72 chars
    for para in exec_text.split("\n"):
        wrapped = _wrap_text(para.strip(), 72, "  ")
        lines.append(wrapped)
    lines.append("")

    # ── Section 3: Key Concerns ──────────────────────────────────────
    lines += [
        "SECTION 3 — KEY CONCERNS",
        _divider(),
        "",
    ]

    if not findings:
        lines.append("  No concerns detected.")
    else:
        concern_shown = 0
        for cat, cat_findings in sorted(
            all_cats.items(),
            key=lambda x: max(
                f.get("confidence") or f.get("max_confidence") or 0
                for f in x[1]
            ),
            reverse=True,
        ):
            best = max(
                cat_findings,
                key=lambda f: f.get("confidence") or f.get("max_confidence") or 0,
            )
            conf = best.get("confidence") or best.get("max_confidence") or 0
            evidence_snippet = (best.get("evidence") or best.get("text") or "")[:100]
            ellip = "…" if len(best.get("evidence") or best.get("text") or "") > 100 else ""
            sev_tag = (best.get("severity") or "").upper()

            lines += [
                f"  [{sev_tag}] {_cat_label(cat)}",
                f"    Confidence: {_fmt_confidence(conf)}",
                f"    Example   : \"{evidence_snippet}{ellip}\"",
                "",
            ]
            concern_shown += 1

    # Escalation warning
    if escalation:
        lines += ["", f"  {escalation}", ""]

    # ── Section 4: Detailed Evidence Log ────────────────────────────
    lines += [
        "SECTION 4 — DETAILED EVIDENCE LOG",
        _divider(),
        f"  Showing top {min(15, len(sorted_findings))} findings "
        f"(sorted by confidence):",
        "",
    ]

    if not sorted_findings:
        lines.append("  No findings to display.")
    else:
        for i, item in enumerate(sorted_findings[:15], 1):
            cats = (
                item.get("categories")
                or ([item["category"]] if item.get("category") else [])
                or ([item["type"]] if item.get("type") else ["unknown"])
            )
            cat_str = ", ".join(_cat_label(c) for c in cats)
            conf = item.get("confidence") or item.get("max_confidence") or 0
            ts   = item.get("timestamp")
            sev_tag = (item.get("severity") or "").upper()
            ctx  = item.get("context_type", "")
            speaker = item.get("speaker", "")
            evidence = item.get("evidence") or item.get("text") or ""

            ts_str = f"{ts:.1f}s" if ts is not None else "N/A"
            spk_str = f" | Speaker: {speaker}" if speaker else ""
            ctx_str = f" | Context: {ctx}" if ctx else ""

            lines += [
                f"  [{i:02d}] {cat_str}",
                f"       Severity  : {sev_tag}",
                f"       Confidence: {_fmt_confidence(conf)}",
                f"       Timestamp : {ts_str}{spk_str}{ctx_str}",
                f"       Evidence  : \"{evidence[:150]}{'…' if len(evidence) > 150 else ''}\"",
                "",
            ]

        if len(findings) > 15:
            lines.append(
                f"  ... and {len(findings) - 15} additional finding(s) not shown above."
            )
    lines.append("")

    # ── Section 5: Risk Assessment ───────────────────────────────────
    lines += [
        "SECTION 5 — RISK ASSESSMENT",
        _divider(),
        "",
    ]
    risk_text = _RISK_ASSESSMENT.get(sev_lower, _RISK_ASSESSMENT["safe"]).format(score=f"{score:.1f}")
    lines.append(_wrap_text(risk_text, 72, "  "))
    lines.append("")

    # Speaker analysis
    spk_summary = _speaker_summary(findings)
    if spk_summary:
        lines += [
            "  Speaker Breakdown:",
            spk_summary,
            "",
        ]

    # Confidence distribution
    if findings:
        conf_vals = [
            f.get("confidence") or f.get("max_confidence") or 0
            for f in findings
        ]
        avg_c = sum(conf_vals) / len(conf_vals)
        max_c = max(conf_vals)
        min_c = min(conf_vals)
        lines += [
            "  Confidence Distribution:",
            f"    Average : {avg_c*100:.1f}%",
            f"    Maximum : {max_c*100:.1f}%",
            f"    Minimum : {min_c*100:.1f}%",
            "",
        ]

    # ── Section 6: Recommended Action ───────────────────────────────
    lines += [
        "SECTION 6 — RECOMMENDED ACTION",
        _divider(),
        "",
    ]
    rec_text = _RECOMMENDATION.get(sev_lower, _RECOMMENDATION["safe"])
    for step in rec_text.split(". ("):
        if step:
            # Re-add the delimiter except for first item
            pass
    lines.append(_wrap_text(rec_text, 72, "  "))
    lines.append("")

    # Footer
    lines += [
        _divider("═"),
        "  This report was generated by the MelodyWings automated safety",
        "  monitoring system. It should be reviewed by a qualified safeguarding",
        "  professional before any action is taken.",
        _divider("═"),
    ]

    return "\n".join(lines)


# ── Text wrapping helper ──────────────────────────────────────────────────────

def _wrap_text(text: str, width: int = 72, indent: str = "") -> str:
    """Simple word-wrap with indent."""
    if not text:
        return indent
    words = text.split()
    lines: List[str] = []
    current = indent
    for word in words:
        if len(current) + len(word) + 1 > width:
            lines.append(current)
            current = indent + word
        else:
            current = (current + " " + word).strip()
            if current == word:
                current = indent + word
    if current.strip():
        lines.append(current)
    return "\n".join(lines)
