"""
Grooming Detection Engine — Context-Based (v2).

ARCHITECTURE CHANGE:
    Previous version applied speaker-role penalties:
        authority_roles = ["teacher", "principal", "counselor", "parent", ...]
        if any(role in speaker_lower for role in authority_roles):
            final_confidence -= 0.30

    That block has been removed entirely.  The system now evaluates WHAT is
    being said, not WHO is saying it.  Speaker labels are preserved in output
    for audit purposes only — they never influence confidence scores.

Detection Pipeline
------------------
    Transcript
        → Sentence splitting
        → Pattern Detection          (patterns.py)
        → Context Classification     (context_analyzer.ContextType)
        → Negation / Joke Filtering  (filters.CombinedFilter)
        → Confidence Scoring         (confidence.ConfidenceCalculator)
        → Evidence Grouping          (evidence_grouping.EvidenceGroupingEngine)

Output per finding
------------------
    {
        "category":     str,
        "confidence":   float,
        "context_type": str,       ← NEW: ContextType name
        "evidence":     str,
        "categories":   List[str], ← for grouped findings
        ...
    }
"""

import re
import unicodedata
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from .patterns import PATTERNS, PATTERN_CONFIDENCE, CATEGORY_METADATA, match_patterns
from .context_analyzer import ContextAnalyzer, ContextType
from .confidence import ConfidenceCalculator
from .filters import CombinedFilter
from .evidence_grouping import EvidenceGroupingEngine
from .ml_classifier import classify_text as ml_classify_text, fuse_with_regex as ml_fuse, classify_batch as ml_classify_batch
from .leetspeak_normalizer import normalize_leetspeak, is_likely_obfuscated


def _normalize_unicode(text: str) -> str:
    """
    Normalize unicode to NFC form, strip zero-width / invisible characters,
    and replace common homoglyphs with their ASCII equivalents.

    This prevents detection bypass via:
    - Homoglyph substitution (e.g. Cyrillic 'а' vs Latin 'a')
    - Zero-width joiners/non-joiners inserted between characters
    - Combining diacritical marks used to obfuscate words
    """
    # NFC normalization — canonical decomposition followed by canonical composition
    text = unicodedata.normalize("NFC", text)
    # Strip zero-width and invisible formatting characters
    _INVISIBLE_CHARS = frozenset([
        '\u200b',  # zero-width space
        '\u200c',  # zero-width non-joiner
        '\u200d',  # zero-width joiner
        '\u200e',  # left-to-right mark
        '\u200f',  # right-to-left mark
        '\u2060',  # word joiner
        '\u2061',  # function application
        '\u2062',  # invisible times
        '\u2063',  # invisible separator
        '\u2064',  # invisible plus
        '\ufeff',  # BOM / zero-width no-break space
        '\u00ad',  # soft hyphen
    ])
    text = "".join(ch for ch in text if ch not in _INVISIBLE_CHARS)

    # Homoglyph replacement — map visually similar Unicode characters to ASCII
    # This catches Cyrillic, Greek, and other scripts used to bypass detection
    _HOMOGLYPH_MAP = {
        # Cyrillic → Latin
        '\u0410': 'A', '\u0430': 'a',  # А/а
        '\u0412': 'B', '\u0432': 'b',  # В/в (actually looks like B)
        '\u0421': 'C', '\u0441': 'c',  # С/с
        '\u0415': 'E', '\u0435': 'e',  # Е/е
        '\u041d': 'H', '\u043d': 'h',  # Н/н (looks like H)
        '\u041a': 'K', '\u043a': 'k',  # К/к
        '\u041c': 'M', '\u043c': 'm',  # М/м
        '\u041e': 'O', '\u043e': 'o',  # О/о
        '\u0420': 'P', '\u0440': 'p',  # Р/р
        '\u0422': 'T', '\u0442': 't',  # Т/т
        '\u0425': 'X', '\u0445': 'x',  # Х/х
        '\u0443': 'y',                  # у (looks like y)
        '\u0423': 'Y',                  # У
        # Greek → Latin
        '\u0391': 'A', '\u03b1': 'a',  # Α/α
        '\u0392': 'B', '\u03b2': 'b',  # Β/β
        '\u0395': 'E', '\u03b5': 'e',  # Ε/ε
        '\u0397': 'H', '\u03b7': 'h',  # Η/η
        '\u0399': 'I', '\u03b9': 'i',  # Ι/ι
        '\u039a': 'K', '\u03ba': 'k',  # Κ/κ
        '\u039c': 'M',                  # Μ
        '\u039d': 'N',                  # Ν
        '\u039f': 'O', '\u03bf': 'o',  # Ο/ο
        '\u03a1': 'P', '\u03c1': 'p',  # Ρ/ρ
        '\u03a4': 'T', '\u03c4': 't',  # Τ/τ
        '\u03a5': 'Y', '\u03c5': 'y',  # Υ/υ
        '\u03a7': 'X', '\u03c7': 'x',  # Χ/χ
        # Common look-alikes
        '\u0131': 'i',                  # ı (dotless i)
        '\u0237': 'j',                  # ȷ (dotless j)
        '\u1d00': 'a',                  # ᴀ (small capital A)
    }
    text = "".join(_HOMOGLYPH_MAP.get(ch, ch) for ch in text)

    return text


