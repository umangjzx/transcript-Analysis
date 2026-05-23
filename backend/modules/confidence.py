"""
Confidence Scoring Engine — Context-Based (v2).

ARCHITECTURE CHANGE:
    Previous version applied a safe-context penalty triggered by role-based
    keywords (teacher, parent, counselor) in safe_indicators.  That logic
    has been removed entirely.

    This version applies confidence adjustments based on:
        1. Exact phrase match bonus
        2. Multiple supporting keywords bonus
        3. ContextType multiplier (from ContextAnalyzer.classify)
        4. Negation penalty  (token-scoped, ±5 tokens)
        5. Joke/sarcasm penalty (±2 sentence window)

    No speaker identity, role, or title is ever consulted.

Scoring formula
---------------
    score = pattern_strength
          + exact_match_bonus        (+0.15 if exact phrase found)
          + keyword_bonus            (+0.10 if ≥2 supporting keywords)
          + context_multiplier       (from ContextType, range -0.40 to +0.40)
          - negation_penalty         (up to -0.40)
          - joke_penalty             (up to -0.50)
    final = clamp(score, 0.0, 1.0)
"""

import re
from typing import Dict, Any, List, Optional

from .context_analyzer import ContextAnalyzer, ContextType, CONTEXT_MULTIPLIERS


