"""
Leetspeak / Obfuscation Normalization Layer.

Normalizes common text obfuscation techniques used to bypass pattern detection:
- Leetspeak substitutions (e.g., "m33t" → "meet", "s3cr3t" → "secret")
- Character repetition (e.g., "seeecret" → "secret")
- Separator insertion (e.g., "s.e.c.r.e.t" → "secret")
- Mixed-case obfuscation (handled by .lower() in patterns)
- Unicode homoglyphs (handled by _normalize_unicode in grooming_detector.py)

This module is applied BEFORE pattern matching to ensure obfuscated text
is caught by existing regex patterns.
"""

import re
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)

# ── Leetspeak character substitution map ──────────────────────────────────────
# Maps common leetspeak characters to their alphabetic equivalents.
# Order matters for multi-char substitutions.

_LEET_MAP: Dict[str, str] = {
    # Numbers → letters
    "0":  "o",
    "1":  "i",
    "3":  "e",
    "4":  "a",
    "5":  "s",
    "6":  "g",
    "7":  "t",
    "8":  "b",
    "9":  "g",
    # Symbols → letters
    "@":  "a",
    "$":  "s",
    "!":  "i",
    "+":  "t",
    "(":  "c",
    "|":  "l",
    "}{": "h",
    "}{": "h",
    "/\\":  "a",
    "\\/": "v",
    "ph": "f",
}

# Single-char substitutions for fast lookup
_SINGLE_CHAR_MAP: Dict[str, str] = {
    "0": "o", "1": "i", "3": "e", "4": "a", "5": "s",
    "6": "g", "7": "t", "8": "b", "9": "g",
    "@": "a", "$": "s", "!": "i", "+": "t", "(": "c", "|": "l",
}

# ── Separator patterns ────────────────────────────────────────────────────────
# Detects characters inserted between letters to break pattern matching.
_SEPARATOR_RE = re.compile(r'(?<=\w)[.\-_*~`\s]{1,2}(?=\w)')

# Repeated separators between every character (e.g., "s.e.c.r.e.t")
_FULL_SEPARATOR_RE = re.compile(
    r'\b([a-zA-Z0-9@$!+|(])(?:[.\-_*~`\s])([a-zA-Z0-9@$!+|(])(?:[.\-_*~`\s])([a-zA-Z0-9@$!+|(])'
)

# ── Character repetition ─────────────────────────────────────────────────────
# Collapses 3+ repeated characters to 2 (preserves legitimate doubles like "meet")
_REPEAT_RE = re.compile(r'(.)\1{2,}')

# ── Known obfuscated words (direct lookup for common bypass attempts) ─────────
_KNOWN_OBFUSCATIONS: Dict[str, str] = {
    # Meeting/location
    "m33t": "meet", "m3et": "meet", "me3t": "meet", "m33+": "meet",
    "m33t up": "meet up", "m33t m3": "meet me",
    # Secrecy
    "s3cr3t": "secret", "s3cret": "secret", "secr3t": "secret",
    "d0nt t3ll": "dont tell", "d0n7 73ll": "dont tell",
    "d0nt": "dont", "d0n7": "dont",
    "t3ll": "tell", "73ll": "tell",
    "any0ne": "anyone", "4ny0ne": "anyone", "4nyone": "anyone",
    "n0body": "nobody", "n0b0dy": "nobody",
    "b3tw33n": "between", "b3tween": "between",
    "k33p": "keep", "k3ep": "keep",
    # Personal info
    "4ddr3ss": "address", "addr3ss": "address", "4ddress": "address",
    "ph0n3": "phone", "phon3": "phone", "ph0ne": "phone",
    "numb3r": "number", "num83r": "number",
    # Trust/manipulation
    "tru5t": "trust", "7rust": "trust", "tru$t": "trust",
    "sp3ci4l": "special", "sp3cial": "special", "speci4l": "special",
    "sp3c1al": "special",
    "und3rstand": "understand", "und3rst4nd": "understand",
    "m4tur3": "mature", "matur3": "mature",
    "imm4tur3": "immature", "1mmatur3": "immature",
    "n0rm4l": "normal", "n0rmal": "normal", "norm4l": "normal",
    # Platform/communication
    "sn4pchat": "snapchat", "sn@pchat": "snapchat",
    "d1sc0rd": "discord", "disc0rd": "discord",
    "1nst4gr4m": "instagram", "inst4gram": "instagram",
    "t3l3gr4m": "telegram", "telegr4m": "telegram",
    # Explicit
    "s3nd": "send", "s3nd m3": "send me",
    "p1c": "pic", "p1cs": "pics", "p1ctur3": "picture",
    "n4k3d": "naked", "nak3d": "naked", "n@ked": "naked",
    "nud3": "nude", "nud3s": "nudes",
    # Video
    "v1d30": "video", "vid30": "video", "v1deo": "video",
    "c4m3r4": "camera", "cam3ra": "camera",
    # Common bypass words
    "k1d": "kid", "k1ds": "kids",
    "4l0n3": "alone", "al0ne": "alone", "4lone": "alone",
    "pr1v4t3": "private", "priv4te": "private", "pr1vate": "private",
    # Deletion/hiding
    "d3l3te": "delete", "del3te": "delete", "d3lete": "delete",
    "cl34r": "clear", "cl3ar": "clear",
    "h1d3": "hide", "hid3": "hide",
    "m3ss4g3s": "messages", "m3ssages": "messages", "messag3s": "messages",
    "msgs": "messages",
    # Parental monitoring
    "par3nts": "parents", "p4rents": "parents", "p4r3nts": "parents",
    "ch3ck": "check", "ch3cks": "checks",
    # Actions
    "l00k": "look", "l0ok": "look",
    "th1nk": "think", "th1nks": "thinks",
    "3very0ne": "everyone", "every0ne": "everyone",
    "d03s": "does",
}