class GroomingDetector:
    """
    Comprehensive grooming detection engine.

    Orchestrates the full detection pipeline.  No speaker-role adjustments
    are applied at any stage.
    """

    def __init__(
        self,
        min_confidence_threshold: float = 0.15,
        enable_context_analysis: bool = True,
        enable_filters: bool = True,
        enable_grouping: bool = True,
        enable_ml_classifier: bool = True,
        ml_max_sentences: int = 50,
    ):
        """
        Args:
            min_confidence_threshold: Minimum confidence to include in results.
            enable_context_analysis:  Apply ContextType multipliers.
            enable_filters:           Apply negation / joke penalties.
            enable_grouping:          Deduplicate via EvidenceGroupingEngine.
            enable_ml_classifier:     Run zero-shot ML classifier as a second
                                      opinion layer. Adds ml_label + ml_confidence
                                      to each finding. Disabled by default on first
                                      run until the model is cached (~1.6 GB download).
                                      Set to True once the model is available locally.
            ml_max_sentences:         Maximum number of findings to run through
                                      the ML classifier (sorted by confidence desc).
                                      Caps worst-case inference time for large transcripts.
        """
        self.min_confidence_threshold = min_confidence_threshold
        self.enable_context_analysis  = enable_context_analysis
        self.enable_filters           = enable_filters
        self.enable_grouping          = enable_grouping
        self.enable_ml_classifier     = enable_ml_classifier
        self.ml_max_sentences         = ml_max_sentences

        self.context_analyzer    = ContextAnalyzer()
        self.confidence_calc     = ConfidenceCalculator()
        self.combined_filter     = CombinedFilter()
        self.grouping_engine     = EvidenceGroupingEngine()

        # Regex to parse "Speaker: text" lines
        self._speaker_re = re.compile(r'^([A-Za-z\s]+):\s*(.+)$')

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def analyze_sentence(
        self,
        sentence: str,
        previous_sentence: Optional[str] = None,
        next_sentence: Optional[str] = None,
        speaker: Optional[str] = None,
        timestamp: Optional[float] = None,
        # Legacy kwargs — accepted but NOT used for scoring
        previous_speaker: Optional[str] = None,
        next_speaker: Optional[str] = None,
        **kwargs,
    ) -> List[Dict[str, Any]]:
        """
        Analyse a single sentence for grooming patterns.

        Speaker is stored in output for audit purposes only.
        It is never used to adjust confidence.

        Args:
            sentence:          Sentence to analyse.
            previous_sentence: Previous sentence for context window.
            next_sentence:     Next sentence for context window.
            speaker:           Speaker label (audit only, not scored).
            timestamp:         Sentence timestamp.

        Returns:
            List of detection dicts (one per matched category).
        """
        if not sentence or not sentence.strip():
            return []

        # Unicode normalization — prevent bypass via homoglyphs / invisible chars
        sentence = _normalize_unicode(sentence)
        if previous_sentence:
            previous_sentence = _normalize_unicode(previous_sentence)
        if next_sentence:
            next_sentence = _normalize_unicode(next_sentence)

        # Extract embedded speaker label if present
        if not speaker:
            m = self._speaker_re.match(sentence)
            if m:
                speaker  = m.group(1).strip()
                sentence = m.group(2).strip()

        # Step 1 — Pattern detection
        pattern_matches = self._detect_patterns(sentence)
        if not pattern_matches:
            return []

        # Step 1b — Safe-phrase allowlist (suppress known false positives)
        from modules.safe_phrases import is_safe_phrase
        pattern_matches = {
            cat: info for cat, info in pattern_matches.items()
            if not is_safe_phrase(sentence, cat)
        }
        if not pattern_matches:
            return []

        # Step 2 — Context classification (content-based, no roles)
        ctx_result = None
        if self.enable_context_analysis:
            ctx_result = self.context_analyzer.classify(
                sentence, previous_sentence, next_sentence
            )

        prev_list = [previous_sentence] if previous_sentence else None
        next_list = [next_sentence]     if next_sentence     else None

        results: List[Dict[str, Any]] = []

        for category, match_info in pattern_matches.items():
            pattern_strength = PATTERN_CONFIDENCE.get(category, 0.5)

            matched_text = sentence
            if match_info.get("matched_patterns"):
                matched_text = match_info["matched_patterns"][0].get("text", sentence)

            # Step 3 — Confidence with context multiplier
            conf_result = self.confidence_calc.calculate(
                category=category,
                matched_text=matched_text,
                sentence=sentence,
                pattern_strength=pattern_strength,
                previous_sentence=previous_sentence,
                next_sentence=next_sentence,
            )
            base_confidence = conf_result["confidence"]
            context_type    = conf_result.get("context_type", ContextType.NEUTRAL.value)

            # Step 4 — Negation / joke filter (scoped to matched phrase)
            filter_result  = None
            filter_penalty = 0.0
            final_confidence = base_confidence

            if self.enable_filters:
                filter_result = self.combined_filter.analyze(
                    sentence=sentence,
                    previous_sentences=prev_list,
                    next_sentences=next_list,
                    target_phrase=matched_text,
                )
                filter_penalty   = filter_result.get("confidence_penalty", 0.0)
                final_confidence = max(0.0, base_confidence - filter_penalty)

            # Threshold gate
            if final_confidence < self.min_confidence_threshold:
                continue

            metadata = CATEGORY_METADATA.get(category)

            finding: Dict[str, Any] = {
                "category":     category,
                "confidence":   round(final_confidence, 4),
                "context_type": context_type,          # ← NEW field
                "evidence":     sentence,
                "matched_text": matched_text,
                "pattern_count": match_info.get("count", 1),
                "severity":     metadata.severity if metadata else "unknown",
                "weight":       metadata.weight   if metadata else 0.5,
                "timestamp":    timestamp or datetime.now().timestamp(),
                "speaker":      speaker,             # audit only
                "categories":   [category],          # for grouped-finding compat
                "scoring": {
                    "pattern_strength":  round(pattern_strength, 4),
                    "base_confidence":   round(base_confidence, 4),
                    "filter_penalty":    round(filter_penalty, 4),
                    "final_confidence":  round(final_confidence, 4),
                    "context_multiplier": conf_result["breakdown"].get("context_multiplier", 0.0),
                },
            }

            # Context details
            if ctx_result:
                finding["context"] = {
                    "primary":        ctx_result["primary_context"].value,
                    "all_contexts":   [ct.value for ct in ctx_result["all_contexts"]],
                    "multiplier":     ctx_result["multiplier"],
                    "is_administrative": ctx_result["is_administrative"],
                    "matched_terms":  {
                        ct.value: terms
                        for ct, terms in ctx_result["matched_terms"].items()
                    },
                    # Legacy keys for downstream consumers
                    "safe":           ctx_result["is_administrative"],
                    "risk":           ctx_result["primary_context"] not in (
                        ContextType.NEUTRAL, ContextType.ADMINISTRATIVE
                    ),
                    "dominant":       ctx_result.get("dominant_context", "neutral"),
                }

            # Filter details
            if filter_result:
                finding["filters"] = {
                    "is_negated":     filter_result.get("is_negated", False),
                    "is_joke":        filter_result.get("is_joke", False),
                    "negation_score": filter_result.get("negation_score", 0.0),
                    "joke_score":     filter_result.get("joke_score", 0.0),
                }

            # Step 5 — ML zero-shot classifier (second opinion + confidence fusion)
            # • Passes regex category so ML can compute agreement signal.
            # • fuse_with_regex() blends ML score into confidence (25% weight).
            # • Full ML result block stored in finding["ml"] for downstream use.
            if self.enable_ml_classifier:
                try:
                    ml_result = ml_classify_text(
                        sentence,
                        regex_categories=[category],
                    )
                    # Dynamic ML fusion weight — trust ML more when it's confident
                    ml_conf = ml_result["top_confidence"]
                    if ml_conf >= 0.80:
                        _fusion_weight = 0.45  # ML is very confident
                    elif ml_conf >= 0.60:
                        _fusion_weight = 0.35  # ML is moderately confident
                    else:
                        _fusion_weight = 0.25  # Low confidence — minimal influence

                    fused_confidence = ml_fuse(
                        ml_result=ml_result,
                        regex_confidence=final_confidence,
                        category=category,
                        fusion_weight=_fusion_weight,
                    )
                    finding["confidence"] = fused_confidence
                    finding["scoring"]["ml_fused_confidence"] = fused_confidence
                    finding["scoring"]["ml_fusion_delta"] = round(
                        fused_confidence - final_confidence, 4
                    )
                    # Full ML result block
                    finding["ml"] = {
                        "top_label":         ml_result["top_label"],
                        "top_confidence":    ml_result["top_confidence"],
                        "matched_labels":    ml_result["matched_labels"],
                        "ml_risk_score":     ml_result["ml_risk_score"],
                        "is_safe":           ml_result["is_safe"],
                        "agreement":         ml_result["agreement"],
                        "disagreement_flag": ml_result["disagreement_flag"],
                        "all_scores":        ml_result["all_scores"],
                    }
                    # Legacy flat fields for backward compat
                    finding["ml_label"]      = ml_result["top_label"]
                    finding["ml_confidence"] = ml_result["top_confidence"]
                except Exception as ml_err:
                    finding["ml"] = {"error": str(ml_err)}
                    finding["ml_label"]      = "unavailable"
                    finding["ml_confidence"] = 0.0

            results.append(finding)

        return results

    def analyze_transcript(
        self,
        transcript: str,
        speaker_aware: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyse a full conversation transcript.

        Args:
            transcript:    Full transcript text (may include "Speaker: text" lines).
            speaker_aware: Parse speaker labels (stored for audit, not scored).

        Returns:
            {
                "findings":         List[Dict],
                "grouped_findings": List[Dict],
                "summary":          Dict,
                "metadata":         Dict,
            }
        """
        sentences = self._split_transcript(transcript)

        if not sentences:
            return {
                "findings":         [],
                "grouped_findings": [],
                "summary":          self._empty_summary(),
                "metadata": {
                    "total_sentences": 0,
                    "analyzed_at":     datetime.now(timezone.utc).isoformat(),
                },
            }

        all_findings: List[Dict[str, Any]] = []

        # ── Pass 1: Regex detection WITHOUT ML (fast) ─────────────────────
        # Temporarily disable ML to collect all regex findings first.
        # ML will be applied selectively in pass 2 to cap inference time.
        original_ml_setting = self.enable_ml_classifier
        self.enable_ml_classifier = False

        for i, sent_data in enumerate(sentences):
            sentence = sent_data["text"]
            speaker  = sent_data.get("speaker") if speaker_aware else None

            previous = sentences[i - 1]["text"] if i > 0 else None
            next_s   = sentences[i + 1]["text"] if i < len(sentences) - 1 else None

            findings = self.analyze_sentence(
                sentence=sentence,
                previous_sentence=previous,
                next_sentence=next_s,
                speaker=speaker,
                timestamp=float(i),
            )
            all_findings.extend(findings)

        # Restore ML setting
        self.enable_ml_classifier = original_ml_setting

        # ── Pass 2: Apply ML classifier to top-N findings only ────────────
        # Sort by confidence (desc) and only run NLI on the most relevant
        # findings. This caps worst-case time for large transcripts while
        # preserving accuracy for the highest-signal detections.
        if original_ml_setting and all_findings:
            # Sort descending by confidence, run ML on top N
            sorted_indices = sorted(
                range(len(all_findings)),
                key=lambda idx: all_findings[idx].get("confidence", 0),
                reverse=True,
            )
            ml_limit = self.ml_max_sentences
            ml_indices = sorted_indices[:ml_limit]

            # Batch inference — process all selected findings in one call
            batch_texts = [all_findings[idx].get("evidence", "") for idx in ml_indices]
            batch_categories = [[all_findings[idx].get("category", "")] for idx in ml_indices]

            try:
                batch_results = ml_classify_batch(batch_texts, batch_categories)

                for batch_i, idx in enumerate(ml_indices):
                    finding = all_findings[idx]
                    final_confidence = finding.get("confidence", 0.0)
                    ml_result = batch_results[batch_i]

                    # Dynamic ML fusion weight
                    ml_conf = ml_result["top_confidence"]
                    if ml_conf >= 0.80:
                        _fusion_weight = 0.45
                    elif ml_conf >= 0.60:
                        _fusion_weight = 0.35
                    else:
                        _fusion_weight = 0.25

                    category = finding.get("category", "")
                    fused_confidence = ml_fuse(
                        ml_result=ml_result,
                        regex_confidence=final_confidence,
                        category=category,
                        fusion_weight=_fusion_weight,
                    )
                    finding["confidence"] = fused_confidence
                    finding["scoring"]["ml_fused_confidence"] = fused_confidence
                    finding["scoring"]["ml_fusion_delta"] = round(
                        fused_confidence - final_confidence, 4
                    )
                    finding["ml"] = {
                        "top_label":         ml_result["top_label"],
                        "top_confidence":    ml_result["top_confidence"],
                        "matched_labels":    ml_result["matched_labels"],
                        "ml_risk_score":     ml_result["ml_risk_score"],
                        "is_safe":           ml_result["is_safe"],
                        "agreement":         ml_result["agreement"],
                        "disagreement_flag": ml_result["disagreement_flag"],
                        "all_scores":        ml_result["all_scores"],
                    }
                    finding["ml_label"]      = ml_result["top_label"]
                    finding["ml_confidence"] = ml_result["top_confidence"]
            except Exception as ml_err:
                logger.warning(f"Batch ML classification failed: {ml_err}")
                for idx in ml_indices:
                    all_findings[idx]["ml"] = {"error": str(ml_err)}
                    all_findings[idx]["ml_label"] = "unavailable"
                    all_findings[idx]["ml_confidence"] = 0.0

        # ── Pass 3: ML standalone scan for sentences regex missed ─────────
        # Run ML classifier on a sample of sentences that had NO regex match.
        # This catches subtle/novel grooming patterns the regex rules miss.
        if original_ml_setting:
            detected_indices = set()
            for f in all_findings:
                ts = int(f.get("timestamp", -1))
                if ts >= 0:
                    detected_indices.add(ts)

            # Pick sentences that regex missed, prioritizing longer/more complex ones
            missed_sentences = [
                (i, s) for i, s in enumerate(sentences)
                if i not in detected_indices and len(s["text"].strip()) > 30
            ]
            # Limit to 20 standalone ML checks
            ml_standalone_limit = min(20, len(missed_sentences))
            if ml_standalone_limit > 0:
                # Sort by sentence length (longer = more likely to contain nuance)
                missed_sentences.sort(key=lambda x: len(x[1]["text"]), reverse=True)
                standalone_batch = missed_sentences[:ml_standalone_limit]

                try:
                    standalone_texts = [s["text"] for _, s in standalone_batch]
                    standalone_results = ml_classify_batch(standalone_texts)

                    for (sent_idx, sent_data), ml_result in zip(standalone_batch, standalone_results):
                        # Only add if ML is confident about a risk category
                        # Use high threshold (0.55) to avoid false positives on safe content
                        if (not ml_result.get("is_safe")
                            and ml_result.get("top_confidence", 0) >= 0.55
                            and ml_result.get("top_label") != "unknown"):

                            top_label = ml_result["top_label"]
                            ml_conf = ml_result["top_confidence"]

                            finding = {
                                "category":     top_label,
                                "confidence":   round(ml_conf * 0.55, 4),  # discount since no regex backing
                                "context_type": "ml_standalone",
                                "evidence":     sent_data["text"],
                                "matched_text": sent_data["text"],
                                "pattern_count": 0,
                                "severity":     "moderate",
                                "weight":       0.5,
                                "timestamp":    float(sent_idx),
                                "speaker":      sent_data.get("speaker"),
                                "categories":   ml_result.get("matched_labels", [top_label])[:3],
                                "scoring": {
                                    "pattern_strength":  0.0,
                                    "base_confidence":   0.0,
                                    "ml_standalone":     True,
                                    "ml_fused_confidence": round(ml_conf * 0.55, 4),
                                },
                                "ml": {
                                    "top_label":         top_label,
                                    "top_confidence":    ml_conf,
                                    "matched_labels":    ml_result.get("matched_labels", []),
                                    "ml_risk_score":     ml_result.get("ml_risk_score", 0),
                                    "is_safe":           False,
                                    "agreement":         None,
                                    "disagreement_flag": False,
                                    "all_scores":        ml_result.get("all_scores", {}),
                                    "standalone":        True,
                                },
                                "ml_label":      top_label,
                                "ml_confidence": ml_conf,
                            }
                            all_findings.append(finding)
                except Exception as e:
                    logger.warning(f"ML standalone scan failed: {e}")

        # ── Behavioral pattern detection (cross-sentence) ─────────────────
        # Detects grooming tactics that are only visible across the full
        # conversation — subtle patterns that individual sentences miss.
        behavioral_findings = self._detect_behavioral_patterns(sentences, all_findings)
        all_findings.extend(behavioral_findings)

        # ── Educational context penalty ───────────────────────────────────
        # If the transcript is primarily educational/professional, reduce
        # confidence on all findings to suppress false positives.
        from modules.educational_context import apply_educational_penalty
        all_findings = apply_educational_penalty(all_findings, transcript)

        grouped = all_findings
        if self.enable_grouping and all_findings:
            grouped = self.grouping_engine.group_findings(all_findings)

        return {
            "findings":         all_findings,
            "grouped_findings": grouped,
            "summary":          self._create_summary(grouped),
            "metadata": {
                "total_sentences":   len(sentences),
                "total_findings":    len(all_findings),
                "grouped_findings":  len(grouped),
                "analyzed_at":       datetime.now(timezone.utc).isoformat(),
                "min_confidence_threshold": self.min_confidence_threshold,
            },
        }

    def detect_patterns(
        self,
        text: str,
        category: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lightweight pattern detection without full pipeline."""
        return match_patterns(text, category)

    def get_category_info(self, category: str) -> Optional[Dict[str, Any]]:
        if category not in CATEGORY_METADATA:
            return None
        meta = CATEGORY_METADATA[category]
        return {
            "name":          meta.name,
            "description":   meta.description,
            "severity":      meta.severity,
            "weight":        meta.weight,
            "confidence":    PATTERN_CONFIDENCE.get(category, 0.5),
            "pattern_count": len(PATTERNS.get(category, [])),
        }

    def get_all_categories(self) -> List[str]:
        return list(PATTERNS.keys())

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _detect_patterns(self, sentence: str) -> Dict[str, Dict[str, Any]]:
        matches: Dict[str, Dict[str, Any]] = {}

        # Always try leetspeak normalization first if text looks obfuscated
        normalized = None
        if is_likely_obfuscated(sentence):
            normalized = normalize_leetspeak(sentence)
            if normalized == sentence.lower():
                normalized = None  # No change, skip

        # Run pattern matching on BOTH original and normalized text
        for category, patterns in PATTERNS.items():
            hits = []
            for pattern in patterns:
                # Match on original text
                m = pattern.search(sentence)
                if m:
                    hits.append({"text": m.group(0), "start": m.start(), "end": m.end()})
                # Also match on normalized text (catches obfuscated variants)
                elif normalized:
                    m = pattern.search(normalized)
                    if m:
                        hits.append({"text": m.group(0), "start": m.start(), "end": m.end(), "normalized": True})
            if hits:
                matches[category] = {
                    "count": len(hits),
                    "matched_patterns": hits,
                    "was_normalized": any(h.get("normalized") for h in hits),
                }

        return matches

        return matches

    def _detect_behavioral_patterns(
        self,
        sentences: List[Dict[str, str]],
        existing_findings: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Detect grooming behavioral patterns across the full conversation.

        These are patterns that individual sentence analysis misses because
        each line looks innocent in isolation, but the combination reveals
        grooming tactics:
        - Age gap acknowledgment + continued engagement
        - Schedule/routine probing (asking when alone, when parents leave)
        - Isolation tactics (undermining friends/family, "only I understand")
        - Gift-giving + secrecy about gifts
        - Requesting private communication channels
        - Flattery + "you're mature/special" + age-inappropriate interest
        - Planning to meet + secrecy about meeting
        """
        if len(sentences) < 4:
            return []

        behavioral_findings: List[Dict[str, Any]] = []
        full_text = " ".join(s["text"].lower() for s in sentences)

        # Track which categories were already detected by regex
        existing_categories = set()
        for f in existing_findings:
            cats = f.get("categories") or ([f.get("category")] if f.get("category") else [])
            existing_categories.update(cats)

        # ── Behavioral signals (soft indicators that accumulate) ──────────
        signals = {
            "age_gap": False,
            "flattery": 0,
            "isolation": 0,
            "schedule_probing": 0,
            "secrecy_hints": 0,
            "gift_offering": 0,
            "private_channel": 0,
            "meeting_intent": 0,
            "trust_building": 0,
            "normalization": 0,
            "parental_avoidance": 0,
        }

        # Behavioral indicator patterns (softer than the main regex patterns)
        _behavioral_indicators = {
            "age_gap": [
                re.compile(r'\b(?:how\s+old|what\s+age|age\s+(?:doesn.?t|does\s+not)\s+matter|just\s+a\s+number|bit\s+older|few\s+years?\s+older|doesn.?t\s+matter\s+though)', re.I),
                re.compile(r'\b(?:i.?m\s+\d{2}|i\s+am\s+\d{2}|nineteen|twenty|twenty.?one|eighteen)', re.I),
            ],
            "flattery": [
                re.compile(r'\b(?:you.?re\s+(?:so\s+)?(?:special|unique|different|mature|talented|amazing|beautiful|gorgeous|smart|cool|interesting))', re.I),
                re.compile(r'\b(?:not\s+like\s+(?:other|most)\s+(?:kids?|people|girls?|boys?|teens?))', re.I),
                re.compile(r'\b(?:more\s+mature|above\s+your\s+(?:age|level|years?))', re.I),
                re.compile(r'\b(?:great\s+taste|you\s+have\s+great)', re.I),
            ],
            "isolation": [
                re.compile(r'\b(?:they\s+(?:don.?t|won.?t|wouldn.?t)\s+(?:understand|get\s+it|appreciate))', re.I),
                re.compile(r'\b(?:(?:your\s+)?friends?\s+(?:don.?t|won.?t)\s+(?:understand|appreciate|get))', re.I),
                re.compile(r'\b(?:only\s+I\s+(?:understand|get|know|appreciate)|I\s+get\s+you\s+in\s+ways)', re.I),
                re.compile(r'\b(?:not\s+everyone\s+(?:can|would|will)\s+(?:understand|appreciate|get))', re.I),
                re.compile(r'\b(?:what\s+we\s+have\s+is\s+(?:different|special|unique))', re.I),
                re.compile(r'\b(?:deeper\s+connection|nobody\s+else)', re.I),
            ],
            "schedule_probing": [
                re.compile(r'\b(?:what\s+time(?:s)?\s+(?:are|do)\s+you|when\s+(?:are|do)\s+you\s+(?:usually|normally|free|available|home|online|on))', re.I),
                re.compile(r'\b(?:when\s+(?:do\s+)?(?:your\s+)?(?:parents?|mom|dad|family)\s+(?:go|leave|are\s+(?:gone|away|out)))', re.I),
                re.compile(r'\b(?:(?:is\s+)?anyone\s+(?:usually\s+)?(?:around|home|there)|are\s+you\s+(?:alone|by\s+yourself))', re.I),
                re.compile(r'\b(?:what\s+(?:days?|nights?|evenings?)\s+(?:work|are\s+(?:best|good)))', re.I),
                re.compile(r'\b(?:after\s+(?:school|dinner|practice)|late\s+(?:night|at\s+night))', re.I),
                re.compile(r'\b(?:walk\s+home|get\s+home|how\s+(?:do\s+you\s+)?get\s+home)', re.I),
            ],
            "secrecy_hints": [
                re.compile(r'\b(?:between\s+(?:us|you\s+and\s+me)|just\s+(?:our|between\s+us|for\s+us))', re.I),
                re.compile(r'\b(?:don.?t\s+(?:mention|tell|say\s+anything)|keep\s+(?:it|this)\s+(?:between|private|quiet|to\s+yourself))', re.I),
                re.compile(r'\b(?:(?:they|people|others?)\s+(?:will|would|might)\s+(?:ruin|not\s+understand|misunderstand|judge|overreact))', re.I),
                re.compile(r'\b(?:our\s+(?:thing|secret|friendship\s+is\s+(?:special|private)))', re.I),
                re.compile(r'\b(?:stays?\s+between\s+us|privacy|respect\s+(?:that\s+kind\s+of\s+)?privacy)', re.I),
            ],
            "gift_offering": [
                re.compile(r'\b(?:I.?(?:ll|will|can|could)\s+(?:buy|get|send|give)\s+(?:you|u))', re.I),
                re.compile(r'\b(?:gift|present|surprise|treat|reward)\s+(?:for\s+you|I\s+have)', re.I),
                re.compile(r'\b(?:I\s+(?:have|got)\s+(?:a|an|something|an?\s+extra))', re.I),
                re.compile(r'\b(?:(?:don.?t|no\s+need\s+to)\s+worry\s+about\s+(?:money|paying|cost|the\s+price))', re.I),
                re.compile(r'\b(?:I.?(?:ll|will|can)\s+(?:arrange|pay\s+for|take\s+care\s+of)\s+everything)', re.I),
            ],
            "private_channel": [
                re.compile(r'\b(?:(?:do\s+you\s+have|what.?s\s+your)\s+(?:discord|snapchat|snap|insta|instagram|whatsapp|telegram|kik|signal))', re.I),
                re.compile(r'\b(?:(?:add|follow|dm|message)\s+me\s+(?:on|at))', re.I),
                re.compile(r'\b(?:voice\s+chat|video\s+call|webcam|camera)', re.I),
                re.compile(r'\b(?:(?:send|share|give)\s+(?:me\s+)?(?:your\s+)?(?:address|number|location))', re.I),
            ],
            "meeting_intent": [
                re.compile(r'\b(?:(?:we\s+could|I\s+could|maybe\s+we)\s+(?:meet|hang\s+out|get\s+together|go\s+together))', re.I),
                re.compile(r'\b(?:(?:pick\s+(?:you\s+)?up|come\s+(?:by|over|get\s+you)|take\s+you))', re.I),
                re.compile(r'\b(?:(?:in\s+person|face\s+to\s+face|irl|somewhere\s+(?:private|fun|nice)))', re.I),
                re.compile(r'\b(?:(?:arrange|plan|figure\s+(?:something|it)\s+out))', re.I),
                re.compile(r'\b(?:ask\s+forgiveness\s+(?:than|rather\s+than)\s+permission)', re.I),
            ],
            "trust_building": [
                re.compile(r'\b(?:I\s+(?:really\s+)?(?:care|understand|get\s+you|feel\s+(?:like|close)))', re.I),
                re.compile(r'\b(?:(?:we\s+really\s+)?(?:get|understand)\s+each\s+other)', re.I),
                re.compile(r'\b(?:(?:I\s+)?feel\s+like\s+we\s+(?:really\s+)?(?:connect|click|get\s+each\s+other))', re.I),
                re.compile(r'\b(?:(?:you\s+can\s+)?(?:tell|share|say)\s+(?:me\s+)?anything)', re.I),
                re.compile(r'\b(?:(?:whatever\s+you\s+)?share\s+(?:with\s+me\s+)?stays)', re.I),
            ],
            "normalization": [
                re.compile(r'\b(?:(?:it.?s|that.?s)\s+(?:totally|completely|perfectly|absolutely)?\s*(?:normal|natural|fine|okay|common))', re.I),
                re.compile(r'\b(?:everyone\s+(?:does|is\s+doing)\s+(?:it|this))', re.I),
                re.compile(r'\b(?:(?:don.?t\s+be)\s+(?:immature|childish|silly|scared|shy|embarrassed))', re.I),
                re.compile(r'\b(?:growing\s+up|part\s+of\s+growing|phase)', re.I),
            ],
            "parental_avoidance": [
                re.compile(r'\b(?:(?:your\s+)?(?:parents?|mom|dad)\s+(?:probably\s+)?(?:won.?t|wouldn.?t)\s+(?:let|allow|understand|approve))', re.I),
                re.compile(r'\b(?:(?:don.?t|do\s+not)\s+(?:mention|tell)\s+(?:(?:it|this)\s+to\s+)?(?:your\s+)?(?:parents?|mom|dad|mother|father))', re.I),
                re.compile(r'\b(?:(?:she|he|they)\s+(?:might|would|will)\s+(?:think\s+it.?s\s+weird|not\s+understand|overreact|freak\s+out))', re.I),
                re.compile(r'\b(?:(?:easier\s+to\s+)?ask\s+forgiveness|without\s+(?:them|your\s+parents?)\s+knowing)', re.I),
            ],
        }

        # Scan all sentences for behavioral signals
        for sent_data in sentences:
            text = sent_data["text"]
            for signal_type, patterns in _behavioral_indicators.items():
                for pattern in patterns:
                    if pattern.search(text):
                        if signal_type == "age_gap":
                            signals["age_gap"] = True
                        else:
                            signals[signal_type] += 1
                        break  # One match per signal type per sentence

        # ── Calculate behavioral risk score ───────────────────────────────
        # Each signal type contributes to a behavioral score.
        # Multiple signal types co-occurring is much more suspicious.
        behavioral_score = 0.0
        triggered_behaviors = []

        # Weights for each behavioral signal
        _signal_weights = {
            "age_gap":             8.0,
            "flattery":            4.0,   # per occurrence
            "isolation":           7.0,   # per occurrence
            "schedule_probing":    5.0,   # per occurrence
            "secrecy_hints":       8.0,   # per occurrence
            "gift_offering":       6.0,   # per occurrence
            "private_channel":     5.0,   # per occurrence
            "meeting_intent":      8.0,   # per occurrence
            "trust_building":      3.0,   # per occurrence
            "normalization":       6.0,   # per occurrence
            "parental_avoidance":  7.0,   # per occurrence
        }

        for signal_type, count_or_flag in signals.items():
            if signal_type == "age_gap":
                if count_or_flag:
                    behavioral_score += _signal_weights["age_gap"]
                    triggered_behaviors.append("age_gap")
            else:
                if count_or_flag > 0:
                    # Diminishing returns: first occurrence full weight, subsequent half
                    weight = _signal_weights.get(signal_type, 3.0)
                    score_contribution = weight + (count_or_flag - 1) * (weight * 0.4)
                    behavioral_score += score_contribution
                    triggered_behaviors.append(f"{signal_type}({count_or_flag})")

        # ── Co-occurrence multiplier ──────────────────────────────────────
        # Multiple different grooming tactics together is much more suspicious
        distinct_signals = len(triggered_behaviors)
        if distinct_signals >= 5:
            behavioral_score *= 1.5
        elif distinct_signals >= 4:
            behavioral_score *= 1.3
        elif distinct_signals >= 3:
            behavioral_score *= 1.15

        # Only generate behavioral findings if score is significant
        # and the existing regex findings didn't already catch enough
        existing_score_estimate = sum(
            (f.get("confidence", 0) * CATEGORY_METADATA.get(
                (f.get("categories") or [f.get("category", "")])[0], 
                type("", (), {"weight": 0.5})()
            ).weight * 20)
            for f in existing_findings
        )

        # If behavioral analysis found significant patterns not caught by regex
        # Require high behavioral score AND multiple distinct HIGH-RISK signals
        # to avoid false positives on innocent conversations
        high_risk_signals = {"isolation", "secrecy_hints", "meeting_intent", 
                            "parental_avoidance", "normalization"}
        high_risk_triggered = sum(
            1 for b in triggered_behaviors 
            if b.split("(")[0] in high_risk_signals
        )
        
        if behavioral_score >= 20 and distinct_signals >= 3 and high_risk_triggered >= 2:
            # Create synthetic findings for behavioral patterns not already detected
            confidence = min(0.90, behavioral_score / 100.0 + 0.3)

            # Map behavioral signals to categories
            _signal_to_category = {
                "isolation": "isolation",
                "secrecy_hints": "secrecy",
                "gift_offering": "gift_bribery",
                "meeting_intent": "meeting",
                "schedule_probing": "routine",
                "private_channel": "video_call",
                "normalization": "desensitization",
                "parental_avoidance": "parent_monitoring",
                "trust_building": "trust_building",
                "flattery": "relationship_building",
                "age_gap": "age_deception",
            }

            for signal_type in triggered_behaviors:
                # Strip count suffix like "isolation(2)"
                base_signal = signal_type.split("(")[0]
                category = _signal_to_category.get(base_signal)
                if not category or category in existing_categories:
                    continue

                metadata = CATEGORY_METADATA.get(category)
                if not metadata:
                    continue

                behavioral_findings.append({
                    "category":     category,
                    "confidence":   round(confidence, 4),
                    "context_type": "BEHAVIORAL_PATTERN",
                    "evidence":     f"[Behavioral] Cross-conversation {base_signal.replace('_', ' ')} pattern detected ({distinct_signals} co-occurring grooming signals)",
                    "matched_text": f"behavioral:{base_signal}",
                    "pattern_count": signals.get(base_signal, 1) if isinstance(signals.get(base_signal), int) else 1,
                    "severity":     metadata.severity,
                    "weight":       metadata.weight,
                    "timestamp":    float(len(sentences) - 1),
                    "speaker":      None,
                    "categories":   [category],
                    "scoring": {
                        "pattern_strength":  round(confidence, 4),
                        "base_confidence":   round(confidence, 4),
                        "filter_penalty":    0.0,
                        "final_confidence":  round(confidence, 4),
                        "behavioral_score":  round(behavioral_score, 2),
                        "distinct_signals":  distinct_signals,
                        "triggered":         triggered_behaviors,
                    },
                })
                existing_categories.add(category)

        return behavioral_findings

    def _split_transcript(self, transcript: str) -> List[Dict[str, str]]:
        sentences: List[Dict[str, str]] = []
        for line in transcript.split("\n"):
            line = line.strip()
            if not line:
                continue
            m = self._speaker_re.match(line)
            if m:
                sentences.append({"text": m.group(2).strip(), "speaker": m.group(1).strip()})
            else:
                for sent in re.split(r"[.!?]+", line):
                    sent = sent.strip()
                    if sent:
                        sentences.append({"text": sent, "speaker": None})
        return sentences

    def _create_summary(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not findings:
            return self._empty_summary()

        cat_counts: Dict[str, int]  = {}
        sev_counts: Dict[str, int]  = {}
        ctx_counts: Dict[str, int]  = {}
        confidences: List[float]    = []

        for f in findings:
            cats = f.get("categories") or ([f["category"]] if f.get("category") else [])
            for c in cats:
                cat_counts[c] = cat_counts.get(c, 0) + 1

            sev = f.get("severity")
            if sev:
                sev_counts[sev] = sev_counts.get(sev, 0) + 1

            ctx = f.get("context_type") or (
                f.get("context", {}).get("primary") if isinstance(f.get("context"), dict) else None
            )
            if ctx:
                ctx_counts[ctx] = ctx_counts.get(ctx, 0) + 1

            conf = f.get("confidence") or f.get("max_confidence")
            if conf:
                confidences.append(float(conf))

        avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
        max_conf = max(confidences) if confidences else 0.0
        min_conf = min(confidences) if confidences else 0.0

        return {
            "total_findings":          len(findings),
            "category_distribution":   cat_counts,
            "severity_distribution":   sev_counts,
            "context_type_distribution": ctx_counts,
            "confidence_stats": {
                "average": round(avg_conf, 3),
                "maximum": round(max_conf, 3),
                "minimum": round(min_conf, 3),
            },
            "risk_level":                self._assess_risk(findings),
            "high_confidence_findings":  sum(1 for f in findings if (f.get("confidence") or f.get("max_confidence", 0)) >= 0.7),
            "critical_severity_findings": sum(1 for f in findings if f.get("severity") == "critical"),
        }

    def _empty_summary(self) -> Dict[str, Any]:
        return {
            "total_findings": 0,
            "category_distribution": {},
            "severity_distribution": {},
            "context_type_distribution": {},
            "confidence_stats": {"average": 0.0, "maximum": 0.0, "minimum": 0.0},
            "risk_level": "none",
            "high_confidence_findings": 0,
            "critical_severity_findings": 0,
        }

    def _assess_risk(self, findings: List[Dict[str, Any]]) -> str:
        if not findings:
            return "none"
        critical = sum(1 for f in findings if f.get("severity") == "critical")
        high     = sum(1 for f in findings if f.get("severity") == "high")
        hi_conf  = sum(1 for f in findings if (f.get("confidence") or f.get("max_confidence", 0)) >= 0.7)
        if critical >= 3 or (critical >= 1 and hi_conf >= 2):
            return "critical"
        if critical >= 1 or high >= 3 or hi_conf >= 3:
            return "high"
        if high >= 1 or hi_conf >= 1 or len(findings) >= 5:
            return "medium"
        return "low"


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def analyze_text(text: str, min_confidence: float = 0.15) -> Dict[str, Any]:
    """Quick convenience wrapper for full transcript analysis."""
    return GroomingDetector(min_confidence_threshold=min_confidence).analyze_transcript(text)


def detect_grooming_patterns(
    sentence: str,
    context: Optional[Dict[str, str]] = None,
) -> List[Dict[str, Any]]:
    """Quick convenience wrapper for single-sentence analysis."""
    detector = GroomingDetector()
    return detector.analyze_sentence(
        sentence=sentence,
        previous_sentence=context.get("previous") if context else None,
        next_sentence=context.get("next")     if context else None,
    )


__all__ = ["GroomingDetector", "analyze_text", "detect_grooming_patterns"]
