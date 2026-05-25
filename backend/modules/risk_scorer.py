"""
Weighted Risk Scoring Engine — Context-Based (v2).

ARCHITECTURE CHANGE:
    No role-based adjustments were present in the original risk scorer.
    This version is updated to:
        1. Surface context_type in breakdown output.
        2. Accept the new "context_type" field emitted by GroomingDetector v2.
        3. Preserve all existing scoring logic (weights, DR, thresholds).

Risk Score Formula
------------------
    effective_score = weight × confidence          (1st occurrence)
    effective_score = weight × confidence × DR     (repeated occurrences)
    total_score     = Σ effective_scores, capped at 0–100

Diminishing Returns (DR) — same-category repeated occurrences only
-------------------------------------------------------------------
    1st occurrence : 1.000  (full weight — no penalty for unique categories)
    2nd occurrence : 0.500
    3rd occurrence : 0.250
    4th occurrence : 0.125
    5th+           : continues halving

Category Weights
----------------
    meeting               = 20
    address               = 20
    secrecy               = 15
    parent_monitoring     = 15
    school                = 10
    routine               = 10
    video_call            = 10
    manipulation          = 10
    trust_building        =  5
    relationship_building =  5
    (total = 120; scores are normalised to 0–100 via cap)

Risk Levels
-----------
    Safe     :  0–20
    Low      : 21–40
    Moderate : 41–60
    High     : 61–80
    Critical : 81–100
"""

from typing import List, Dict, Any, Optional
from collections import defaultdict


