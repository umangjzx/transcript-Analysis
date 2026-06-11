"""
Analytics Routes
================
Prefix: /api/v1

Endpoints:
  GET  /analytics/summary  → aggregate analytics across all meetings
  POST /analytics/insights → rich rule-based + LLM-enhanced insights
"""

import logging
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends

from auth import get_current_user
from database.mongo import get_analytics_summary as mongo_analytics
from modules.cache import TTLCache

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Analytics"],
)

_cache          = TTLCache(ttl=60,  name="analytics_routes")
_insights_cache = TTLCache(ttl=300, name="analytics_insights")   # 5-min LLM cache


# ── Category display names (mirrors summarizer) ───────────────────────────────

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


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/analytics/summary")
def get_analytics_summary(current_user: dict = Depends(get_current_user)):
    """Aggregate analytics with TTL cache — reads from MongoDB."""
    cached = _cache.get("analytics")
    if cached is not None:
        return cached
    result = mongo_analytics()
    _cache.set("analytics", result)
    return result


@router.post("/analytics/insights")
def get_analytics_insights(current_user: dict = Depends(get_current_user)):
    """
    Generate rich analytics insights.

    Strategy:
      1. Always compute a full rule-based analysis (instant, no LLM needed).
      2. If Ollama is available, enhance with an LLM narrative layer on top.
      3. Cache the combined result for 5 minutes.

    The rule-based layer covers:
      - Overall risk posture with severity band interpretation
      - Per-metric deep-dives (score distribution, category breakdown,
        ML agreement, confidence, volume trends)
      - Anomaly detection (dominant categories, confidence gaps, failure rate)
      - Severity escalation signals
      - Tiered actionable recommendations
    """
    cached = _insights_cache.get("insights")
    if cached is not None:
        return cached

    analytics = mongo_analytics()

    if not analytics or analytics.get("total_reports", 0) == 0:
        return {
            "insights": (
                "## No Data Available\n\n"
                "No analysis reports have been processed yet. "
                "Upload and analyze some session files to generate insights."
            ),
            "cached": False,
        }

    # ── 1. Build rich rule-based insights (always run) ───────────────
    rule_insights = _build_rule_insights(analytics)

    # ── 2. Try LLM enhancement ───────────────────────────────────────
    try:
        import ollama
        data_summary = _build_llm_data_block(analytics, rule_insights)

        # Sanitize data before injecting into LLM prompt to prevent prompt injection.
        # Strip markdown fences, instruction-like markers, and excessive length.
        def _sanitize_for_llm(text: str, max_len: int = 2000) -> str:
            """Remove content that could be interpreted as injected instructions."""
            sanitized = text[:max_len]
            # Remove markdown code fences and horizontal rules
            sanitized = sanitized.replace("```", "")
            sanitized = sanitized.replace("---", "")
            # Remove lines that look like injected instructions
            lines = sanitized.split("\n")
            lines = [
                ln for ln in lines
                if not ln.strip().lower().startswith(("ignore", "forget", "you are now", "system:"))
            ]
            return "\n".join(lines)

        safe_rule_insights = _sanitize_for_llm(rule_insights, 2000)
        safe_data_summary = _sanitize_for_llm(data_summary, 1500)

        prompt = f"""You are a senior child safeguarding analyst reviewing aggregate system analytics for "MelodyWings Safety", an automated grooming-detection platform.

A rule-based analysis has already been computed (shown below). Your job is to:
1. Write a **2-paragraph executive narrative** that synthesises the most important signals into plain language a non-technical safeguarding manager can act on.
2. Identify **1-2 patterns or anomalies** that the rule-based analysis may have missed.
3. Add **2 specific recommendations** grounded in the data.

Keep the total response under 250 words. Use ## headers. Be direct and specific — cite numbers.

--- RULE-BASED ANALYSIS ---
{safe_rule_insights}
--- END ---

--- RAW METRICS ---
{safe_data_summary}
--- END ---

Respond in markdown. Do NOT repeat statistics already obvious from the rule-based section above — add interpretation and insight."""

        response = ollama.chat(
            model="llama3.1",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.3, "num_predict": 400},
        )
        llm_addition = response["message"]["content"].strip()

        combined = (
            rule_insights
            + "\n\n---\n\n"
            + "## 🤖 AI Analyst Commentary\n\n"
            + llm_addition
        )
        result = {"insights": combined, "cached": False, "llm_enhanced": True}

    except Exception as e:
        logger.warning(f"Analytics LLM enhancement failed (using rule-based only): {e}")
        result = {
            "insights": rule_insights,
            "cached": False,
            "llm_enhanced": False,
            "llm_error": str(e),
        }

    _insights_cache.set("insights", result)
    return result