class ConfidenceCalculator:
    """
    Calculate confidence scores for pattern matches in grooming detection.

    All context adjustments are derived from ContextType classification —
    never from speaker labels or role names.
    """

    # Bonus / penalty constants
    EXACT_MATCH_BONUS        =  0.15
    MULTIPLE_KEYWORDS_BONUS  =  0.10
    NEGATION_PENALTY         = -0.40
    JOKE_PENALTY             = -0.50

    MIN_SUPPORTING_KEYWORDS  = 2

    def __init__(self):
        self._context_analyzer = ContextAnalyzer()
        self._build_phrase_library()
        self._compile_patterns()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate(
        self,
        category: str,
        matched_text: str,
        sentence: str,
        pattern_strength: float,
        previous_sentence: Optional[str] = None,
        next_sentence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Calculate confidence score for a pattern match.

        Args:
            category:         Detection category (e.g. "secrecy")
            matched_text:     The specific text that matched the pattern
            sentence:         Full sentence containing the match
            pattern_strength: Base strength from the regex pattern (0.0–1.0)
            previous_sentence: Previous sentence for context window (optional)
            next_sentence:    Next sentence for context window (optional)

        Returns:
            {
                "confidence":   float (0.0–1.0),
                "breakdown":    dict,
                "factors":      List[str],
                "adjustments":  float,
                "context_type": str,
            }
        """
        score = pattern_strength
        factors: List[str] = []
        breakdown = {
            "base_score":          pattern_strength,
            "exact_match_bonus":   0.0,
            "keyword_bonus":       0.0,
            "context_multiplier":  0.0,
            "negation_penalty":    0.0,
            "joke_penalty":        0.0,
        }

        matched_lower  = matched_text.lower().strip()
        sentence_lower = sentence.lower().strip()

        # 1. Exact phrase match
        exact_bonus = self._check_exact_match(category, matched_lower)
        if exact_bonus:
            score += exact_bonus
            breakdown["exact_match_bonus"] = exact_bonus
            factors.append("exact_phrase_match")

        # 2. Supporting keywords
        kw_bonus = self._check_supporting_keywords(category, sentence_lower)
        if kw_bonus:
            score += kw_bonus
            breakdown["keyword_bonus"] = kw_bonus
            factors.append("multiple_keywords")

        # 3. Context-type multiplier (replaces old safe/risk context logic)
        ctx_result = self._context_analyzer.classify(
            sentence, previous_sentence, next_sentence
        )
        ctx_multiplier = ctx_result["multiplier"]
        if ctx_multiplier != 0.0:
            score += ctx_multiplier
            breakdown["context_multiplier"] = ctx_multiplier
            factors.append(f"context:{ctx_result['primary_context'].value}")

        # 4. Negation penalty (token-scoped)
        neg_penalty = self._check_negation(sentence_lower, matched_lower)
        if neg_penalty:
            score += neg_penalty          # neg_penalty is already negative
            breakdown["negation_penalty"] = neg_penalty
            factors.append("negation_detected")

        # 5. Joke / sarcasm penalty
        joke_penalty = self._check_joke_context(sentence_lower)
        if joke_penalty:
            score += joke_penalty         # joke_penalty is already negative
            breakdown["joke_penalty"] = joke_penalty
            factors.append("joke_context")

        final_score = max(0.0, min(1.0, score))

        return {
            "confidence":   round(final_score, 4),
            "breakdown":    breakdown,
            "factors":      factors,
            "adjustments":  round(final_score - pattern_strength, 4),
            "context_type": ctx_result["primary_context"].value,
        }

    def batch_calculate(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Calculate confidence for a list of match dicts."""
        return [
            self.calculate(
                category=m.get("category", ""),
                matched_text=m.get("matched_text", ""),
                sentence=m.get("sentence", ""),
                pattern_strength=m.get("pattern_strength", 0.5),
                previous_sentence=m.get("previous_sentence"),
                next_sentence=m.get("next_sentence"),
            )
            for m in matches
        ]

    def get_scoring_rules(self) -> Dict[str, Any]:
        return {
            "exact_match_bonus":       self.EXACT_MATCH_BONUS,
            "multiple_keywords_bonus": self.MULTIPLE_KEYWORDS_BONUS,
            "negation_penalty":        self.NEGATION_PENALTY,
            "joke_penalty":            self.JOKE_PENALTY,
            "min_supporting_keywords": self.MIN_SUPPORTING_KEYWORDS,
            "context_multipliers":     {k.value: v for k, v in CONTEXT_MULTIPLIERS.items()},
        }

    def explain_score(
        self,
        category: str,
        matched_text: str,
        sentence: str,
        pattern_strength: float,
    ) -> str:
        result = self.calculate(category, matched_text, sentence, pattern_strength)
        lines = [
            f"Confidence Score : {result['confidence']:.2%}",
            f"Base Strength    : {pattern_strength:.2%}",
            f"Total Adjustment : {result['adjustments']:+.2%}",
            f"Context Type     : {result['context_type']}",
            "Factors Applied  :",
        ]
        bd = result["breakdown"]
        if bd["exact_match_bonus"]:
            lines.append(f"  + Exact phrase match : +{bd['exact_match_bonus']:.2%}")
        if bd["keyword_bonus"]:
            lines.append(f"  + Multiple keywords  : +{bd['keyword_bonus']:.2%}")
        if bd["context_multiplier"]:
            lines.append(f"  ~ Context multiplier : {bd['context_multiplier']:+.2%}")
        if bd["negation_penalty"]:
            lines.append(f"  - Negation detected  : {bd['negation_penalty']:.2%}")
        if bd["joke_penalty"]:
            lines.append(f"  - Joke/sarcasm       : {bd['joke_penalty']:.2%}")
        if not result["factors"]:
            lines.append("  (No adjustments applied)")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _check_exact_match(self, category: str, matched_text: str) -> float:
        phrases = self.exact_phrases.get(category, [])
        for phrase in phrases:
            if phrase in matched_text or matched_text in phrase:
                return self.EXACT_MATCH_BONUS
        return 0.0

    def _check_supporting_keywords(self, category: str, sentence: str) -> float:
        keywords = self.supporting_keywords.get(category, [])
        count = sum(1 for kw in keywords if kw.lower() in sentence)
        return self.MULTIPLE_KEYWORDS_BONUS if count >= self.MIN_SUPPORTING_KEYWORDS else 0.0

    def _check_negation(self, sentence: str, matched_text: str) -> float:
        """
        Token-scoped negation: only penalise if a negation word appears
        within 5 tokens of the matched phrase.
        """
        match_pos = sentence.find(matched_text)
        if match_pos == -1:
            return 0.0
        # Check 30 characters before the match (approx 5 tokens)
        context_before = sentence[max(0, match_pos - 30): match_pos]
        for pattern in self.negation_regex:
            if pattern.search(context_before):
                return self.NEGATION_PENALTY
        return 0.0

    def _check_joke_context(self, sentence: str) -> float:
        for pattern in self.joke_regex:
            if pattern.search(sentence):
                return self.JOKE_PENALTY
        return 0.0

    def _build_phrase_library(self):
        """Exact phrases and supporting keywords per category."""
        self.exact_phrases: Dict[str, List[str]] = {
            "parent_monitoring": [
                "do your parents check", "does your mom read",
                "are your parents monitoring", "who checks your phone",
                "do they check your messages",
            ],
            "secrecy": [
                "don't tell anyone", "keep this between us", "our secret",
                "delete these messages", "nobody needs to know",
                "nobody else needs to know", "secret chat", "private conversation",
            ],
            "trust_building": [
                "i'm trustworthy", "i'm here for you", "you can trust me",
                "i care about you", "trust me", "always talk to me",
                "i understand you", "i'm someone you can trust",
            ],
            "relationship_building": [
                "you're special", "i love you", "we have a special connection",
                "special connection", "close friendship", "best friends",
            ],
            "manipulation": [
                "your parents will overreact", "only i understand you",
                "prove you love me", "if you really loved me", "everyone does this",
                "they won't understand",
            ],
            "video_call": [
                "let's video call", "turn on your camera", "show me yourself",
                "send me a video", "private video call", "one-on-one call",
                "video chat", "facetime",
            ],
            "meeting": [
                "let's meet up", "meet you in person", "come to my place",
                "hang out together", "meet in person", "see each other",
            ],
            "address": [
                "what's your address", "where do you live", "send your location",
                "share your address", "house number", "street name",
            ],
            "school": [
                "what school do you go to", "which school are you",
                "what grade are you in",
            ],
            "routine": [
                "when are you alone", "what's your schedule",
                "when do your parents leave",
            ],
        }

        self.supporting_keywords: Dict[str, List[str]] = {
            "parent_monitoring": [
                "parents", "mom", "dad", "mother", "father",
                "check", "monitor", "read", "phone", "messages",
            ],
            "secrecy": [
                "secret", "don't tell", "between us", "delete",
                "hide", "private", "nobody", "anyone",
            ],
            "trust_building": [
                "trust", "care", "understand", "here for you",
                "reliable", "honest", "trustworthy", "friendly",
            ],
            "relationship_building": [
                "special", "love", "connection", "close",
                "unique", "different", "bond", "together",
            ],
            "manipulation": [
                "overreact", "understand", "prove", "only i",
                "everyone", "mature", "owe", "promised",
            ],
            "video_call": [
                "video", "camera", "webcam", "call",
                "facetime", "see you", "show",
            ],
            "meeting": [
                "meet", "hang out", "in person", "irl",
                "come", "place", "house", "together",
            ],
            "address": [
                "address", "location", "live", "where",
                "street", "city", "area", "house",
            ],
            "school": [
                "school", "grade", "class", "campus",
            ],
            "routine": [
                "schedule", "routine", "alone", "free",
                "available", "time", "when", "usually",
            ],
        }

    def _compile_patterns(self):
        """Compile negation and joke regex patterns."""
        negation_terms = [
            "does not", "did not", "will not", "would not", "could not",
            "should not", "have not", "has not", "had not", "do not",
            "is not", "was not", "are not", "were not",
            "didn't", "doesn't", "wasn't", "isn't", "won't", "wouldn't",
            "can't", "cannot", "couldn't", "shouldn't", "haven't", "hasn't",
            "hadn't", "don't", "ain't",
            "not", "never", "neither", "nor", "nobody", "nothing",
            "nowhere", "none",
        ]
        alternation = "|".join(re.escape(t) for t in negation_terms)
        self.negation_regex = [
            re.compile(r"\b(?:" + alternation + r")\b", re.IGNORECASE)
        ]

        joke_patterns = [
            r'\b(?:lol|lmao|rofl|haha|hehe|lmfao)\b',
            r'\b(?:just\s+kidding|jk|joking|joke|sarcasm)\b',
            r'\b(?:obviously|clearly)\s+(?:not|joking)\b',
            r'(?:😂|😅|🤣|😆|😄|😁)',
            r'\b(?:as\s+if|yeah\s+right)\b',
            r'\beveryone\s+laughed\b',
        ]
        self.joke_regex = [re.compile(p, re.IGNORECASE) for p in joke_patterns]


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def calculate_confidence(
    category: str,
    matched_text: str,
    sentence: str,
    pattern_strength: float,
) -> float:
    """Quick convenience wrapper — returns confidence float."""
    return ConfidenceCalculator().calculate(
        category, matched_text, sentence, pattern_strength
    )["confidence"]


__all__ = ["ConfidenceCalculator", "calculate_confidence"]
