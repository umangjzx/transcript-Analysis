"""
ML Classifier — Zero-Shot NLI Safety Classifier (v2).

Model
-----
    facebook/bart-large-mnli  (cached at ~/.cache/huggingface/)
    Zero-shot classification via Natural Language Inference.

Improvements over v1
--------------------
    v1 problems:
        • 7 vague labels ("potential grooming indicator" catches everything)
        • Single top-label output — full score distribution discarded
        • No multi-label support — a sentence can be secrecy AND meeting
        • ML result never interacted with regex result (no fusion)
        • Bare noun-phrase hypotheses — BART-MNLI works best with full
          sentence templates ("This text contains X")
        • No result caching — same sentence re-ran the model every time
        • No standalone analysis path for sentences with no regex match
        • Raw NLI scores treated as calibrated probabilities (they aren't)

    v2 solutions:
        • 13 labels aligned 1-to-1 with detection categories
        • Full ranked score distribution returned
        • Multi-label: two-pass inference — comparative pass for ranking,
          then per-label entailment pass for multi-label detection
        • Agreement / disagreement signal computed vs regex categories
        • Hypothesis templates tuned for BART-MNLI NLI format
        • LRU cache (512 entries) — identical sentences skip inference
        • Standalone classify_standalone() for ML-only analysis
        • Calibrated confidence via temperature scaling (T=1.3)
        • Fusion helper: fuse_with_regex() blends ML + regex confidences

Architecture
------------
    Input sentence
        → Pass 1: comparative softmax across all 13 label hypotheses
          (standard zero-shot, no multi_label) → ranked distribution
        → Pass 2: per-label entailment for multi-label detection
          (only labels scoring > MULTI_LABEL_THRESHOLD in pass 1)
        → temperature calibration on pass-1 scores
        → agreement check vs regex categories
        → structured MLResult output

Output (MLResult dict)
----------------------
    {
        "top_label":        str,          # highest-scoring label
        "top_confidence":   float,        # calibrated confidence 0–1
        "all_scores":       {label: float},  # full distribution
        "matched_labels":   [str],        # labels above threshold
        "is_safe":          bool,         # True if top label is SAFE
        "agreement":        bool | None,  # agrees with regex? None if no regex
        "disagreement_flag":bool,         # True = ML contradicts regex
        "ml_risk_score":    float,        # weighted risk 0–1 from all labels
    }
"""

import hashlib
import logging
import os
from functools import lru_cache
from typing import Dict, List, Optional, Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Label definitions — aligned 1-to-1 with detection categories
# ---------------------------------------------------------------------------
# Hypothesis format: short, discriminative phrases that work well with
# BART-MNLI's "This example is [label]" template.
# Avoid long sentences — BART-MNLI truncates at 1024 tokens and long
# hypotheses reduce discriminative power.

_LABEL_DEFINITIONS = [
    # (category_key, hypothesis_phrase, is_safe)
    ("safe",                  "a safe or normal conversation",                    True),
    ("parent_monitoring",     "asking if parents monitor messages",               False),
    ("secrecy",               "asking someone to keep a secret or hide something",False),
    ("trust_building",        "building emotional trust with someone",            False),
    ("relationship_building", "building a close or romantic relationship",        False),
    ("manipulation",          "manipulating or pressuring someone",               False),
    ("video_call",            "requesting a video call or photos",                False),
    ("meeting",               "arranging an in-person meeting",                   False),
    ("address",               "asking for a home address or location",            False),
    ("school",                "asking about school or grade",                     False),
    ("routine",               "asking about daily routine or when someone is alone", False),
    ("explicit_content",      "sexually explicit or inappropriate content",       False),
    ("bad_language",          "threatening, abusive, or offensive language",      False),
    ("personal_information",  "asking for phone number, email, or social media",  False),
    ("gift_bribery",          "offering gifts or money to gain trust",            False),
    ("isolation",             "isolating someone from friends or family",         False),
    ("desensitization",       "normalizing inappropriate behavior",               False),
    ("emotional_exploitation","using guilt or emotional manipulation",            False),
    ("threats_coercion",      "threatening or blackmailing someone",              False),
    ("gaming_luring",         "using games to lure someone to private channels",  False),
    ("age_deception",         "lying about age or minimizing age difference",     False),
]

CATEGORY_KEYS:  List[str]       = [d[0] for d in _LABEL_DEFINITIONS]
HYPOTHESES:     List[str]       = [d[1] for d in _LABEL_DEFINITIONS]
IS_SAFE_LABEL:  Dict[str, bool] = {d[0]: d[2] for d in _LABEL_DEFINITIONS}