# ── Rule-based insights engine ────────────────────────────────────────────────

def _build_rule_insights(a: dict) -> str:
    """
    Build a comprehensive, structured rule-based insights report.
    Reads every field from the analytics summary and produces analyst-grade output.
    """
    total        = a.get("total_reports", 0)
    total_find   = a.get("total_findings", 0)
    avg_risk     = a.get("avg_risk_score", 0) or 0
    high_conf    = a.get("high_confidence_count", 0)
    sev          = a.get("severity_distribution", {})
    risk_hist    = a.get("risk_score_histogram", {})
    top_cats     = a.get("top_categories", [])
    ctx_totals   = a.get("context_type_totals", {})
    ml           = a.get("ml_agreement_totals", {})
    conf_hist    = a.get("confidence_histogram", {})
    status_dist  = a.get("status_distribution", {})

    now_str = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")

    lines: List[str] = []

    # ── Header ───────────────────────────────────────────────────────
    lines += [
        f"## 📊 Analytics Insights Report",
        f"*Generated {now_str} · {total} report(s) in database*",
        "",
    ]

    # ── Section 1: Overall Risk Posture ──────────────────────────────
    lines.append("## Overall Risk Posture")
    posture, posture_detail = _risk_posture(avg_risk, sev, total)
    lines += [
        f"**Risk Level: {posture}**",
        "",
        posture_detail,
        "",
    ]

    # Score band breakdown
    critical_n = sev.get("Critical", 0)
    high_n     = sev.get("High", 0)
    moderate_n = sev.get("Moderate", 0)
    low_n      = sev.get("Low", 0)
    safe_n     = sev.get("Safe", 0)
    danger_n   = critical_n + high_n

    def pct(n: int) -> str:
        """Format n as a percentage of total reports."""
        return f"{(n/total*100):.0f}%" if total else "0%"

    lines += [
        "**Severity Breakdown:**",
        f"- 🔴 Critical: **{critical_n}** ({pct(critical_n)})",
        f"- 🟠 High: **{high_n}** ({pct(high_n)})",
        f"- 🟡 Moderate: **{moderate_n}** ({pct(moderate_n)})",
        f"- 🔵 Low: **{low_n}** ({pct(low_n)})",
        f"- 🟢 Safe: **{safe_n}** ({pct(safe_n)})",
        "",
    ]

    if danger_n > 0:
        lines.append(
            f"⚠️ **{danger_n} session(s) ({pct(danger_n)}) require immediate attention** "
            f"(High or Critical severity)."
        )
        lines.append("")

    # ── Section 2: Risk Score Distribution ───────────────────────────
    lines.append("## Risk Score Distribution")
    lines += [_risk_histogram_narrative(risk_hist, total, avg_risk), ""]

    # ── Section 3: Detection Categories ──────────────────────────────
    lines.append("## Top Detected Risk Categories")
    if top_cats:
        total_cat_hits = sum(c["count"] for c in top_cats)
        lines.append(
            f"**{total_cat_hits} total category hits** across {len(top_cats)} distinct "
            f"category type(s).\n"
        )
        dominant = top_cats[0] if top_cats else None
        if dominant and dominant["count"] > 0:
            dom_pct = (dominant["count"] / total_cat_hits * 100) if total_cat_hits else 0
            lines.append(
                f"The most frequently detected category is "
                f"**{_cat_label(dominant['category'])}** with **{dominant['count']} "
                f"occurrence(s)** ({dom_pct:.0f}% of all category hits). "
                + _category_significance(dominant["category"])
            )
            lines.append("")

        lines.append("**Full breakdown:**")
        for i, cat in enumerate(top_cats[:10]):
            pct_of_total = (cat["count"] / total_cat_hits * 100) if total_cat_hits else 0
            severity_tag = _category_risk_tag(cat["category"])
            lines.append(
                f"- {severity_tag} **{_cat_label(cat['category'])}** — "
                f"{cat['count']} hits ({pct_of_total:.0f}%)"
            )
        if len(top_cats) > 10:
            lines.append(f"- *...and {len(top_cats) - 10} more categories*")
    else:
        lines.append("No category data available.")
    lines.append("")

    # ── Section 4: Detection Confidence ──────────────────────────────
    lines.append("## Detection Confidence")
    lines += [_confidence_narrative(conf_hist, high_conf, total), ""]

    # ── Section 5: ML vs Rule Agreement ──────────────────────────────
    lines.append("## ML Classifier vs Rule-Based Agreement")
    lines += [_ml_agreement_narrative(ml), ""]

    # ── Section 6: Context Type Analysis ─────────────────────────────
    if ctx_totals:
        lines.append("## Context Type Distribution")
        lines += [_context_narrative(ctx_totals), ""]

    # ── Section 7: Processing Health ─────────────────────────────────
    lines.append("## Processing Health")
    lines += [_processing_health_narrative(status_dist, total), ""]

    # ── Section 8: Anomalies & Signals ───────────────────────────────
    anomalies = _detect_anomalies(a)
    if anomalies:
        lines.append("## ⚡ Anomalies & Signals")
        for anomaly in anomalies:
            lines.append(f"- {anomaly}")
        lines.append("")

    # ── Section 9: Recommendations ───────────────────────────────────
    lines.append("## Recommended Actions")
    lines += _build_recommendations(a)
    lines.append("")

    return "\n".join(lines)


