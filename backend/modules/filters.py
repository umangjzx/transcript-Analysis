"""
Negation and Joke Detection Filters for Grooming Detection.

This module provides filters to detect negations and jokes in conversation
transcripts. These filters help reduce false positives by identifying when
potentially concerning phrases are negated or used in a joking context.

NEGATION SCOPING RULE (token-distance):
A negation term only counts as negating a target phrase when it appears
within TOKEN_WINDOW tokens of that phrase (default 5).  Negation terms
that appear far away in the same sentence — e.g. in an unrelated clause —
do NOT suppress the risk signal for the target phrase.

Examples:
  "parents might misunderstand"          → NOT negated  (no negation near phrase)
  "did not ask for the address"          → NEGATED      ("not" within 5 tokens of "address")
  "I never lie but I want your address"  → NOT negated  ("never" is 7+ tokens away from "address")
"""

import re
from typing import Dict, List, Optional, Tuple, Any


class NegationFilter:
    """
    Detect and analyse negation in sentences using token-distance scoping.

    A negation term is only considered to modify a target phrase when it
    falls within ``token_window`` tokens of that phrase.  This prevents
    negation words in unrelated clauses from suppressing risk signals.

    When no ``target_phrase`` is supplied the filter still reports whether
    any negation exists in the sentence, but ``is_negated`` is set to
    ``False`` (no target → no scoped negation) and the caller should treat
    the result as informational only.

    SECRECY PHRASE EXEMPTION:
    Certain secrecy/grooming phrases contain negation words as their core
    semantic content (e.g. "nobody needs to know", "don't tell anyone",
    "did not need to tell anyone").  For these phrases the negation word is
    *part of the threat*, not a denial of it.  When the target_phrase is
    recognised as one of these exempt phrases, scoped negation is skipped
    entirely so the confidence penalty is not applied.
    """

    # Phrases whose negation words are intrinsic to the secrecy/grooming
    # signal and must NOT be treated as negating the phrase itself.
    # Stored normalised (lowercase, collapsed whitespace).
    NEGATION_EXEMPT_PHRASES = frozenset([
        # nobody / no one constructions
        "nobody needs to know",
        "nobody else needs to know",
        "nobody needed to know",
        "nobody else needed to know",
        "no one needs to know",
        "no one else needs to know",
        "no one needed to know",
        "no one else needed to know",
        "nobody has to know",
        "nobody else has to know",
        "no one has to know",
        "no one else has to know",
        # don't tell constructions
        "don't tell anyone",
        "dont tell anyone",
        "do not tell anyone",
        "never tell anyone",
        "don't tell anybody",
        "do not tell anybody",
        "never tell anybody",
        "don't tell your parents",
        "do not tell your parents",
        "don't tell them",
        "do not tell them",
        # didn't / did not need to tell
        "didn't need to tell anyone",
        "did not need to tell anyone",
        "didn't have to tell anyone",
        "did not have to tell anyone",
        "didn't need to tell anybody",
        "did not need to tell anybody",
        # don't let anyone know
        "don't let anyone know",
        "do not let anyone know",
        "don't let them know",
        "do not let them know",
        # keep secret / between us
        "keep this between us",
        "keep it between us",
        "keep this secret",
        "keep it secret",
        # delete messages
        "delete these messages",
        "delete this message",
        "delete our messages",
        "delete the messages",
    ])

    # Negation terms — ordered longest-first so multi-word contractions
    # are matched before their single-word substrings.
    NEGATION_TERMS = [
        # Multi-word contractions first
        "does not", "did not", "will not", "would not", "could not",
        "should not", "have not", "has not", "had not", "do not",
        "is not", "was not", "are not", "were not", "no one",
        # Single-word contractions
        "didn't", "doesn't", "wasn't", "isn't", "won't", "wouldn't",
        "can't", "cannot", "couldn't", "shouldn't", "haven't", "hasn't",
        "hadn't", "don't", "ain't", "aint",
        # Plain negation words
        "not", "never", "neither", "nor", "nobody", "nothing",
        "nowhere", "none", "noone",
        # "no" last — very short, high false-positive risk
        "no",
    ]

    # Negation terms whose strength warrants a higher score
    STRONG_NEGATIONS = frozenset([
        "never", "cannot", "can't", "won't", "nothing", "nobody",
        "nowhere", "none", "no one", "noone",
    ])

    def __init__(self, token_window: int = 5):
        """
        Initialise the negation filter.

        Args:
            token_window: Maximum number of tokens allowed between the end of
                          a negation term and the start of the target phrase
                          (or vice-versa) for the negation to be considered
                          scoped to that phrase.  Default is 5.
        """
        self.token_window = token_window

        # Compile a single alternation pattern (longest terms first to avoid
        # partial matches, e.g. "did not" before "not").
        alternation = "|".join(re.escape(t) for t in self.NEGATION_TERMS)
        self._negation_re = re.compile(
            r"\b(?:" + alternation + r")\b", re.IGNORECASE
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect_negation(
        self,
        sentence: str,
        target_phrase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Detect negation in a sentence with token-distance scoping.

        When ``target_phrase`` is provided the method checks whether any
        negation term is within ``self.token_window`` tokens of the phrase.
        Only that proximity-scoped result drives ``is_negated``.

        When ``target_phrase`` is *not* provided, ``is_negated`` is always
        ``False`` (there is nothing to negate) but ``negation_terms`` still
        lists every negation word found in the sentence so callers can use
        the information for other purposes.

        Args:
            sentence: The sentence to analyse.
            target_phrase: The matched/risk phrase to check against (optional).

        Returns:
            Dictionary containing:
            - is_negated: bool — True only when a negation is within
                          token_window of target_phrase.
            - negation_score: float 0.0–1.0
            - negation_terms: list of negation words found anywhere in sentence
            - negation_count: int
            - negation_positions: list of (term, char_position) tuples
            - directly_negates_target: bool (always present; False when no target)
            - scoped_negation_terms: list of negation terms that are within
                                     token_window of target_phrase
        """
        negation_positions: List[Tuple[str, int]] = []
        seen: set = set()

        for match in self._negation_re.finditer(sentence):
            term_lower = match.group(0).lower()
            if term_lower not in seen:
                seen.add(term_lower)
                negation_positions.append((match.group(0), match.start()))

        negation_terms = [t for t, _ in negation_positions]

        # --- Secrecy-phrase exemption ---
        # If the target phrase is a known secrecy/grooming phrase whose
        # negation words are intrinsic to the threat (e.g. "nobody needs to
        # know"), skip scoped negation entirely so no penalty is applied.
        if target_phrase:
            normalised_target = " ".join(target_phrase.lower().split())
            if normalised_target in self.NEGATION_EXEMPT_PHRASES:
                return {
                    "is_negated": False,
                    "negation_score": 0.0,
                    "negation_terms": negation_terms,
                    "negation_count": len(negation_terms),
                    "negation_positions": negation_positions,
                    "directly_negates_target": False,
                    "scoped_negation_terms": [],
                }

        # --- Scoped check against target phrase ---
        directly_negates = False
        scoped_terms: List[str] = []

        if target_phrase:
            directly_negates, scoped_terms = self._scoped_negation(
                sentence, target_phrase, negation_positions
            )

        # is_negated is ONLY True when a negation is scoped to the target.
        # If no target was given we cannot claim anything is negated.
        is_negated = directly_negates

        # Score is based on scoped terms (or all terms when no target given,
        # for informational use only).
        scoring_terms = scoped_terms if target_phrase else negation_terms
        negation_score = self._score(scoring_terms)

        return {
            "is_negated": is_negated,
            "negation_score": round(negation_score, 3),
            "negation_terms": negation_terms,
            "negation_count": len(negation_terms),
            "negation_positions": negation_positions,
            "directly_negates_target": directly_negates,
            "scoped_negation_terms": scoped_terms,
        }

    def analyze_with_context(
        self,
        sentence: str,
        previous_sentences: Optional[List[str]] = None,
        next_sentences: Optional[List[str]] = None,
        target_phrase: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyse negation with surrounding context sentences.

        Neighbouring sentences are checked for negation terms that could
        carry over (e.g. "I did not — " split across lines), but they are
        reported separately and do NOT override the scoped result for the
        main sentence.

        Args:
            sentence: Main sentence to analyse.
            previous_sentences: Sentences before (optional).
            next_sentences: Sentences after (optional).
            target_phrase: Target phrase to scope negation against (optional).

        Returns:
            Negation analysis dict (same keys as ``detect_negation``) plus:
            - context_negations: list of neighbouring sentences that contain
                                 negation terms (informational only).
            - has_context_negation: bool
        """
        main_result = self.detect_negation(sentence, target_phrase)

        context_negations = []

        for position, sentences in (
            ("previous", previous_sentences or []),
            ("next", next_sentences or []),
        ):
            for sent in sentences:
                ctx = self.detect_negation(sent)
                if ctx["negation_terms"]:
                    context_negations.append({
                        "position": position,
                        "sentence": sent,
                        "terms": ctx["negation_terms"],
                    })

        main_result["context_negations"] = context_negations
        main_result["has_context_negation"] = len(context_negations) > 0
        return main_result

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _tokenize(self, text: str) -> List[Tuple[str, int]]:
        """
        Return a list of (token, char_start) pairs for every word token in
        ``text``.  Punctuation-only tokens are skipped.
        """
        return [
            (m.group(0), m.start())
            for m in re.finditer(r"\b\w+\b", text)
        ]

    # Conjunctions that mark a clause boundary.  A negation on one side of
    # these words does NOT carry over to a phrase on the other side.
    _CLAUSE_BOUNDARIES = frozenset([
        "but", "and", "or", "nor", "so", "yet", "although", "though",
        "however", "whereas", "while", "whilst", "because", "since",
        "unless", "until", "except",
    ])

    def _scoped_negation(
        self,
        sentence: str,
        target_phrase: str,
        negation_positions: List[Tuple[str, int]],
    ) -> Tuple[bool, List[str]]:
        """
        Determine whether any negation term is within ``self.token_window``
        tokens of ``target_phrase`` in ``sentence``, with two guards:

        1. **Token-distance**: the number of word tokens between the negation
           and the target must be *strictly less than* ``self.token_window``
           (i.e. at most ``token_window - 1`` intervening tokens).

        2. **Clause-boundary**: if a coordinating/subordinating conjunction
           (but, and, or, however, …) appears in the token span between the
           negation and the target, they are in different clauses and the
           negation does NOT apply.

        Args:
            sentence: Original sentence (case-preserved).
            target_phrase: The phrase to check proximity against.
            negation_positions: List of (term, char_start) from the sentence.

        Returns:
            (directly_negates: bool, scoped_terms: List[str])
        """
        sentence_lower = sentence.lower()
        target_lower = target_phrase.lower()

        # Find all occurrences of the target phrase
        target_spans: List[Tuple[int, int]] = []
        start = 0
        while True:
            pos = sentence_lower.find(target_lower, start)
            if pos == -1:
                break
            target_spans.append((pos, pos + len(target_phrase)))
            start = pos + 1

        if not target_spans:
            return False, []

        # Tokenise the full sentence once
        all_tokens = self._tokenize(sentence)
        if not all_tokens:
            return False, []

        def char_to_token_idx(char_pos: int) -> int:
            """Return the index of the token that contains (or is nearest to) char_pos."""
            for idx, (tok, tok_start) in enumerate(all_tokens):
                if tok_start <= char_pos < tok_start + len(tok):
                    return idx
            best, best_dist = 0, abs(all_tokens[0][1] - char_pos)
            for idx, (tok, tok_start) in enumerate(all_tokens):
                d = abs(tok_start - char_pos)
                if d < best_dist:
                    best_dist = d
                    best = idx
            return best

        def has_clause_boundary(from_tok_idx: int, to_tok_idx: int) -> bool:
            """Return True if a clause-boundary conjunction sits between the two token indices."""
            lo, hi = min(from_tok_idx, to_tok_idx), max(from_tok_idx, to_tok_idx)
            for idx in range(lo + 1, hi):
                if all_tokens[idx][0].lower() in self._CLAUSE_BOUNDARIES:
                    return True
            return False

        scoped_terms: List[str] = []

        for neg_term, neg_char_start in negation_positions:
            neg_char_end = neg_char_start + len(neg_term)

            for tgt_start, tgt_end in target_spans:

                # --- Negation BEFORE target ---
                if neg_char_end <= tgt_start:
                    neg_last_tok  = char_to_token_idx(neg_char_end - 1)
                    tgt_first_tok = char_to_token_idx(tgt_start)
                    gap = tgt_first_tok - neg_last_tok - 1
                    # Strict less-than: window=5 → max 4 intervening tokens
                    if 0 <= gap < self.token_window:
                        if not has_clause_boundary(neg_last_tok, tgt_first_tok):
                            if neg_term not in scoped_terms:
                                scoped_terms.append(neg_term)

                # --- Negation AFTER target ---
                elif neg_char_start >= tgt_end:
                    tgt_last_tok  = char_to_token_idx(tgt_end - 1)
                    neg_first_tok = char_to_token_idx(neg_char_start)
                    gap = neg_first_tok - tgt_last_tok - 1
                    if 0 <= gap < self.token_window:
                        if not has_clause_boundary(tgt_last_tok, neg_first_tok):
                            if neg_term not in scoped_terms:
                                scoped_terms.append(neg_term)

                # --- Negation overlaps target ---
                else:
                    if neg_term not in scoped_terms:
                        scoped_terms.append(neg_term)

        return len(scoped_terms) > 0, scoped_terms

    def _score(self, terms: List[str]) -> float:
        """Compute a negation score from a list of (scoped) negation terms."""
        if not terms:
            return 0.0
        base = min(0.5 + (len(terms) - 1) * 0.15, 1.0)
        has_strong = any(t.lower() in self.STRONG_NEGATIONS for t in terms)
        return min(base + 0.2, 1.0) if has_strong else base


class JokeFilter:
    """
    Detect and analyze joke/sarcasm indicators in sentences.
    
    This filter identifies when potentially concerning phrases are used in
    a joking or sarcastic context, which should reduce confidence in matches.
    """
    
    # Joke and sarcasm terms
    JOKE_TERMS = [
        "joke", "joking", "kidding", "sarcastic", "sarcasm",
        "laughed", "everyone laughed", "obviously joking",
        "just kidding", "jk", "lol", "lmao", "haha", "hehe",
        "rofl", "lmfao", "funny", "hilarious", "humor",
        "sarcasm", "sarcastically", "jokingly", "in jest",
        "teasing", "messing with", "pulling your leg",
        "not serious", "not seriously", "as a joke",
        "for laughs", "being silly", "being funny"
    ]
    
    # Emoji patterns for jokes/laughter
    JOKE_EMOJIS = [
        "😂", "🤣", "😆", "😄", "😁", "😅", "😊", "😉",
        "🙃", "😜", "😝", "😛", "🤪", "😏"
    ]
    
    def __init__(self):
        """Initialize the joke filter with compiled patterns."""
        # Create regex patterns for joke detection
        self.joke_patterns = [
            re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
            for term in self.JOKE_TERMS
        ]
        
        # Pattern for emoji detection
        emoji_pattern = '|'.join(re.escape(emoji) for emoji in self.JOKE_EMOJIS)
        self.emoji_pattern = re.compile(emoji_pattern)
        
        # Pattern for common joke phrases
        self.joke_phrase_patterns = [
            re.compile(r'\bjust\s+kidding\b', re.IGNORECASE),
            re.compile(r'\bobviously\s+joking\b', re.IGNORECASE),
            re.compile(r'\beveryone\s+laughed\b', re.IGNORECASE),
            re.compile(r'\bas\s+a\s+joke\b', re.IGNORECASE),
            re.compile(r'\bnot\s+serious(?:ly)?\b', re.IGNORECASE),
            re.compile(r'\bpulling\s+your\s+leg\b', re.IGNORECASE),
        ]
    
    def detect_joke(
        self,
        sentence: str
    ) -> Dict[str, Any]:
        """
        Detect joke/sarcasm indicators in a sentence.
        
        Args:
            sentence: The sentence to analyze
        
        Returns:
            Dictionary containing:
            - is_joke: Boolean indicating if joke indicators are present
            - joke_score: Score from 0.0 (no joke) to 1.0 (strong joke indicators)
            - joke_terms: List of joke terms found
            - joke_emojis: List of joke emojis found
            - joke_phrases: List of joke phrases found
        """
        sentence_lower = sentence.lower()
        joke_terms = []
        joke_emojis = []
        joke_phrases = []
        
        # Find joke terms
        for pattern in self.joke_patterns:
            matches = pattern.finditer(sentence)
            for match in matches:
                term = match.group(0)
                if term.lower() not in [t.lower() for t in joke_terms]:
                    joke_terms.append(term)
        
        # Find joke emojis
        emoji_matches = self.emoji_pattern.finditer(sentence)
        for match in emoji_matches:
            emoji = match.group(0)
            if emoji not in joke_emojis:
                joke_emojis.append(emoji)
        
        # Find joke phrases
        for pattern in self.joke_phrase_patterns:
            match = pattern.search(sentence)
            if match:
                phrase = match.group(0)
                if phrase.lower() not in [p.lower() for p in joke_phrases]:
                    joke_phrases.append(phrase)
        
        # Calculate joke score
        total_indicators = len(joke_terms) + len(joke_emojis) + len(joke_phrases)
        is_joke = total_indicators > 0
        
        if not is_joke:
            joke_score = 0.0
        else:
            # Base score
            base_score = min(0.4 + (total_indicators - 1) * 0.15, 0.9)
            
            # Strong joke indicators get higher scores
            strong_indicators = ["just kidding", "jk", "obviously joking", "as a joke", "lol", "lmao"]
            has_strong = any(
                term.lower() in strong_indicators for term in joke_terms
            ) or len(joke_phrases) > 0
            
            if has_strong:
                joke_score = min(base_score + 0.2, 1.0)
            else:
                joke_score = base_score
        
        return {
            "is_joke": is_joke,
            "joke_score": round(joke_score, 3),
            "joke_terms": joke_terms,
            "joke_emojis": joke_emojis,
            "joke_phrases": joke_phrases,
            "total_indicators": total_indicators
        }
    
    def analyze_with_context(
        self,
        sentence: str,
        previous_sentences: Optional[List[str]] = None,
        next_sentences: Optional[List[str]] = None,
        context_window: int = 2
    ) -> Dict[str, Any]:
        """
        Analyze joke indicators with surrounding context.
        
        If joke appears within ±context_window sentences, it affects the score.
        
        Args:
            sentence: Main sentence to analyze
            previous_sentences: List of previous sentences (optional)
            next_sentences: List of next sentences (optional)
            context_window: Number of sentences to check before/after (default: 2)
        
        Returns:
            Dictionary with joke analysis including context
        """
        # Analyze main sentence
        main_result = self.detect_joke(sentence)
        
        # Analyze context
        context_jokes = []
        
        if previous_sentences:
            # Check up to context_window previous sentences
            for i, prev in enumerate(previous_sentences[-context_window:]):
                prev_result = self.detect_joke(prev)
                if prev_result["is_joke"]:
                    context_jokes.append({
                        "position": f"previous_{i+1}",
                        "sentence": prev,
                        "indicators": prev_result["total_indicators"],
                        "score": prev_result["joke_score"]
                    })
        
        if next_sentences:
            # Check up to context_window next sentences
            for i, nxt in enumerate(next_sentences[:context_window]):
                nxt_result = self.detect_joke(nxt)
                if nxt_result["is_joke"]:
                    context_jokes.append({
                        "position": f"next_{i+1}",
                        "sentence": nxt,
                        "indicators": nxt_result["total_indicators"],
                        "score": nxt_result["joke_score"]
                    })
        
        # Calculate combined joke score
        has_context_joke = len(context_jokes) > 0
        
        if has_context_joke:
            # If jokes in context, increase overall joke score
            max_context_score = max(joke["score"] for joke in context_jokes)
            combined_score = max(main_result["joke_score"], max_context_score * 0.8)
        else:
            combined_score = main_result["joke_score"]
        
        main_result["context_jokes"] = context_jokes
        main_result["has_context_joke"] = has_context_joke
        main_result["combined_joke_score"] = round(combined_score, 3)
        
        return main_result


class CombinedFilter:
    """
    Combined negation and joke filter for comprehensive analysis.
    
    This filter combines both negation and joke detection to provide
    a unified confidence adjustment for pattern matches.
    """
    
    def __init__(self):
        """Initialize combined filter with both negation and joke filters."""
        self.negation_filter = NegationFilter()
        self.joke_filter = JokeFilter()
    
    def analyze(
        self,
        sentence: str,
        previous_sentences: Optional[List[str]] = None,
        next_sentences: Optional[List[str]] = None,
        target_phrase: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Perform combined negation and joke analysis.
        
        Args:
            sentence: Main sentence to analyze
            previous_sentences: List of previous sentences (optional)
            next_sentences: List of next sentences (optional)
            target_phrase: Target phrase to check for negation (optional)
        
        Returns:
            Dictionary containing:
            - is_negated: Boolean
            - is_joke: Boolean
            - negation_score: Float (0.0-1.0)
            - joke_score: Float (0.0-1.0)
            - confidence_penalty: Combined penalty to apply (0.0-1.0)
            - should_reduce_confidence: Boolean recommendation
            - negation_details: Detailed negation analysis
            - joke_details: Detailed joke analysis
        """
        # Analyze negation
        negation_result = self.negation_filter.analyze_with_context(
            sentence=sentence,
            previous_sentences=previous_sentences,
            next_sentences=next_sentences,
            target_phrase=target_phrase
        )
        
        # Analyze jokes
        joke_result = self.joke_filter.analyze_with_context(
            sentence=sentence,
            previous_sentences=previous_sentences,
            next_sentences=next_sentences,
            context_window=2
        )
        
        # Calculate combined confidence penalty
        negation_penalty = negation_result["negation_score"] * 0.4  # Max 40% penalty
        joke_penalty = joke_result["combined_joke_score"] * 0.5  # Max 50% penalty
        
        # If both present, use the maximum penalty (not additive)
        confidence_penalty = max(negation_penalty, joke_penalty)
        
        # If target is directly negated, increase penalty
        if target_phrase and negation_result.get("directly_negates_target", False):
            confidence_penalty = min(confidence_penalty + 0.2, 1.0)
        
        # Recommendation to reduce confidence
        should_reduce = (
            negation_result["is_negated"] or
            joke_result["is_joke"] or
            joke_result["has_context_joke"]
        )
        
        return {
            "is_negated": negation_result["is_negated"],
            "is_joke": joke_result["is_joke"],
            "negation_score": negation_result["negation_score"],
            "joke_score": joke_result["combined_joke_score"],
            "confidence_penalty": round(confidence_penalty, 3),
            "should_reduce_confidence": should_reduce,
            "negation_details": negation_result,
            "joke_details": joke_result
        }
    
    def apply_penalty(
        self,
        base_confidence: float,
        sentence: str,
        previous_sentences: Optional[List[str]] = None,
        next_sentences: Optional[List[str]] = None,
        target_phrase: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Apply confidence penalty based on negation and joke detection.
        
        Args:
            base_confidence: Original confidence score (0.0-1.0)
            sentence: Main sentence
            previous_sentences: Previous sentences (optional)
            next_sentences: Next sentences (optional)
            target_phrase: Target phrase (optional)
        
        Returns:
            Dictionary with adjusted confidence and analysis details
        """
        analysis = self.analyze(
            sentence=sentence,
            previous_sentences=previous_sentences,
            next_sentences=next_sentences,
            target_phrase=target_phrase
        )
        
        # Apply penalty
        penalty = analysis["confidence_penalty"]
        adjusted_confidence = max(0.0, base_confidence - penalty)
        
        return {
            "original_confidence": base_confidence,
            "adjusted_confidence": round(adjusted_confidence, 3),
            "penalty_applied": round(penalty, 3),
            "reduction_percentage": round((penalty / base_confidence * 100) if base_confidence > 0 else 0, 1),
            "analysis": analysis
        }


# Convenience functions
def check_negation(sentence: str, target_phrase: Optional[str] = None) -> Dict[str, Any]:
    """
    Quick negation check for a sentence.
    
    Args:
        sentence: Sentence to check
        target_phrase: Optional target phrase
    
    Returns:
        Negation analysis result
    """
    filter_obj = NegationFilter()
    return filter_obj.detect_negation(sentence, target_phrase)


def check_joke(sentence: str) -> Dict[str, Any]:
    """
    Quick joke check for a sentence.
    
    Args:
        sentence: Sentence to check
    
    Returns:
        Joke analysis result
    """
    filter_obj = JokeFilter()
    return filter_obj.detect_joke(sentence)


def analyze_filters(
    sentence: str,
    neighboring_sentences: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Analyze both negation and joke filters with neighboring sentences.
    
    Args:
        sentence: Main sentence
        neighboring_sentences: List of neighboring sentences (before and after)
    
    Returns:
        Combined analysis result
    """
    # Split neighboring sentences into previous and next
    # Assume first half are previous, second half are next
    previous = None
    next_sent = None
    
    if neighboring_sentences:
        mid = len(neighboring_sentences) // 2
        previous = neighboring_sentences[:mid] if mid > 0 else None
        next_sent = neighboring_sentences[mid:] if mid < len(neighboring_sentences) else None
    
    filter_obj = CombinedFilter()
    return filter_obj.analyze(
        sentence=sentence,
        previous_sentences=previous,
        next_sentences=next_sent
    )


# Export main components
__all__ = [
    'NegationFilter',
    'JokeFilter',
    'CombinedFilter',
    'check_negation',
    'check_joke',
    'analyze_filters'
]
