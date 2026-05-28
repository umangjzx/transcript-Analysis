"""
Analytics Routes
================
Prefix: /api/v1

Endpoints:
  GET  /analytics/summary  → aggregate analytics across all meetings
  POST /analytics/insights → LLM-generated explanation of analytics data
"""

import logging
import json

from fastapi import APIRouter, Depends

from auth import get_current_user
from database.mongo import get_analytics_summary as mongo_analytics
from modules.cache import TTLCache

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/v1",
    tags=["Analytics"],
)

_cache = TTLCache(ttl=60, name="analytics_routes")
_insights_cache = TTLCache(ttl=300, name="analytics_insights")  # 5 min cache for LLM insights


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
    Generate LLM-powered insights explaining the analytics data.
    Uses Ollama (Llama 3.1 — same model as the chatbot) to produce a
    natural-language summary of:
    - Overall system health and risk posture
    - What each chart/metric tells the analyst
    - Actionable recommendations

    Results are cached for 5 minutes to avoid repeated LLM calls.
    """
    # Check cache first
    cached = _insights_cache.get("insights")
    if cached is not None:
        return cached

    # Get fresh analytics data
    analytics = mongo_analytics()

    if not analytics or analytics.get("total_reports", 0) == 0:
        return {
            "insights": "No analysis data available yet. Upload and analyze some files to generate insights.",
            "cached": False,
        }

    # Build a structured data summary for the LLM
    data_summary = _build_data_summary(analytics)

    # Call LLM (same direct path the chatbot uses — no circuit breaker so
    # a transient failure on a single insights call doesn't trip a breaker
    # that the chatbot also depends on).
    try:
        import ollama

        prompt = f"""You are a senior child safety analyst reviewing aggregate analytics from an audio/text grooming detection system called "Melody Wings Safety".

Below is the current analytics data from the system. Provide a clear, professional analysis that:

1. **Overall Summary** — A 2-3 sentence executive overview of the system's current state and risk posture.

2. **Key Metrics Explained** — For each major metric, explain what it means in plain language:
   - Total reports analyzed and what the volume suggests
   - Risk score distribution and what it tells us
   - Severity breakdown and areas of concern
   - Top risk categories and their significance
   - ML vs Regex agreement rate and what disagreements mean
   - Detection confidence levels and reliability

3. **Trends & Patterns** — Any notable patterns or trends visible in the data.

4. **Recommendations** — 2-3 actionable recommendations for the analyst team based on this data.

Keep the tone professional but accessible. Use bullet points for clarity. Be specific with numbers from the data.

--- ANALYTICS DATA ---
{data_summary}
--- END DATA ---

Respond in well-formatted markdown with headers (##) for each section."""

        response = ollama.chat(
            model="llama3.1",
            messages=[{"role": "user", "content": prompt}],
        )
        insights_text = response["message"]["content"]

        result = {"insights": insights_text, "cached": False}
        _insights_cache.set("insights", result)
        return result

    except Exception as e:
        logger.warning(f"Analytics insights LLM call failed: {e}")
        # Fallback: generate a basic rule-based summary
        fallback = _generate_fallback_insights(analytics)
        return {"insights": fallback, "cached": False, "fallback": True}


def _build_data_summary(analytics: dict) -> str:
    """Build a compact text representation of analytics for the LLM prompt."""
    lines = []
    lines.append(f"Total Reports Analyzed: {analytics.get('total_reports', 0)}")
    lines.append(f"Total Findings Detected: {analytics.get('total_findings', 0)}")
    lines.append(f"Average Risk Score: {analytics.get('avg_risk_score', 0):.1f}/100")
    lines.append(f"High Confidence Detections (≥75%): {analytics.get('high_confidence_count', 0)}")

    sev = analytics.get("severity_distribution", {})
    if sev:
        lines.append(f"\nSeverity Distribution:")
        for k, v in sorted(sev.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  - {k}: {v} reports")

    status = analytics.get("status_distribution", {})
    if status:
        lines.append(f"\nProcessing Status:")
        for k, v in status.items():
            lines.append(f"  - {k}: {v}")

    risk_hist = analytics.get("risk_score_histogram", {})
    if risk_hist:
        lines.append(f"\nRisk Score Histogram:")
        for k, v in risk_hist.items():
            lines.append(f"  - Score {k}: {v} reports")

    cats = analytics.get("top_categories", [])
    if cats:
        lines.append(f"\nTop Risk Categories (by occurrence):")
        for c in cats[:10]:
            lines.append(f"  - {c['category']}: {c['count']} occurrences")

    ctx = analytics.get("context_type_totals", {})
    if ctx:
        lines.append(f"\nContext Type Distribution:")
        for k, v in sorted(ctx.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  - {k}: {v}")

    ml = analytics.get("ml_agreement_totals", {})
    if ml and ml.get("total", 0) > 0:
        lines.append(f"\nML Classifier Agreement:")
        lines.append(f"  - Agreed with regex: {ml.get('agreed', 0)}")
        lines.append(f"  - Disagreed: {ml.get('disagreed', 0)}")
        lines.append(f"  - Total ML evaluations: {ml.get('total', 0)}")
        if ml.get("rate") is not None:
            lines.append(f"  - Agreement rate: {ml['rate']*100:.1f}%")

    conf = analytics.get("confidence_histogram", {})
    if conf:
        lines.append(f"\nConfidence Distribution:")
        for k, v in conf.items():
            lines.append(f"  - {k}%: {v} reports")

    return "\n".join(lines)


def _generate_fallback_insights(analytics: dict) -> str:
    """Generate basic rule-based insights when LLM is unavailable."""
    total = analytics.get("total_reports", 0)
    findings = analytics.get("total_findings", 0)
    avg_risk = analytics.get("avg_risk_score", 0)
    high_conf = analytics.get("high_confidence_count", 0)
    sev = analytics.get("severity_distribution", {})

    critical = sev.get("Critical", 0)
    high = sev.get("High", 0)

    lines = [
        "## Overall Summary",
        f"The system has analyzed **{total} reports** with an average risk score of **{avg_risk:.1f}/100**. ",
        f"A total of **{findings} findings** have been detected across all analyses.",
        "",
        "## Key Observations",
    ]

    if critical + high > 0:
        lines.append(f"- ⚠️ **{critical + high} reports** flagged as High or Critical severity — these require immediate review.")
    if avg_risk > 60:
        lines.append(f"- The average risk score of {avg_risk:.1f} is elevated, suggesting a high proportion of concerning content.")
    elif avg_risk < 25:
        lines.append(f"- The average risk score of {avg_risk:.1f} is low, indicating most analyzed content is safe.")

    if high_conf > 0:
        lines.append(f"- **{high_conf} high-confidence detections** (≥75%) indicate strong pattern matches.")

    ml = analytics.get("ml_agreement_totals", {})
    if ml.get("rate") is not None:
        rate = ml["rate"] * 100
        if rate < 70:
            lines.append(f"- ML agreement rate is **{rate:.0f}%** — significant disagreements suggest reviewing flagged items manually.")
        else:
            lines.append(f"- ML agreement rate is **{rate:.0f}%** — good consistency between detection methods.")

    lines.append("")
    lines.append("## Recommendations")
    lines.append("- Review all Critical and High severity reports promptly.")
    lines.append("- Monitor the risk score trend for any upward patterns.")
    lines.append("- Investigate ML disagreements to improve detection accuracy.")
    lines.append("")
    lines.append("*Note: LLM-powered insights are unavailable. This is a rule-based summary.*")

    return "\n".join(lines)