# ── Narrative helpers ─────────────────────────────────────────────────────────

def _risk_posture(
    avg_risk: float,
    sev: dict,
    total: int,
) -> tuple:
    """Return (posture_label, posture_detail_string)."""
    critical = sev.get("Critical", 0)
    high     = sev.get("High", 0)
    danger   = critical + high
    danger_pct = danger / total if total else 0

    if avg_risk >= 70 or danger_pct >= 0.3:
        label = "🔴 ELEVATED — Immediate Review Required"
        detail = (
            f"The system is in an **elevated risk state**. The average risk score of "
            f"**{avg_risk:.1f}/100** and the proportion of High/Critical sessions "
            f"({danger_pct*100:.0f}%) indicate a significant volume of potentially "
            f"harmful interactions that require prompt attention from the safety team."
        )
    elif avg_risk >= 45 or danger_pct >= 0.1:
        label = "🟡 MODERATE — Active Monitoring Recommended"
        detail = (
            f"The system is at a **moderate risk level**. An average score of "
            f"**{avg_risk:.1f}/100** with {danger_pct*100:.0f}% of sessions flagged "
            f"as High/Critical suggests meaningful risk activity. Regular review of "
            f"flagged sessions is recommended."
        )
    elif avg_risk >= 20:
        label = "🔵 LOW — Routine Monitoring"
        detail = (
            f"The system is at a **low risk level**. The average score of "
            f"**{avg_risk:.1f}/100** reflects predominantly safe interactions with "
            f"occasional low-level flags. Routine monitoring is sufficient at this time."
        )
    else:
        label = "🟢 SAFE — System Normal"
        detail = (
            f"The system is in a **normal, low-risk state**. An average score of "
            f"**{avg_risk:.1f}/100** across {total} session(s) suggests the platform "
            f"is operating within expected safe parameters."
        )
    return label, detail


def _risk_histogram_narrative(hist: dict, total: int, avg: float) -> str:
    if not hist or total == 0:
        return "Insufficient data to analyse risk score distribution."

    safe_low  = (hist.get("0-20", 0) + hist.get("21-40", 0))
    danger    = (hist.get("61-80", 0) + hist.get("81-100", 0))
    mid       = hist.get("41-60", 0)

    lines = []
    lines.append(
        f"Average risk score: **{avg:.1f}/100**. "
        f"Distribution across {total} report(s):"
    )
    for band, count in hist.items():
        bar = "█" * min(20, int((count / total) * 20)) if total else ""
        pct = count / total * 100 if total else 0
        label = {
            "0-20":   "Safe",
            "21-40":  "Low",
            "41-60":  "Moderate",
            "61-80":  "High",
            "81-100": "Critical",
        }.get(band, band)
        lines.append(f"- **{band}** ({label}): {count} session(s) ({pct:.0f}%) {bar}")

    if danger > safe_low:
        lines.append(
            f"\n⚠️ The distribution is **skewed toward higher risk scores** — "
            f"{danger} session(s) score above 60, compared to {safe_low} below 40."
        )
    return "\n".join(lines)


