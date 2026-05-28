"""
Temporal Weighting for Risk Scoring.

Applies position-based weighting to findings based on where they appear
in the conversation timeline. Grooming patterns that appear later in a
conversation (after trust-building) are weighted higher than early ones.

Rationale:
- Early findings may be exploratory/testing boundaries
- Late findings after trust-building indicate escalation
- Clustered findings in a short window indicate active grooming phase

Weighting Curve:
- First 25% of conversation: 0.8x weight (early/exploratory)
- Middle 50%: 1.0x weight (baseline)
- Last 25%: 1.2x weight (escalation phase)

Additional bonuses:
- Clustering bonus: +0.15 if 3+ findings within 10% of conversation
- Escalation bonus: +0.20 if severity increases over time
"""

import logging
from typing import List, Dict, Any, Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────

# Position-based weight multipliers
EARLY_PHASE_MULTIPLIER = 0.8    # First 25% of conversation
MIDDLE_PHASE_MULTIPLIER = 1.0   # Middle 50%
LATE_PHASE_MULTIPLIER = 1.2     # Last 25% of conversation

# Clustering detection
CLUSTER_WINDOW_PERCENT = 0.10   # 10% of conversation length
CLUSTER_MIN_FINDINGS = 3        # Minimum findings to trigger cluster bonus
CLUSTER_BONUS = 0.15            # Bonus applied to clustered findings

# Escalation detection
ESCALATION_BONUS = 0.20         # Bonus when severity escalates over time


def apply_temporal_weighting(
    findings: List[Dict[str, Any]],
    total_sentences: int,
) -> List[Dict[str, Any]]:
    """
    Apply temporal weighting to findings based on their position in the conversation.

    Args:
        findings: List of finding dicts (must have 'timestamp' field = sentence index)
        total_sentences: Total number of sentences in the transcript

    Returns:
        Findings with updated confidence scores and temporal metadata.
    """
    if not findings or total_sentences <= 0:
        return findings

    # Sort by timestamp/position
    sorted_findings = sorted(findings, key=lambda f: f.get("timestamp", 0))

    # Calculate position-based weights
    for finding in sorted_findings:
        position = float(finding.get("timestamp", 0))
        relative_position = position / max(total_sentences, 1)

        # Determine phase multiplier
        if relative_position <= 0.25:
            phase_multiplier = EARLY_PHASE_MULTIPLIER
            phase = "early"
        elif relative_position <= 0.75:
            phase_multiplier = MIDDLE_PHASE_MULTIPLIER
            phase = "middle"
        else:
            phase_multiplier = LATE_PHASE_MULTIPLIER
            phase = "late"

        # Apply phase multiplier to confidence
        original_confidence = finding.get("confidence", 0.5)
        weighted_confidence = min(1.0, original_confidence * phase_multiplier)

        # Store temporal metadata
        finding["temporal"] = {
            "relative_position": round(relative_position, 3),
            "phase": phase,
            "phase_multiplier": phase_multiplier,
            "original_confidence": round(original_confidence, 4),
            "weighted_confidence": round(weighted_confidence, 4),
        }
        finding["confidence"] = round(weighted_confidence, 4)

    # Apply clustering bonus
    _apply_clustering_bonus(sorted_findings, total_sentences)

    # Apply escalation bonus
    _apply_escalation_bonus(sorted_findings, total_sentences)

    return sorted_findings


def _apply_clustering_bonus(
    findings: List[Dict[str, Any]],
    total_sentences: int,
) -> None:
    """
    Apply bonus to findings that are clustered together in a short window.
    Indicates an active grooming phase.
    """
    if len(findings) < CLUSTER_MIN_FINDINGS:
        return

    window_size = max(1, int(total_sentences * CLUSTER_WINDOW_PERCENT))

    # Sliding window to detect clusters
    for i, finding in enumerate(findings):
        pos = float(finding.get("timestamp", 0))
        # Count findings within the window
        cluster_count = sum(
            1 for f in findings
            if abs(float(f.get("timestamp", 0)) - pos) <= window_size
        )

        if cluster_count >= CLUSTER_MIN_FINDINGS:
            current_conf = finding.get("confidence", 0.5)
            boosted = min(1.0, current_conf + CLUSTER_BONUS)
            finding["confidence"] = round(boosted, 4)
            finding.setdefault("temporal", {})["cluster_bonus"] = CLUSTER_BONUS
            finding["temporal"]["cluster_size"] = cluster_count


