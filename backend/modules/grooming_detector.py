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
from .ml_classifier import classify_text as ml_classify_text, fuse_with_regex as ml_fuse
from .leetspeak_normalizer import normalize_leetspeak, is_likely_obfuscated


def _normalize_unicode(text: str) -> str:
    """
    Normalize unicode to NFC form and strip zero-width / invisible characters.

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
        """
        self.min_confidence_threshold = min_confidence_threshold
        self.enable_context_analysis  = enable_context_analysis
        self.enable_filters           = enable_filters
        self.enable_grouping          = enable_grouping
        self.enable_ml_classifier     = enable_ml_classifier

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
                    # Fuse ML score into confidence (advisory, 25% weight)
                    fused_confidence = ml_fuse(
                        ml_result=ml_result,
                        regex_confidence=final_confidence,
                        category=category,
                        fusion_weight=0.25,
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
        for category, patterns in PATTERNS.items():
            hits = []
            for pattern in patterns:
                m = pattern.search(sentence)
                if m:
                    hits.append({"text": m.group(0), "start": m.start(), "end": m.end()})
            if hits:
                matches[category] = {"count": len(hits), "matched_patterns": hits}

        # If no matches found on original text, try leetspeak-normalized version
        if not matches and is_likely_obfuscated(sentence):
            normalized = normalize_leetspeak(sentence)
            if normalized != sentence.lower():
                for category, patterns in PATTERNS.items():
                    hits = []
                    for pattern in patterns:
                        m = pattern.search(normalized)
                        if m:
                            hits.append({"text": m.group(0), "start": m.start(), "end": m.end(), "normalized": True})
                    if hits:
                        matches[category] = {"count": len(hits), "matched_patterns": hits, "was_normalized": True}

        return matches

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