class WeightedRiskScorer:
    """
    Calculate weighted risk scores from grooming detection findings.

    Accepts findings in three formats:
        1. Single-category  : {"category": "meeting",  "confidence": 0.85}
        2. Multi-category   : {"categories": ["meeting","address"],
                               "max_confidence": 1.0,
                               "category_details": [{"category":"meeting","confidence":1.0}, ...]}
        3. Legacy list-1    : {"categories": ["secrecy"], "confidence": 0.9}
    """

    CATEGORY_WEIGHTS: Dict[str, int] = {
        "meeting":               20,
        "address":               20,
        "secrecy":               15,
        "parent_monitoring":     15,
        "school":                10,
        "routine":               10,
        "video_call":            10,
        "manipulation":          10,
        "trust_building":         5,
        "relationship_building":  5,
        "explicit_content":      25,   # highest weight — direct harm signal
        "bad_language":           8,
        "personal_information":  18,   # high-risk — PII disclosure/solicitation
        "gift_bribery":          12,   # bribery/grooming incentive
        "isolation":             16,   # isolating child from support network
        "desensitization":       14,   # normalising inappropriate behaviour
        "emotional_exploitation": 18,  # guilt/self-harm threats
        "threats_coercion":      22,   # blackmail/explicit threats
        "gaming_luring":         10,   # platform-based luring
        "age_deception":         14,   # misrepresenting age
    }

    RISK_LEVELS: Dict[str, tuple] = {
        "Safe":     (0,  20),
        "Low":      (21, 40),
        "Moderate": (41, 60),
        "High":     (61, 80),
        "Critical": (81, 100),
    }

    _DR_FACTORS = [1.0, 0.5, 0.25, 0.125, 0.0625]

    def __init__(
        self,
        custom_weights: Optional[Dict[str, float]] = None,
        enable_diminishing_returns: bool = True,
    ):
        self.weights: Dict[str, float] = {k: float(v) for k, v in self.CATEGORY_WEIGHTS.items()}
        if custom_weights:
            self.weights.update({k: float(v) for k, v in custom_weights.items()})
        self.enable_diminishing_returns = enable_diminishing_returns

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def calculate_score(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate risk score from a list of findings.

        Returns:
            {
                "score":           float  0–100,
                "level":           str,
                "breakdown":       {category: {..., "context_types": List[str]}},
                "total_findings":  int,
                "category_counts": {category: int},
                "raw_score":       float,
            }
        """
        if not findings:
            return self._empty_result()

        pairs = self._expand_findings(findings)

        # Group by category, preserving insertion order
        category_pairs: Dict[str, List[tuple]] = defaultdict(list)
        for category, confidence, context_type in pairs:
            category_pairs[category].append((confidence, context_type))

        # Sort each category descending by confidence
        for cat in category_pairs:
            category_pairs[cat].sort(key=lambda x: x[0], reverse=True)

        breakdown: Dict[str, Any] = {}
        total_score = 0.0

        for category, conf_ctx_list in category_pairs.items():
            cat_result = self._score_category(category, conf_ctx_list)
            breakdown[category] = cat_result
            total_score += cat_result["total_score"]

        final_score = min(100.0, total_score)

        return {
            "score":           round(final_score, 2),
            "level":           self.classify_risk(final_score),
            "breakdown":       breakdown,
            "total_findings":  len(findings),
            "category_counts": {cat: len(items) for cat, items in category_pairs.items()},
            "raw_score":       round(total_score, 2),
        }

    def calculate_score_with_details(self, findings: List[Dict[str, Any]]) -> Dict[str, Any]:
        """calculate_score + human-readable explanation."""
        result = self.calculate_score(findings)
        result["explanation"] = self._generate_explanation(result)
        return result

    def classify_risk(self, score: float) -> str:
        for level, (lo, hi) in self.RISK_LEVELS.items():
            if lo <= score <= hi:
                return level
        return "Critical" if score > 100 else "Safe"

    def get_category_weight(self, category: str) -> float:
        return self.weights.get(category, 5.0)

    def set_category_weight(self, category: str, weight: float) -> None:
        self.weights[category] = float(weight)

    def get_all_weights(self) -> Dict[str, float]:
        return self.weights.copy()

    def get_risk_level_info(self, level: str) -> Optional[Dict[str, Any]]:
        if level not in self.RISK_LEVELS:
            return None
        lo, hi = self.RISK_LEVELS[level]
        return {"level": level, "min_score": lo, "max_score": hi,
                "description": self._level_description(level)}

    def compare_scores(
        self,
        findings_a: List[Dict[str, Any]],
        findings_b: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        a = self.calculate_score(findings_a)
        b = self.calculate_score(findings_b)
        diff = a["score"] - b["score"]
        return {
            "score_a":           a["score"],
            "level_a":           a["level"],
            "score_b":           b["score"],
            "level_b":           b["level"],
            "difference":        round(diff, 2),
            "percentage_change": round((diff / b["score"] * 100) if b["score"] else 0, 2),
        }

    def simulate_score(
        self,
        category: str,
        confidence: float,
        occurrence_count: int = 1,
    ) -> Dict[str, Any]:
        findings = [
            {"category": category, "confidence": confidence,
             "evidence": f"Simulated {category} #{i + 1}"}
            for i in range(occurrence_count)
        ]
        return self.calculate_score_with_details(findings)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _expand_findings(
        self,
        findings: List[Dict[str, Any]],
    ) -> List[tuple]:
        """
        Flatten every finding into (category, confidence, context_type) tuples.
        context_type is the new field added by GroomingDetector v2.
        """
        pairs: List[tuple] = []

        for finding in findings:
            categories  = finding.get("categories")
            single_cat  = finding.get("category")
            context_type = finding.get("context_type", "NEUTRAL")

            if categories and isinstance(categories, list):
                cat_list = [c for c in categories if c]
            elif single_cat:
                cat_list = [single_cat]
            else:
                continue

            if len(cat_list) == 1:
                conf = self._resolve_confidence(finding, cat_list[0])
                pairs.append((cat_list[0], conf, context_type))
            else:
                details_map: Dict[str, float] = {}
                for detail in finding.get("category_details", []):
                    dc, dc_conf = detail.get("category"), detail.get("confidence")
                    if dc and dc_conf is not None:
                        details_map[dc] = float(dc_conf)

                fallback = (
                    finding.get("max_confidence")
                    or finding.get("confidence")
                    or finding.get("avg_confidence")
                    or 0.5
                )
                for cat in cat_list:
                    conf = details_map.get(cat, fallback)
                    pairs.append((cat, float(conf), context_type))

        return pairs

    @staticmethod
    def _resolve_confidence(finding: Dict[str, Any], _category: str) -> float:
        for key in ("confidence", "max_confidence", "avg_confidence"):
            val = finding.get(key)
            if val is not None:
                return float(val)
        return 0.5

    def _score_category(
        self,
        category: str,
        conf_ctx_list: List[tuple],
    ) -> Dict[str, Any]:
        """Score a single category given its sorted (desc) (confidence, context_type) list."""
        weight = self.weights.get(category, 5.0)
        occurrences = []
        total = 0.0
        context_types_seen = []

        for i, (conf, ctx_type) in enumerate(conf_ctx_list):
            if self.enable_diminishing_returns and i > 0:
                if i < len(self._DR_FACTORS):
                    dr = self._DR_FACTORS[i]
                else:
                    dr = self._DR_FACTORS[-1] / (2 ** (i - len(self._DR_FACTORS) + 1))
            else:
                dr = 1.0

            effective = weight * conf * dr
            total += effective

            if ctx_type and ctx_type not in context_types_seen:
                context_types_seen.append(ctx_type)

            occurrences.append({
                "occurrence":         i + 1,
                "confidence":         round(conf, 4),
                "context_type":       ctx_type,
                "diminishing_factor": round(dr, 4),
                "effective_score":    round(effective, 4),
            })

        return {
            "category":        category,
            "weight":          weight,
            "occurrence_count": len(conf_ctx_list),
            "total_score":     round(total, 4),
            "context_types":   context_types_seen,   # ← NEW: surfaces context types
            "occurrences":     occurrences,
        }

    def _generate_explanation(self, result: Dict[str, Any]) -> str:
        lines = [
            f"Risk Score : {result['score']}/100",
            f"Risk Level : {result['level']}",
            f"Findings   : {result['total_findings']}",
            "",
            "Category Breakdown:",
        ]
        sorted_cats = sorted(
            result["breakdown"].items(),
            key=lambda x: x[1]["total_score"],
            reverse=True,
        )
        for cat, details in sorted_cats:
            label = cat.replace("_", " ").title()
            n     = details["occurrence_count"]
            ctxs  = ", ".join(details.get("context_types", []))
            lines.append(
                f"  • {label}: {details['total_score']:.2f} pts "
                f"({n} occurrence{'s' if n > 1 else ''}"
                + (f", ctx: {ctxs}" if ctxs else "") + ")"
            )
            if n > 1:
                for occ in details["occurrences"][:3]:
                    lines.append(
                        f"    - #{occ['occurrence']}: {occ['effective_score']:.2f} pts "
                        f"(conf {occ['confidence']:.0%}, DR {occ['diminishing_factor']:.0%}, "
                        f"ctx: {occ.get('context_type','?')})"
                    )
                if n > 3:
                    lines.append(f"    ... and {n - 3} more")
        return "\n".join(lines)

    @staticmethod
    def _level_description(level: str) -> str:
        return {
            "Safe":     "No significant grooming indicators detected.",
            "Low":      "Minor concerns detected. May warrant monitoring.",
            "Moderate": "Multiple grooming indicators present. Increased monitoring recommended.",
            "High":     "Significant grooming patterns detected. Immediate review recommended.",
            "Critical": "Severe grooming behaviour detected. Urgent intervention required.",
        }.get(level, "Unknown risk level.")

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "score":           0.0,
            "level":           "Safe",
            "breakdown":       {},
            "total_findings":  0,
            "category_counts": {},
            "raw_score":       0.0,
        }


# ---------------------------------------------------------------------------
# Convenience functions
# ---------------------------------------------------------------------------

def calculate_risk_score(findings: List[Dict[str, Any]]) -> Dict[str, Any]:
    return WeightedRiskScorer().calculate_score(findings)


def classify_risk_level(score: float) -> str:
    return WeightedRiskScorer().classify_risk(score)


def get_risk_explanation(findings: List[Dict[str, Any]]) -> str:
    return WeightedRiskScorer().calculate_score_with_details(findings)["explanation"]


__all__ = [
    "WeightedRiskScorer",
    "calculate_risk_score",
    "classify_risk_level",
    "get_risk_explanation",
]