def _apply_escalation_bonus(
    findings: List[Dict[str, Any]],
    total_sentences: int,
) -> None:
    """
    Apply bonus when severity escalates over time (later findings are more severe).
    """
    if len(findings) < 4:
        return

    severity_order = {"safe": 0, "low": 1, "moderate": 2, "medium": 2, "high": 3, "critical": 4}

    # Split into halves
    mid = len(findings) // 2
    first_half = findings[:mid]
    second_half = findings[mid:]

    # Average severity of each half
    def avg_severity(group):
        scores = [severity_order.get((f.get("severity") or "low").lower(), 1) for f in group]
        return sum(scores) / len(scores) if scores else 0

    first_avg = avg_severity(first_half)
    second_avg = avg_severity(second_half)

    # If second half is more severe, apply escalation bonus to late findings
    if second_avg > first_avg + 0.5:
        for finding in second_half:
            current_conf = finding.get("confidence", 0.5)
            boosted = min(1.0, current_conf + ESCALATION_BONUS)
            finding["confidence"] = round(boosted, 4)
            finding.setdefault("temporal", {})["escalation_bonus"] = ESCALATION_BONUS


def detect_escalation_patterns(
    findings: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Detect repeated category escalation patterns.

    Looks for:
    1. Same category appearing with increasing confidence
    2. Category progression (trust_building → secrecy → meeting)
    3. Repeated high-severity categories

    Returns:
        {
            "has_escalation": bool,
            "escalation_score": float (0-1),
            "patterns": List[str],
            "repeated_categories": Dict[str, int],
            "progression_detected": bool,
        }
    """
    if not findings:
        return {
            "has_escalation": False,
            "escalation_score": 0.0,
            "patterns": [],
            "repeated_categories": {},
            "progression_detected": False,
        }

    # Track category occurrences and their confidences over time
    category_timeline: Dict[str, List[float]] = defaultdict(list)
    for f in sorted(findings, key=lambda x: x.get("timestamp", 0)):
        cats = f.get("categories") or ([f["category"]] if f.get("category") else [])
        conf = f.get("confidence", 0.5)
        for cat in cats:
            category_timeline[cat].append(conf)

    patterns: List[str] = []
    escalation_score = 0.0

    # 1. Repeated categories with increasing confidence
    repeated_categories = {cat: len(confs) for cat, confs in category_timeline.items() if len(confs) >= 2}

    for cat, confidences in category_timeline.items():
        if len(confidences) >= 3:
            # Check if confidence is trending upward
            increases = sum(1 for i in range(1, len(confidences)) if confidences[i] > confidences[i-1])
            if increases >= len(confidences) * 0.5:
                patterns.append(f"escalating_{cat}")
                escalation_score += 0.2

    # 2. Known grooming progression patterns
    PROGRESSION_CHAINS = [
        ["trust_building", "secrecy", "meeting"],
        ["trust_building", "personal_information", "meeting"],
        ["relationship_building", "secrecy", "video_call"],
        ["trust_building", "manipulation", "secrecy"],
        ["relationship_building", "isolation", "meeting"],
    ]

    categories_seen_ordered = []
    for f in sorted(findings, key=lambda x: x.get("timestamp", 0)):
        cats = f.get("categories") or ([f["category"]] if f.get("category") else [])
        for cat in cats:
            if cat not in categories_seen_ordered:
                categories_seen_ordered.append(cat)

    progression_detected = False
    for chain in PROGRESSION_CHAINS:
        # Check if chain appears in order (not necessarily consecutive)
        chain_idx = 0
        for cat in categories_seen_ordered:
            if chain_idx < len(chain) and cat == chain[chain_idx]:
                chain_idx += 1
        if chain_idx == len(chain):
            progression_detected = True
            patterns.append(f"progression:{'→'.join(chain)}")
            escalation_score += 0.3
            break

    # 3. High-severity category repetition
    high_severity_cats = {"meeting", "secrecy", "explicit_content", "personal_information", "threats_coercion"}
    for cat in high_severity_cats:
        if category_timeline.get(cat) and len(category_timeline[cat]) >= 3:
            patterns.append(f"repeated_high_severity:{cat}")
            escalation_score += 0.15

    escalation_score = min(1.0, escalation_score)

    return {
        "has_escalation": escalation_score > 0.2,
        "escalation_score": round(escalation_score, 3),
        "patterns": patterns,
        "repeated_categories": repeated_categories,
        "progression_detected": progression_detected,
    }
