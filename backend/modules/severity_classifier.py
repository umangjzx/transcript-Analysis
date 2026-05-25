"""
Severity classifier — maps a 0–100 risk score to a 5-level label.

Levels (aligned with WeightedRiskScorer.RISK_LEVELS):
    Safe     :  0–20
    Low      : 21–40
    Moderate : 41–60
    High     : 61–80
    Critical : 81–100
"""


def classify_severity(score: float) -> str:
    """
    Classify a risk score (0–100) into a severity label.

    Args:
        score: Risk score between 0 and 100.

    Returns:
        One of: "Critical", "High", "Moderate", "Low", "Safe"
    """
    try:
        score = float(score)
    except (TypeError, ValueError):
        return "Safe"

    if score >= 81:
        return "Critical"
    if score >= 61:
        return "High"
    if score >= 41:
        return "Moderate"
    if score >= 21:
        return "Low"
    return "Safe"
