"""
Safe-Phrase Allowlist — False Positive Suppression.

Per-category list of phrases that should NOT trigger detection even if
regex matches. These represent legitimate, common uses of flagged language
in educational, professional, or family contexts.

Usage:
    from modules.safe_phrases import is_safe_phrase
    if is_safe_phrase(sentence, category):
        # Skip this finding — it's a known-safe context
        continue

The check is case-insensitive substring matching. A phrase matches if the
full safe phrase appears anywhere in the sentence.
"""

import re
from typing import Dict, List, Set

# ── Per-category safe phrases ─────────────────────────────────────────────────
# Each key is a detection category. Each value is a list of phrases that,
# when present in the sentence, indicate the match is a false positive.

SAFE_PHRASES: Dict[str, List[str]] = {
    "meeting": [
        "parent-teacher meeting",
        "parent teacher meeting",
        "staff meeting",
        "team meeting",
        "office meeting",
        "board meeting",
        "class meeting",
        "school meeting",
        "zoom meeting",
        "meeting room",
        "meeting agenda",
        "meeting minutes",
        "pta meeting",
        "meeting with the principal",
        "meeting with parents",
        "faculty meeting",
        "scheduled meeting",
        "meeting at school",
        "council meeting",
        "safety meeting",
    ],
    "secrecy": [
        "surprise party",
        "birthday surprise",
        "secret santa",
        "secret ingredient",
        "trade secret",
        "secret garden",
        "secret ballot",
        "top secret mission",  # game context
        "secret level",
        "secret passage",
    ],
    "address": [
        "email address",
        "web address",
        "ip address",
        "mailing address",
        "return address",
        "address the issue",
        "address the problem",
        "address the class",
        "address the audience",
        "address book",
        "address this concern",
        "bitcoin address",
        "wallet address",
    ],
    "personal_information": [
        "phone number for emergencies",
        "emergency contact",
        "parent contact number",
        "school phone number",
        "office phone number",
        "contact information for",
        "teacher's email",
        "school email",
    ],
    "video_call": [
        "class video call",
        "zoom class",
        "online class",
        "virtual classroom",
        "google meet class",
        "teams meeting",
        "video conference",
        "video lesson",
        "recorded lecture",
    ],
    "routine": [
        "class schedule",
        "school timetable",
        "homework schedule",
        "practice schedule",
        "bus schedule",
        "exam schedule",
        "revision timetable",
        "lesson plan",
    ],
    "school": [
        "school project",
        "school assignment",
        "school play",
        "school trip",
        "school bus",
        "school uniform",
        "school holiday",
        "after school club",
        "school sports day",
    ],
    "trust_building": [
        "trust exercises",
        "trust fall",
        "build trust with students",
        "trust between teacher and student",
        "therapeutic trust",
        "trust the process",
    ],
    "relationship_building": [
        "building relationships with students",
        "positive relationships in class",
        "teacher-student relationship",
        "peer relationships",
        "relationship with learning",
    ],
    "gift_bribery": [
        "birthday gift",
        "christmas gift",
        "graduation gift",
        "gift for the class",
        "gift exchange",
        "class prize",
        "reward sticker",
        "reward chart",
        "merit award",
        "school prize",
    ],
    "isolation": [
        "quiet reading time",
        "individual work",
        "independent study",
        "one-on-one tutoring",
        "study alone",
        "work independently",
    ],
    "explicit_content": [
        "sex education",
        "sex ed class",
        "sexual health",
        "reproductive health",
        "biology lesson",
        "anatomy class",
        "puberty education",
        "consent education",
        "healthy relationships curriculum",
    ],
    "desensitization": [
        "it's normal to feel nervous",
        "it's normal to make mistakes",
        "it's normal to feel anxious",
        "it's completely normal to struggle",
        "perfectly normal to feel",
        "normal part of growing up",
        "normal part of learning",
        "nothing wrong with asking for help",
        "nothing wrong with making mistakes",
    ],
    "manipulation": [
        "peer pressure awareness",
        "anti-bullying",
        "say no to pressure",
        "resist pressure",
        "recognise manipulation",
    ],
    "gaming_luring": [
        "minecraft education",
        "educational game",
        "class game server",
        "school minecraft server",
        "kahoot game",
        "class discord server",
        "study group discord",
    ],
}

# Pre-compile for fast lookup: lowercase set per category
_COMPILED: Dict[str, List[str]] = {
    cat: [phrase.lower() for phrase in phrases]
    for cat, phrases in SAFE_PHRASES.items()
}


def is_safe_phrase(sentence: str, category: str) -> bool:
    """
    Check if a sentence contains a known-safe phrase for the given category.

    Args:
        sentence: The sentence text to check.
        category: The detection category that was triggered.

    Returns:
        True if the sentence is a known false positive (should be suppressed).
    """
    if category not in _COMPILED:
        return False

    lower_sentence = sentence.lower()
    for safe in _COMPILED[category]:
        if safe in lower_sentence:
            return True
    return False


def get_safe_phrases(category: str) -> List[str]:
    """Return the safe phrases list for a category (for testing/debugging)."""
    return SAFE_PHRASES.get(category, [])