def normalize_leetspeak(text: str) -> str:
    """
    Normalize leetspeak and obfuscation in text.

    Processing order:
    1. Known obfuscation lookup (exact matches)
    2. Remove separators between characters
    3. Apply character substitution map
    4. Collapse repeated characters

    Args:
        text: Input text (may contain leetspeak/obfuscation)

    Returns:
        Normalized text with obfuscation removed.
        Original text is preserved alongside for dual matching.
    """
    if not text:
        return text

    normalized = text.lower()

    # Step 1: Known obfuscation lookup (case-insensitive)
    for obfuscated, clean in _KNOWN_OBFUSCATIONS.items():
        # Use word-boundary-aware replacement
        pattern = re.compile(re.escape(obfuscated), re.IGNORECASE)
        normalized = pattern.sub(clean, normalized)

    # Step 2: Remove separators between single characters
    # Detect patterns like "s.e.c.r.e.t" or "m-e-e-t"
    normalized = _remove_separators(normalized)

    # Step 3: Apply single-character leetspeak substitutions
    normalized = _apply_char_substitutions(normalized)

    # Step 4: Collapse excessive character repetition
    normalized = _REPEAT_RE.sub(r'\1\1', normalized)

    return normalized


def _remove_separators(text: str) -> str:
    """
    Remove separators inserted between characters to break words.
    Only removes separators in sequences that look like obfuscated words
    (single chars separated by dots/dashes/etc).
    """
    # Match sequences of single chars separated by consistent separators
    # e.g., "s.e.c.r.e.t" → "secret", "m-e-e-t" → "meet"
    def _deseparate(match_text: str) -> str:
        # Remove common separator characters between single chars
        return re.sub(r'(?<=\w)[.\-_*~`]{1}(?=\w)', '', match_text)

    # Find words that are likely separator-obfuscated (alternating char-separator pattern)
    # Pattern: letter, separator, letter, separator, letter (at least 3 chars)
    sep_pattern = re.compile(
        r'\b([a-zA-Z0-9@$!+|(])[.\-_*~`]'
        r'([a-zA-Z0-9@$!+|(])[.\-_*~`]'
        r'([a-zA-Z0-9@$!+|(](?:[.\-_*~`][a-zA-Z0-9@$!+|(])*)\b'
    )

    def _replace_separated(m):
        full = m.group(0)
        return re.sub(r'[.\-_*~`]', '', full)

    text = sep_pattern.sub(_replace_separated, text)
    return text


def _apply_char_substitutions(text: str) -> str:
    """Apply single-character leetspeak substitutions."""
    result = []
    i = 0
    while i < len(text):
        ch = text[i]
        if ch in _SINGLE_CHAR_MAP:
            result.append(_SINGLE_CHAR_MAP[ch])
        else:
            result.append(ch)
        i += 1
    return "".join(result)


def normalize_for_detection(text: str) -> Tuple[str, str]:
    """
    Return both original (lowercased) and normalized versions of text.
    Pattern matching should check BOTH to avoid false positives on
    legitimate use of numbers/symbols.

    Returns:
        (original_lower, normalized) tuple
    """
    original_lower = text.lower()
    normalized = normalize_leetspeak(text)
    return original_lower, normalized


def is_likely_obfuscated(text: str) -> bool:
    """
    Heuristic check: does this text contain likely obfuscation?
    Used to decide whether to run the normalization layer.

    Returns True if text contains patterns suggesting intentional obfuscation.
    """
    if not text:
        return False

    lower = text.lower()

    # Check for known obfuscations
    for obf in _KNOWN_OBFUSCATIONS:
        if obf in lower:
            return True

    # Check for high density of leetspeak characters in word-like sequences
    # (e.g., "m33t" has 2/4 = 50% leet chars)
    words = re.findall(r'\S+', lower)
    for word in words:
        if len(word) < 3:
            continue
        leet_count = sum(1 for ch in word if ch in _SINGLE_CHAR_MAP)
        if leet_count >= 2 and leet_count / len(word) >= 0.3:
            return True

    # Check for separator patterns (e.g., "s.e.c.r.e.t")
    if re.search(r'[a-z0-9][.\-_][a-z0-9][.\-_][a-z0-9]', lower):
        return True

    return False