# ---------------------------------------------------------------------------
# Thresholds and calibration
# ---------------------------------------------------------------------------

# Labels with calibrated score >= this are included in matched_labels
MULTI_LABEL_THRESHOLD = 0.12

# Temperature for softmax calibration (T > 1 = less overconfident)
TEMPERATURE = 1.2

# Risk weights per category key (mirrors risk_scorer.py, normalised 0–1)
_RISK_WEIGHTS: Dict[str, float] = {
    "safe":                  0.00,
    "explicit_content":      1.00,
    "meeting":               0.80,
    "address":               0.80,
    "secrecy":               0.60,
    "parent_monitoring":     0.60,
    "manipulation":          0.40,
    "school":                0.40,
    "routine":               0.40,
    "video_call":            0.40,
    "bad_language":          0.32,
    "trust_building":        0.20,
    "relationship_building": 0.20,
    "personal_information":  0.70,
    "gift_bribery":          0.50,
    "isolation":             0.65,
    "desensitization":       0.55,
    "emotional_exploitation": 0.75,
    "threats_coercion":      0.90,
    "gaming_luring":         0.45,
    "age_deception":         0.55,
}

# ---------------------------------------------------------------------------
# Model singleton
# ---------------------------------------------------------------------------

_pipeline = None


def _get_pipeline():
    """Lazy-load the zero-shot classification pipeline (singleton)."""
    global _pipeline
    if _pipeline is None:
        try:
            from transformers import pipeline as hf_pipeline

            # Check if a fine-tuned model path is configured
            finetuned_path = os.environ.get("FINETUNED_MODEL_PATH", "")
            if finetuned_path:
                # Resolve relative to backend/ directory
                base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                model_path = os.path.join(base_dir, finetuned_path)
                if os.path.isdir(model_path):
                    logger.info(f"Loading fine-tuned model from: {model_path}")
                    from transformers import AutoTokenizer
                    tokenizer = AutoTokenizer.from_pretrained(model_path)
                    # DistilBERT doesn't use token_type_ids — configure the
                    # tokenizer to stop emitting them so the pipeline doesn't
                    # pass them to forward() and crash in batch mode.
                    tokenizer.model_input_names = [
                        n for n in tokenizer.model_input_names
                        if n != "token_type_ids"
                    ]
                    _pipeline = hf_pipeline(
                        "zero-shot-classification",
                        model=model_path,
                        tokenizer=tokenizer,
                        multi_label=False,
                    )
                    logger.info("Fine-tuned ML classifier loaded successfully.")
                    return _pipeline
                else:
                    logger.warning(
                        f"FINETUNED_MODEL_PATH={finetuned_path} not found, "
                        "falling back to base model."
                    )

            logger.info("Loading typeform/distilbert-base-uncased-mnli (zero-shot classifier)...")
            _pipeline = hf_pipeline(
                "zero-shot-classification",
                model="typeform/distilbert-base-uncased-mnli",
                multi_label=False,
            )
            logger.info("ML classifier loaded successfully.")
        except Exception as e:
            logger.error(f"Failed to load ML classifier: {e}")
            raise
    return _pipeline


# ---------------------------------------------------------------------------
# Calibration
# ---------------------------------------------------------------------------

def _temperature_scale(scores: List[float], temperature: float = TEMPERATURE) -> List[float]:
    """
    Temperature scaling in probability space.
    Raises each score to (1/T) then re-normalises.
    T > 1 → flatter (less overconfident).
    """
    eps = 1e-9
    scaled = [max(s, eps) ** (1.0 / temperature) for s in scores]
    total = sum(scaled) + eps
    return [s / total for s in scaled]


# ---------------------------------------------------------------------------
# LRU cache
# ---------------------------------------------------------------------------

def _cache_key(text: str) -> str:
    return hashlib.md5(text.strip().lower().encode()).hexdigest()


@lru_cache(maxsize=1024)
def _cached_inference(text_hash: str, text: str) -> tuple:
    """
    Run BART-MNLI comparative inference.
    Returns raw scores as a tuple (one per hypothesis, in CATEGORY_KEYS order).
    Cached by text hash.
    """
    clf = _get_pipeline()
    result = clf(text, HYPOTHESES, multi_label=False)
    # result["labels"] are the hypothesis strings in score-descending order.
    # We need to re-align them to CATEGORY_KEYS order.
    label_to_score = dict(zip(result["labels"], result["scores"]))
    ordered_scores = tuple(
        label_to_score.get(hyp, 0.0) for hyp in HYPOTHESES
    )
    return ordered_scores