def _confidence_narrative(conf_hist: dict, high_conf: int, total: int) -> str:
    if not conf_hist:
        return "No confidence distribution data available."

    total_findings = sum(conf_hist.values())
    high_pct = (conf_hist.get("75-100", 0) / total_findings * 100) if total_findings else 0
    low_pct  = (conf_hist.get("0-25", 0)   / total_findings * 100) if total_findings else 0

    lines = []
    lines.append(
        f"**{high_conf} high-confidence detection(s)** (≥75%) recorded across all reports."
    )
    for band, count in conf_hist.items():
        pct = count / total_findings * 100 if total_findings else 0
        bar = "█" * min(20, int(pct / 5))
        lines.append(f"- **{band}%**: {count} report(s) ({pct:.0f}%) {bar}")

    if high_pct >= 50:
        lines.append(
            f"\n✅ **{high_pct:.0f}% of detections fall in the high-confidence tier** — "
            f"strong signal quality, low false-positive risk."
        )
    elif low_pct >= 40:
        lines.append(
            f"\n⚠️ **{low_pct:.0f}% of detections are low-confidence** — "
            f"these may include false positives and should be reviewed carefully."
        )
    return "\n".join(lines)


def _ml_agreement_narrative(ml: dict) -> str:
    total   = ml.get("total", 0)
    agreed  = ml.get("agreed", 0)
    disag   = ml.get("disagreed", 0)
    rate    = ml.get("rate")

    if total == 0:
        return (
            "No ML classifier data available. "
            "ML classification may be disabled (`ENABLE_ML_CLASSIFIER=false`)."
        )

    no_signal = total - agreed - disag
    rate_pct  = rate * 100 if rate is not None else 0

    lines = [
        f"ML classifier evaluated **{total} finding(s)**:",
        f"- ✅ Agreed with rule-based detection: **{agreed}** ({agreed/total*100:.0f}%)",
        f"- ❌ Disagreed: **{disag}** ({disag/total*100:.0f}%)",
    ]
    if no_signal > 0:
        lines.append(f"- ⬜ No ML signal: **{no_signal}** ({no_signal/total*100:.0f}%)")

    if rate_pct >= 80:
        lines.append(
            f"\n✅ **Agreement rate: {rate_pct:.1f}%** — excellent consistency "
            f"between the ML model and rule-based patterns."
        )
    elif rate_pct >= 60:
        lines.append(
            f"\n🟡 **Agreement rate: {rate_pct:.1f}%** — moderate consistency. "
            f"The {disag} disagreements warrant manual review to identify "
            f"false positives or missed detections."
        )
    else:
        lines.append(
            f"\n🔴 **Agreement rate: {rate_pct:.1f}%** — significant disagreement "
            f"between the ML model and rule-based patterns. "
            f"Consider retraining the classifier or reviewing detection rules."
        )
    return "\n".join(lines)


def _context_narrative(ctx: dict) -> str:
    if not ctx:
        return "No context type data available."
    total = sum(ctx.values())
    grooming = ctx.get("GROOMING", 0)
    neutral  = ctx.get("NEUTRAL", 0)

    lines = []
    for ctx_type, count in sorted(ctx.items(), key=lambda x: x[1], reverse=True):
        pct = count / total * 100 if total else 0
        lines.append(f"- **{ctx_type}**: {count} finding(s) ({pct:.0f}%)")

    if grooming > neutral and total > 0:
        g_pct = grooming / total * 100
        lines.append(
            f"\n⚠️ **{g_pct:.0f}% of findings are classified as GROOMING context** "
            f"— the system is detecting substantive threat indicators, not just "
            f"ambiguous language."
        )
    return "\n".join(lines)


