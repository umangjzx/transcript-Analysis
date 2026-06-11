"""
Educational Context Detector.

Detects whether a transcript is primarily educational/professional in nature.
When the ratio of educational keywords is high, all findings receive a
confidence penalty — reducing false positives in classroom, tutoring,
therapy, and parenting contexts.

Usage:
    from modules.educational_context import detect_educational_context
    result = detect_educational_context(transcript)
    if result["is_educational"]:
        # Apply penalty to all findings
        for finding in findings:
            finding["confidence"] *= (1 - result["penalty"])
"""

import re
from typing import Dict, Any

# ── Educational / Professional keywords ───────────────────────────────────────
# These words strongly indicate the conversation is in a legitimate context.

_EDUCATIONAL_KEYWORDS = [
    # School / academic
    r'\b(?:homework|assignment|essay|exam|test|quiz|grade|marks?|class(?:room)?|lesson|lecture|curriculum|syllabus|semester|term)\b',
    r'\b(?:teacher|professor|tutor|instructor|student|pupil|classmate|headteacher|principal)\b',
    r'\b(?:subject|maths?|science|english|history|geography|biology|chemistry|physics|literature)\b',
    r'\b(?:textbook|worksheet|exercise|revision|coursework|dissertation|thesis|research\s+paper)\b',
    r'\b(?:school|college|university|campus|library|laboratory|classroom|assembly)\b',

    # Professional / therapy / safeguarding
    r'\b(?:counsellor|therapist|psychologist|safeguarding|child\s+protection|social\s+worker)\b',
    r'\b(?:session\s+notes?|case\s+(?:study|file|notes?)|professional\s+development|training)\b',
    r'\b(?:policy|procedure|protocol|guidelines?|framework|assessment|evaluation|report\s+card)\b',

    # Parenting / legitimate adult context
    r'\b(?:parent(?:ing)?|guardian|family\s+(?:meeting|discussion|time)|bedtime\s+routine)\b',
    r'\b(?:permission\s+slip|field\s+trip|school\s+bus|lunch\s+money|packed\s+lunch)\b',

    # Sports / activities
    r'\b(?:coach(?:ing)?|practice|training\s+session|match|tournament|team\s+(?:meeting|practice))\b',
    r'\b(?:rehearsal|performance|concert|recital|club\s+meeting|scout(?:s|ing)?)\b',
]

_COMPILED_KEYWORDS = [re.compile(p, re.IGNORECASE) for p in _EDUCATIONAL_KEYWORDS]

# ── Penalty configuration ─────────────────────────────────────────────────────

# If educational keyword density exceeds this threshold, apply penalty
EDUCATIONAL_DENSITY_THRESHOLD = 0.15  # 15% of sentences contain educational keywords

# Maximum penalty applied (confidence multiplied by 1 - penalty)
MAX_EDUCATIONAL_PENALTY = 0.25  # Up to 25% confidence reduction

# Minimum number of sentences to evaluate (avoid over-penalizing very short texts)
MIN_SENTENCES_FOR_DETECTION = 5


def detect_educational_context(transcript: str) -> Dict[str, Any]:
    """
    Analyse a transcript for educational/professional context signals.

    Args:
        transcript: Full transcript text.

    Returns:
        {
            "is_educational": bool,
            "penalty": float (0.0 to MAX_EDUCATIONAL_PENALTY),
            "density": float (ratio of sentences with educational keywords),
            "keyword_count": int,
            "sentence_count": int,
        }
    """
    if not transcript or not transcript.strip():
        return {
            "is_educational": False,
            "penalty": 0.0,
            "density": 0.0,
            "keyword_count": 0,
            "sentence_count": 0,
        }

    sentences = [s.strip() for s in transcript.split("\n") if s.strip()]
    sentence_count = len(sentences)

    if sentence_count < MIN_SENTENCES_FOR_DETECTION:
        return {
            "is_educational": False,
            "penalty": 0.0,
            "density": 0.0,
            "keyword_count": 0,
            "sentence_count": sentence_count,
        }

    # Count sentences containing at least one educational keyword
    keyword_hits = 0
    for sentence in sentences:
        for pattern in _COMPILED_KEYWORDS:
            if pattern.search(sentence):
                keyword_hits += 1
                break  # one hit per sentence is enough

    density = keyword_hits / sentence_count

    # Calculate penalty — linear scale from threshold to 2x threshold
    is_educational = density >= EDUCATIONAL_DENSITY_THRESHOLD
    penalty = 0.0
    if is_educational:
        # Scale penalty linearly: at threshold = 0, at 2x threshold = MAX
        scale = min(1.0, (density - EDUCATIONAL_DENSITY_THRESHOLD) / EDUCATIONAL_DENSITY_THRESHOLD)
        penalty = scale * MAX_EDUCATIONAL_PENALTY

    return {
        "is_educational": is_educational,
        "penalty": round(penalty, 4),
        "density": round(density, 4),
        "keyword_count": keyword_hits,
        "sentence_count": sentence_count,
    }


def apply_educational_penalty(
    findings: list,
    transcript: str,
) -> list:
    """
    Apply educational context penalty to all findings if the transcript
    is detected as primarily educational.

    Modifies findings in-place and returns them.
    """
    context = detect_educational_context(transcript)

    if not context["is_educational"] or context["penalty"] <= 0:
        return findings

    penalty = context["penalty"]

    for finding in findings:
        original = finding.get("confidence", 0)
        adjusted = original * (1.0 - penalty)
        finding["confidence"] = round(adjusted, 4)
        # Store the penalty for transparency
        finding.setdefault("scoring", {})["educational_penalty"] = round(penalty, 4)
        finding.setdefault("scoring", {})["educational_density"] = context["density"]

    return findings
