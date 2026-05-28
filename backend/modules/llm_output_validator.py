"""
LLM Output Validator — verifies that quotes in LLM-generated summaries
actually exist in the source transcript.

This prevents hallucinated evidence from appearing in reports.
"""

import re
import logging
from typing import List, Dict, Tuple
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Minimum length for a quote to be validated (very short quotes are likely common phrases)
_MIN_QUOTE_LENGTH = 10

# Minimum similarity ratio for fuzzy matching (accounts for minor LLM paraphrasing)
_FUZZY_THRESHOLD = 0.75


def extract_quotes(text: str) -> List[str]:
    """
    Extract all quoted strings from LLM output.
    Handles both straight quotes ("...") and curly quotes (\u201c...\u201d).
    """
    patterns = [
        r'"([^"]{10,})"',           # Straight double quotes
        r'\u201c([^\u201d]{10,})\u201d',  # Curly double quotes
        r"'([^']{10,})'",           # Single quotes (only long ones)
    ]
    quotes = []
    for pattern in patterns:
        matches = re.findall(pattern, text)
        quotes.extend(matches)
    return quotes


def _normalize(text: str) -> str:
    """Normalize text for comparison: lowercase, collapse whitespace."""
    return re.sub(r'\s+', ' ', text.lower().strip())


def _fuzzy_match(quote: str, transcript: str) -> Tuple[bool, float]:
    """
    Check if a quote exists in the transcript using fuzzy matching.
    Returns (found: bool, best_ratio: float).
    """
    norm_quote = _normalize(quote)
    norm_transcript = _normalize(transcript)

    # Exact substring match first (fast path)
    if norm_quote in norm_transcript:
        return True, 1.0

    # Sliding window fuzzy match for longer quotes
    quote_words = norm_quote.split()
    transcript_words = norm_transcript.split()
    window_size = len(quote_words)

    if window_size > len(transcript_words):
        return False, 0.0

    best_ratio = 0.0
    # Slide a window of similar size across the transcript
    for i in range(len(transcript_words) - window_size + 1):
        window = " ".join(transcript_words[i:i + window_size])
        ratio = SequenceMatcher(None, norm_quote, window).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
        if ratio >= _FUZZY_THRESHOLD:
            return True, ratio

    return best_ratio >= _FUZZY_THRESHOLD, best_ratio


def validate_llm_output(
    llm_output: str,
    transcript: str,
    strict: bool = False,
) -> Dict[str, any]:
    """
    Validate that quotes in LLM output exist in the source transcript.

    Args:
        llm_output: The LLM-generated summary text.
        transcript: The original transcript text.
        strict: If True, removes invalid quotes from output.

    Returns:
        {
            "valid": bool,           # True if all quotes verified
            "output": str,           # Cleaned output (quotes removed if strict)
            "total_quotes": int,
            "verified_quotes": int,
            "unverified_quotes": List[str],
            "verification_rate": float,
        }
    """
    if not llm_output or not transcript:
        return {
            "valid": True,
            "output": llm_output or "",
            "total_quotes": 0,
            "verified_quotes": 0,
            "unverified_quotes": [],
            "verification_rate": 1.0,
        }

    quotes = extract_quotes(llm_output)
    if not quotes:
        return {
            "valid": True,
            "output": llm_output,
            "total_quotes": 0,
            "verified_quotes": 0,
            "unverified_quotes": [],
            "verification_rate": 1.0,
        }

    verified = []
    unverified = []
    cleaned_output = llm_output

    for quote in quotes:
        if len(quote.strip()) < _MIN_QUOTE_LENGTH:
            verified.append(quote)  # Too short to validate meaningfully
            continue

        found, ratio = _fuzzy_match(quote, transcript)
        if found:
            verified.append(quote)
        else:
            unverified.append(quote)
            logger.warning(
                f"LLM hallucinated quote (best_ratio={ratio:.2f}): "
                f'"{quote[:80]}..."'
            )
            if strict:
                # Replace the hallucinated quote with a note
                cleaned_output = cleaned_output.replace(
                    f'"{quote}"',
                    "[quote not verified in transcript]",
                )
                cleaned_output = cleaned_output.replace(
                    f'\u201c{quote}\u201d',
                    "[quote not verified in transcript]",
                )

    total = len(quotes)
    verified_count = len(verified)
    rate = verified_count / total if total > 0 else 1.0

    if unverified:
        logger.warning(
            f"LLM output validation: {len(unverified)}/{total} quotes "
            f"could not be verified in transcript"
        )

    return {
        "valid": len(unverified) == 0,
        "output": cleaned_output if strict else llm_output,
        "total_quotes": total,
        "verified_quotes": verified_count,
        "unverified_quotes": unverified,
        "verification_rate": round(rate, 3),
    }