def _processing_health_narrative(status_dist: dict, total: int) -> str:
    if not status_dist:
        return "No processing status data available."

    completed  = status_dist.get("COMPLETED", 0)
    processing = status_dist.get("PROCESSING", 0)
    failed     = status_dist.get("FAILED", 0)
    total_s    = sum(status_dist.values()) or 1

    lines = [
        f"- ✅ Completed: **{completed}** ({completed/total_s*100:.0f}%)",
        f"- ⏳ Processing: **{processing}** ({processing/total_s*100:.0f}%)",
        f"- ❌ Failed: **{failed}** ({failed/total_s*100:.0f}%)",
    ]

    if failed / total_s > 0.1:
        lines.append(
            f"\n⚠️ **{failed} failed job(s)** ({failed/total_s*100:.0f}%) detected. "
            f"Check backend logs for transcription or pipeline errors."
        )
    elif completed / total_s >= 0.95:
        lines.append(f"\n✅ Pipeline is healthy — {completed/total_s*100:.0f}% success rate.")

    return "\n".join(lines)


def _detect_anomalies(a: dict) -> List[str]:
    """Detect and surface notable anomalies from the analytics data."""
    anomalies = []
    sev       = a.get("severity_distribution", {})
    top_cats  = a.get("top_categories", [])
    ml        = a.get("ml_agreement_totals", {})
    conf_hist = a.get("confidence_histogram", {})
    total     = a.get("total_reports", 0)
    avg_risk  = a.get("avg_risk_score", 0) or 0
    risk_hist = a.get("risk_score_histogram", {})

    # High critical concentration
    critical = sev.get("Critical", 0)
    if total > 0 and critical / total > 0.2:
        anomalies.append(
            f"🔴 **High Critical concentration**: {critical} of {total} sessions "
            f"({critical/total*100:.0f}%) are Critical — significantly above normal."
        )

    # Dominant single category
    if top_cats:
        total_hits = sum(c["count"] for c in top_cats)
        if total_hits > 0:
            dom = top_cats[0]
            dom_pct = dom["count"] / total_hits * 100
            if dom_pct > 50:
                anomalies.append(
                    f"📌 **Category dominance**: '{_cat_label(dom['category'])}' accounts for "
                    f"{dom_pct:.0f}% of all hits — unusually concentrated pattern."
                )

    # Low ML agreement
    if ml.get("rate") is not None and ml["rate"] < 0.6 and ml.get("total", 0) > 10:
        anomalies.append(
            f"🤖 **ML/Rule disagreement**: Agreement rate is only {ml['rate']*100:.0f}% "
            f"— the classifier and rule patterns are diverging."
        )

    # Confidence gap — many high-risk but low-confidence detections
    low_conf = conf_hist.get("0-25", 0) + conf_hist.get("25-50", 0)
    high_risk = (risk_hist.get("61-80", 0) + risk_hist.get("81-100", 0))
    if high_risk > 0 and low_conf > high_risk * 0.5:
        anomalies.append(
            f"⚠️ **Confidence gap**: High-risk scores alongside many low-confidence detections "
            f"({low_conf} reports) — potential false positive inflation."
        )

    # All safe but high findings count
    total_find = a.get("total_findings", 0)
    safe_n = sev.get("Safe", 0)
    if safe_n == total and total_find > 0:
        anomalies.append(
            f"ℹ️ **Findings in safe sessions**: {total_find} finding(s) detected across "
            f"{safe_n} safe-rated sessions — individual finding thresholds may be too lenient."
        )

    return anomalies