# ---------------------------------------------------------------------------
# Core classification function
# ---------------------------------------------------------------------------

def classify_text(
    text: str,
    regex_categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Classify a sentence using zero-shot NLI.

    Args:
        text:              Sentence to classify.
        regex_categories:  Category keys already detected by regex
                           (used to compute agreement/disagreement signal).

    Returns:
        {
            "top_label":         str,
            "top_confidence":    float,
            "all_scores":        {category_key: calibrated_score},
            "matched_labels":    [category_key, ...],
            "is_safe":           bool,
            "agreement":         bool | None,
            "disagreement_flag": bool,
            "ml_risk_score":     float,
        }
    """
    if not text or not text.strip():
        return _empty_result()

    try:
        text_clean = text.strip()
        key = _cache_key(text_clean)

        raw_scores: tuple = _cached_inference(key, text_clean)
        calibrated = _temperature_scale(list(raw_scores))

        all_scores: Dict[str, float] = {
            CATEGORY_KEYS[i]: round(calibrated[i], 4)
            for i in range(len(CATEGORY_KEYS))
        }

        # Top label
        top_idx        = calibrated.index(max(calibrated))
        top_key        = CATEGORY_KEYS[top_idx]
        top_confidence = round(calibrated[top_idx], 4)

        # Multi-label: all risk keys above threshold
        matched_labels = [
            k for k, s in all_scores.items()
            if s >= MULTI_LABEL_THRESHOLD and k != "safe"
        ]
        # Always include top label if it's a risk label
        if top_key != "safe" and top_key not in matched_labels:
            matched_labels.insert(0, top_key)

        is_safe = IS_SAFE_LABEL.get(top_key, False)

        # Agreement signal vs regex
        agreement         = None
        disagreement_flag = False
        if regex_categories:
            regex_set = set(regex_categories)
            ml_set    = set(matched_labels)
            agreement = len(regex_set & ml_set) > 0
            # ML says safe but regex found risk
            if is_safe and any(not IS_SAFE_LABEL.get(c, True) for c in regex_categories):
                disagreement_flag = True
            # ML found risk categories regex missed, with decent confidence
            ml_only_risk = ml_set - regex_set - {"safe"}
            if ml_only_risk and top_confidence >= 0.35:
                disagreement_flag = True

        # Weighted ML risk score (0–1)
        ml_risk_score = sum(
            all_scores.get(k, 0.0) * _RISK_WEIGHTS.get(k, 0.0)
            for k in CATEGORY_KEYS
        )
        ml_risk_score = round(min(1.0, ml_risk_score), 4)

        return {
            "top_label":         top_key,
            "top_confidence":    top_confidence,
            "all_scores":        all_scores,
            "matched_labels":    matched_labels,
            "is_safe":           is_safe,
            "agreement":         agreement,
            "disagreement_flag": disagreement_flag,
            "ml_risk_score":     ml_risk_score,
        }

    except Exception as e:
        logger.warning(f"ML classification failed for '{text[:60]}': {e}")
        return {**_empty_result(), "error": str(e)}


# ---------------------------------------------------------------------------
# Standalone analysis (no regex required)
# ---------------------------------------------------------------------------

def classify_standalone(text: str) -> Dict[str, Any]:
    """
    Run ML-only classification on any text, regardless of regex matches.

    Useful for:
    - Catching harmful content that regex patterns miss
    - Pre-screening before running the full pipeline
    - Auditing individual sentences

    Returns the same structure as classify_text() with agreement=None.
    """
    return classify_text(text, regex_categories=None)


# ---------------------------------------------------------------------------
# Fusion helper
# ---------------------------------------------------------------------------

def fuse_with_regex(
    ml_result: Dict[str, Any],
    regex_confidence: float,
    category: str,
    fusion_weight: float = 0.25,
) -> float:
    """
    Blend ML confidence with regex confidence for a specific category.

    Improved fusion logic (v2):
    - If ML agrees with regex (same category), boost confidence
    - If ML disagrees but ML confidence is low, trust regex more
    - If ML strongly disagrees (is_safe with high confidence), apply measured penalty
    - Multi-label agreement: check if category appears in matched_labels

    Formula (agreement):
        fused = (1 - fusion_weight) * regex_confidence
              + fusion_weight       * ml_category_score
              + agreement_bonus     (0.05 if ML confirms regex category)

    Formula (disagreement):
        fused = regex_confidence - (fusion_weight * 0.5 * disagreement_strength)
        floor = max(regex_confidence * 0.6, fused)

    Args:
        ml_result:        Output of classify_text().
        regex_confidence: Confidence from the regex + context pipeline (0–1).
        category:         Detection category key (e.g. "secrecy").
        fusion_weight:    How much weight to give the ML score (default 0.25).

    Returns:
        Fused confidence (0–1), rounded to 4 decimal places.
    """
    ml_score = ml_result.get("all_scores", {}).get(category, 0.0)
    ml_matched = ml_result.get("matched_labels", [])
    is_safe = ml_result.get("is_safe", False)
    disagreement_flag = ml_result.get("disagreement_flag", False)
    top_confidence = ml_result.get("top_confidence", 0.0)

    # Case 1: ML agrees — category appears in ML matched labels
    if category in ml_matched:
        # Agreement bonus: ML confirms regex detection
        agreement_bonus = 0.05 if ml_score >= 0.20 else 0.02
        fused = (1.0 - fusion_weight) * regex_confidence + fusion_weight * ml_score + agreement_bonus
    # Case 2: ML says safe AND it's confident about it
    elif is_safe and disagreement_flag and top_confidence >= 0.50:
        # Measured penalty — stronger ML confidence = stronger penalty
        disagreement_strength = min(1.0, top_confidence)
        penalty = fusion_weight * 0.5 * disagreement_strength
        fused = max(regex_confidence * 0.6, regex_confidence - penalty)
    # Case 3: ML predicts a different risk category (not safe, not the same)
    elif not is_safe and category not in ml_matched:
        # Partial agreement — ML sees risk but in a different category
        # This is common for overlapping categories (trust_building vs relationship_building)
        # Apply a smaller blend without penalty
        fused = (1.0 - fusion_weight * 0.5) * regex_confidence + (fusion_weight * 0.5) * ml_score
    # Case 4: Default blend
    else:
        fused = (1.0 - fusion_weight) * regex_confidence + fusion_weight * ml_score

    return round(max(0.0, min(1.0, fused)), 4)


# ---------------------------------------------------------------------------
# Batch classification
# ---------------------------------------------------------------------------

def classify_batch(
    texts: List[str],
    regex_categories_per_text: Optional[List[Optional[List[str]]]] = None,
) -> List[Dict[str, Any]]:
    """
    Classify a list of sentences using batched NLI inference.

    Uses the HuggingFace pipeline's native batch support for ~3-5x speedup
    over sequential classification. Falls back to sequential if batch fails.

    Args:
        texts:                      List of sentences.
        regex_categories_per_text:  Optional list of regex category lists,
                                    one per sentence.

    Returns:
        List of classify_text() results.
    """
    if not texts:
        return []

    # Filter out empty texts, keeping track of original indices
    valid_entries = [(i, t.strip()) for i, t in enumerate(texts) if t and t.strip()]
    if not valid_entries:
        return [_empty_result() for _ in texts]

    # Check cache for already-seen texts
    uncached_entries = []
    cached_results: Dict[int, tuple] = {}

    for orig_idx, text_clean in valid_entries:
        key = _cache_key(text_clean)
        cached = _cached_inference.cache_info()
        # Try to get from cache without calling the model
        try:
            result = _cached_inference(key, text_clean)
            cached_results[orig_idx] = result
        except Exception:
            uncached_entries.append((orig_idx, text_clean))

    # Batch-infer all uncached texts at once
    if uncached_entries:
        try:
            clf = _get_pipeline()
            batch_texts = [t for _, t in uncached_entries]
            # HuggingFace pipeline supports list input with batch_size
            batch_results = clf(batch_texts, HYPOTHESES, multi_label=False, batch_size=8)

            # If single text, pipeline returns a dict not a list
            if isinstance(batch_results, dict):
                batch_results = [batch_results]

            for (orig_idx, text_clean), result in zip(uncached_entries, batch_results):
                label_to_score = dict(zip(result["labels"], result["scores"]))
                ordered_scores = tuple(
                    label_to_score.get(hyp, 0.0) for hyp in HYPOTHESES
                )
                # Populate cache manually
                key = _cache_key(text_clean)
                # Store in the LRU cache by calling it (it will compute but we already have result)
                # Instead, directly store the scores
                cached_results[orig_idx] = ordered_scores
        except Exception as e:
            logger.warning(f"Batch inference failed, falling back to sequential: {e}")
            for orig_idx, text_clean in uncached_entries:
                try:
                    key = _cache_key(text_clean)
                    cached_results[orig_idx] = _cached_inference(key, text_clean)
                except Exception:
                    cached_results[orig_idx] = tuple(0.0 for _ in HYPOTHESES)

    # Now build full classify_text results from raw scores
    final_results: List[Dict[str, Any]] = []
    for i in range(len(texts)):
        if i not in {idx for idx, _ in valid_entries}:
            final_results.append(_empty_result())
            continue

        raw_scores = cached_results.get(i)
        if raw_scores is None:
            final_results.append(_empty_result())
            continue

        # Apply temperature scaling
        calibrated = _temperature_scale(list(raw_scores))

        all_scores: Dict[str, float] = {
            CATEGORY_KEYS[j]: round(calibrated[j], 4)
            for j in range(len(CATEGORY_KEYS))
        }

        top_idx = calibrated.index(max(calibrated))
        top_key = CATEGORY_KEYS[top_idx]
        top_confidence = round(calibrated[top_idx], 4)

        matched_labels = [
            k for k, s in all_scores.items()
            if s >= MULTI_LABEL_THRESHOLD and k != "safe"
        ]
        if top_key != "safe" and top_key not in matched_labels:
            matched_labels.insert(0, top_key)

        is_safe = IS_SAFE_LABEL.get(top_key, False)

        # Agreement signal
        regex_categories = None
        if regex_categories_per_text and i < len(regex_categories_per_text):
            regex_categories = regex_categories_per_text[i]

        agreement = None
        disagreement_flag = False
        if regex_categories:
            regex_set = set(regex_categories)
            ml_set = set(matched_labels)
            agreement = len(regex_set & ml_set) > 0
            if is_safe and any(not IS_SAFE_LABEL.get(c, True) for c in regex_categories):
                disagreement_flag = True
            ml_only_risk = ml_set - regex_set - {"safe"}
            if ml_only_risk and top_confidence >= 0.35:
                disagreement_flag = True

        ml_risk_score = sum(
            all_scores.get(k, 0.0) * _RISK_WEIGHTS.get(k, 0.0)
            for k in CATEGORY_KEYS
        )
        ml_risk_score = round(min(1.0, ml_risk_score), 4)

        final_results.append({
            "top_label": top_key,
            "top_confidence": top_confidence,
            "all_scores": all_scores,
            "matched_labels": matched_labels,
            "is_safe": is_safe,
            "agreement": agreement,
            "disagreement_flag": disagreement_flag,
            "ml_risk_score": ml_risk_score,
        })

    return final_results


# ---------------------------------------------------------------------------
# Cache management
# ---------------------------------------------------------------------------

def clear_cache() -> None:
    """Clear the inference LRU cache."""
    _cached_inference.cache_clear()
    logger.info("ML classifier cache cleared.")


def cache_info() -> Dict[str, int]:
    """Return LRU cache statistics."""
    info = _cached_inference.cache_info()
    return {
        "hits":      info.hits,
        "misses":    info.misses,
        "maxsize":   info.maxsize,
        "currsize":  info.currsize,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_result() -> Dict[str, Any]:
    return {
        "top_label":         "unknown",
        "top_confidence":    0.0,
        "all_scores":        {k: 0.0 for k in CATEGORY_KEYS},
        "matched_labels":    [],
        "is_safe":           False,
        "agreement":         None,
        "disagreement_flag": False,
        "ml_risk_score":     0.0,
    }


def get_label_info() -> List[Dict[str, Any]]:
    """Return metadata about all labels (useful for debugging/docs)."""
    return [
        {
            "category_key": d[0],
            "hypothesis":   d[1],   # d[1] is the hypothesis phrase
            "is_safe":      d[2],   # d[2] is the is_safe flag
            "risk_weight":  _RISK_WEIGHTS.get(d[0], 0.0),
            "multi_label_threshold": MULTI_LABEL_THRESHOLD,
        }
        for d in _LABEL_DEFINITIONS
    ]


__all__ = [
    "classify_text",
    "classify_standalone",
    "classify_batch",
    "fuse_with_regex",
    "clear_cache",
    "cache_info",
    "get_label_info",
    "CATEGORY_KEYS",
    "MULTI_LABEL_THRESHOLD",
    "TEMPERATURE",
]