def _build_recommendations(a: dict) -> List[str]:
    """Generate tiered, data-driven recommendations."""
    recs = []
    sev       = a.get("severity_distribution", {})
    top_cats  = a.get("top_categories", [])
    ml        = a.get("ml_agreement_totals", {})
    status    = a.get("status_distribution", {})
    avg_risk  = a.get("avg_risk_score", 0) or 0
    total     = a.get("total_reports", 0)

    critical = sev.get("Critical", 0)
    high_n   = sev.get("High", 0)
    failed   = status.get("FAILED", 0)

    if critical > 0:
        recs.append(
            f"1. 🔴 **Immediately review {critical} Critical-severity session(s).** "
            f"Escalate to the designated safeguarding lead if not already done."
        )
    if high_n > 0:
        recs.append(
            f"{'2' if recs else '1'}. 🟠 **Prioritise {high_n} High-severity session(s)** "
            f"for manual review within 24 hours."
        )

    idx = len(recs) + 1
    if top_cats:
        top_cat = top_cats[0]["category"]
        recs.append(
            f"{idx}. 📋 **Focus detection review on '{_cat_label(top_cat)}'** "
            f"— the highest-frequency risk category. "
            f"Consider targeted rule refinements or additional training data for this pattern."
        )
        idx += 1

    if ml.get("rate") is not None and ml["rate"] < 0.75 and ml.get("total", 0) > 5:
        recs.append(
            f"{idx}. 🤖 **Investigate ML/rule disagreements** ({(1-ml['rate'])*100:.0f}% "
            f"disagreement rate). Review misclassified cases and consider "
            f"fine-tuning the ML classifier."
        )
        idx += 1

    if failed > 0:
        recs.append(
            f"{idx}. 🔧 **Resolve {failed} failed pipeline job(s).** "
            f"Check transcription service availability and backend error logs."
        )
        idx += 1

    if avg_risk < 15 and total >= 10:
        recs.append(
            f"{idx}. ✅ **System health check passed.** Average risk is low ({avg_risk:.1f}/100). "
            f"Continue routine monitoring and consider expanding analysis coverage."
        )

    if not recs:
        recs.append(
            "1. ✅ No immediate actions required. Continue routine monitoring."
        )

    return recs


def _category_significance(cat: str) -> str:
    """Return a one-sentence significance note for a category."""
    notes = {
        "meeting":              "Physical meeting requests are a strong grooming indicator requiring urgent review.",
        "secrecy":              "Secrecy instructions are a primary grooming tactic designed to evade parental detection.",
        "address":              "Location solicitation poses a direct physical safety risk.",
        "sexual_content":       "Sexual content in educational contexts represents a serious policy and safeguarding violation.",
        "manipulation":         "Psychological manipulation is a core grooming technique used to establish control.",
        "isolation":            "Isolation tactics aim to separate the child from protective adults.",
        "threat":               "Threats may indicate coercive control and require immediate escalation.",
        "self_harm":            "Self-harm discussions require immediate pastoral and safeguarding response.",
    }
    return notes.get(cat.lower(), "")


def _category_risk_tag(cat: str) -> str:
    """Return a risk emoji tag for a category."""
    high_risk = {"meeting", "secrecy", "address", "sexual_content", "manipulation",
                 "isolation", "threat", "self_harm", "contact_escalation"}
    medium_risk = {"trust_building", "personal_info", "desensitization",
                   "boundary_testing", "identity_probing"}
    c = cat.lower()
    if c in high_risk:   return "🔴"
    if c in medium_risk: return "🟡"
    return "🔵"


# ── Compact data block for LLM prompt ────────────────────────────────────────

def _build_llm_data_block(analytics: dict, rule_summary: str) -> str:
    """Build a compact metrics snapshot for the LLM prompt."""
    a = analytics
    lines = [
        f"total_reports={a.get('total_reports',0)}",
        f"total_findings={a.get('total_findings',0)}",
        f"avg_risk_score={a.get('avg_risk_score',0):.1f}",
        f"high_confidence_count={a.get('high_confidence_count',0)}",
    ]
    sev = a.get("severity_distribution", {})
    if sev:
        lines.append("severity=" + ", ".join(f"{k}:{v}" for k, v in sev.items()))

    top = a.get("top_categories", [])[:5]
    if top:
        lines.append("top_categories=" + ", ".join(
            f"{_cat_label(c['category'])}:{c['count']}" for c in top
        ))

    ml = a.get("ml_agreement_totals", {})
    if ml.get("total", 0) > 0:
        lines.append(f"ml_agreement_rate={ml.get('rate', 0)*100:.1f}%")

    status = a.get("status_distribution", {})
    if status:
        lines.append("processing=" + ", ".join(f"{k}:{v}" for k, v in status.items()))

    return "\n".join(lines)
