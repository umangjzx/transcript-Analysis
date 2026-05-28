"""
Context Analyzer — Context-Based Risk Analysis (v2).

ARCHITECTURE CHANGE:
    Previous version used role-based safe context (teacher, parent, principal, etc.)
    to suppress risk signals. This was incorrect for general audio analysis.

    This version classifies WHAT is being said into semantic ContextTypes and
    applies confidence multipliers based on those types — no speaker identity
    is ever used to adjust risk.

ContextType Enum
----------------
    ADMINISTRATIVE        — event logistics, forms, schedules  → confidence -0.20
    INFORMATION_GATHERING — collecting personal details        → confidence +0.15
    TRUST_BUILDING        — "I care about you", "trust me"     → confidence +0.20
    RELATIONSHIP_BUILDING — "special connection", "best friends"→ confidence +0.15
    MANIPULATION          — "they won't understand"            → confidence +0.30
    SECRECY               — "don't tell anyone", "our secret"  → confidence +0.40
    ESCALATION            — private call, move platform        → confidence +0.35
    MEETING               — meet up, in person, hang out       → confidence +0.35
    PERSONAL_INFORMATION  — address, phone, email, route       → confidence +0.30
    VIDEO_CALL            — video chat, facetime, camera       → confidence +0.25
    NEUTRAL               — no strong signal                   → confidence  0.00

LOCAL CONTEXT ONLY:
    Analysis is strictly local to the current sentence ± its immediate
    neighbours. No transcript-wide state is propagated.
"""

import re
from enum import Enum
from typing import Dict, List, Optional, Tuple, Any


# ---------------------------------------------------------------------------
# ContextType Enum
# ---------------------------------------------------------------------------

class ContextType(str, Enum):
    """Semantic context types derived from conversation content."""
    ADMINISTRATIVE        = "ADMINISTRATIVE"
    INFORMATION_GATHERING = "INFORMATION_GATHERING"
    TRUST_BUILDING        = "TRUST_BUILDING"
    RELATIONSHIP_BUILDING = "RELATIONSHIP_BUILDING"
    MANIPULATION          = "MANIPULATION"
    SECRECY               = "SECRECY"
    ESCALATION            = "ESCALATION"
    MEETING               = "MEETING"
    PERSONAL_INFORMATION  = "PERSONAL_INFORMATION"
    VIDEO_CALL            = "VIDEO_CALL"
    EXPLICIT_CONTENT      = "EXPLICIT_CONTENT"
    BAD_LANGUAGE          = "BAD_LANGUAGE"
    NEUTRAL               = "NEUTRAL"


# ---------------------------------------------------------------------------
# Context multipliers — applied to confidence score
# Positive = raises confidence (more suspicious)
# Negative = lowers confidence (less suspicious)
# ---------------------------------------------------------------------------

CONTEXT_MULTIPLIERS: Dict[ContextType, float] = {
    ContextType.ADMINISTRATIVE:        -0.20,   # Reduced from -0.40 to prevent over-suppression
    ContextType.INFORMATION_GATHERING: +0.15,
    ContextType.TRUST_BUILDING:        +0.20,
    ContextType.RELATIONSHIP_BUILDING: +0.15,
    ContextType.MANIPULATION:          +0.30,
    ContextType.SECRECY:               +0.40,
    ContextType.ESCALATION:            +0.35,
    ContextType.MEETING:               +0.35,
    ContextType.PERSONAL_INFORMATION:  +0.30,
    ContextType.VIDEO_CALL:            +0.25,
    ContextType.EXPLICIT_CONTENT:      +0.50,   # maximum boost — direct harm
    ContextType.BAD_LANGUAGE:          +0.20,
    ContextType.NEUTRAL:               +0.00,
}


# ---------------------------------------------------------------------------
# Pattern definitions per ContextType
# Each entry is a list of raw regex strings (compiled once at class init).
# ---------------------------------------------------------------------------

_CONTEXT_PATTERNS: Dict[ContextType, List[str]] = {

    # ------------------------------------------------------------------
    # ADMINISTRATIVE — event logistics, forms, schedules, registrations
    # Presence of these phrases means information collection is benign.
    # ------------------------------------------------------------------
    ContextType.ADMINISTRATIVE: [
        r'\b(?:science\s+exhibition|science\s+fair|project\s+exhibition)\b',
        r'\b(?:permission\s+form|consent\s+form|registration\s+form|sign[-\s]up\s+form)\b',
        r'\b(?:event\s+registration|conference\s+registration|event\s+sign[-\s]up)\b',
        r'\b(?:conference\s+schedule|event\s+schedule|class\s+timetable|timetable)\b',
        r'\b(?:office\s+timings?|office\s+hours?|opening\s+hours?|closing\s+time)\b',
        r'\b(?:attendance\s+register|attendance\s+sheet|roll\s+call)\b',
        r'\b(?:meeting\s+agenda|agenda\s+for|agenda\s+items?)\b',
        r'\b(?:sports\s+practice|training\s+schedule|practice\s+session)\b',
        r'\b(?:school\s+event|office\s+event|community\s+event|annual\s+day|sports\s+day)\b',
        r'\b(?:field\s+trip|educational\s+trip|school\s+trip|excursion)\b',
        r'\b(?:what\s+time\s+does\s+(?:the\s+)?(?:event|session|class|meeting|practice)\s+(?:finish|end|start|begin))\b',
        r'\b(?:when\s+does\s+(?:the\s+)?(?:event|session|class|meeting|practice)\s+(?:finish|end|start|begin))\b',
        r'\b(?:assembly|morning\s+assembly|school\s+assembly|town\s+hall)\b',
        r'\b(?:workshop|seminar|webinar|orientation|induction)\b',
        r'\b(?:deadline|submission\s+date|due\s+date|cutoff\s+date)\b',
        r'\b(?:invoice|receipt|billing|payment\s+confirmation|order\s+confirmation)\b',
    ],

    # ------------------------------------------------------------------
    # INFORMATION_GATHERING — collecting personal details about someone
    # ------------------------------------------------------------------
    ContextType.INFORMATION_GATHERING: [
        r'\bwhat\s+school\b',
        r'\bwhich\s+school\b',
        r'\bwhat\s+grade\b',
        r'\bwhich\s+grade\b',
        r'\bwhat\s+class\b',
        r'\bwhich\s+class\b',
        r'\bwhat\s+route\b',
        r'\bwhich\s+route\b',
        r'\bwhat\s+time\s+do\s+you\s+(?:leave|get\s+home|arrive|finish)\b',
        r'\bwhere\s+do\s+you\s+(?:live|stay|go\s+to\s+school)\b',
        r'\bwhich\s+(?:neighborhood|neighbourhood|area|district|part\s+of\s+town)\b',
        r'\bwhat\s+(?:area|neighborhood|neighbourhood)\s+(?:are\s+you|do\s+you)\b',
        r'\bhow\s+old\s+are\s+you\b',
        r'\bwhat\'?s\s+your\s+(?:age|dob|date\s+of\s+birth|birthday)\b',
        r'\bdo\s+you\s+(?:live\s+alone|stay\s+alone|go\s+home\s+alone)\b',
        r'\bwho\s+(?:else\s+)?(?:lives|stays)\s+(?:with\s+you|at\s+your\s+place)\b',
    ],

    # ------------------------------------------------------------------
    # TRUST_BUILDING — establishing emotional trust
    # ------------------------------------------------------------------
    ContextType.TRUST_BUILDING: [
        r'\bI\s+care\s+about\s+you\b',
        r'\byou\s+can\s+(?:always\s+)?trust\s+me\b',
        r'\bI\'?m\s+(?:very\s+)?trustworthy\b',
        r'\bI\'?m\s+here\s+for\s+you\b',
        r'\byou\s+can\s+always\s+talk\s+to\s+me\b',
        r'\bI\s+understand\s+you\b',
        r'\bI\s+(?:really\s+)?understand\s+(?:you|what\s+you\'?re\s+going\s+through)\b',
        r'\bI\'?m\s+(?:someone|a\s+person)\s+you\s+can\s+trust\b',
        r'\byou\s+can\s+(?:tell|share)\s+(?:me\s+)?anything\b',
        r'\bI\'?ll\s+never\s+(?:judge|hurt|betray)\s+you\b',
        r'\bI\s+would\s+never\s+(?:lie|deceive|trick)\s+(?:to\s+)?you\b',
        r'\btrust\s+me\b',
        r'\bbelieve\s+me\b',
        r'\bhave\s+faith\s+in\s+me\b',
    ],

    # ------------------------------------------------------------------
    # RELATIONSHIP_BUILDING — deepening personal relationship
    # ------------------------------------------------------------------
    ContextType.RELATIONSHIP_BUILDING: [
        r'\bgood\s+friends?\b',
        r'\bspecial\s+(?:connection|bond|relationship|friendship)\b',
        r'\bclose\s+friendship\b',
        r'\bour\s+friendship\s+is\s+(?:special|different|unique)\b',
        r'\bbest\s+friends?\b',
        r'\bwe\s+have\s+a\s+(?:special|unique|strong)\s+(?:connection|bond)\b',
        r'\byou\'?re\s+(?:so\s+)?(?:special|unique|different)\s+to\s+me\b',
        r'\byou\s+mean\s+(?:so\s+much|everything)\s+to\s+me\b',
        r'\bI\s+feel\s+(?:so\s+)?close\s+to\s+you\b',
        r'\bwe\'?re\s+(?:meant\s+to\s+be|perfect\s+together)\b',
        r'\bI\s+(?:really\s+)?(?:like|love|adore)\s+(?:you|talking\s+to\s+you)\b',
        r'\byou\'?re\s+(?:not\s+like|different\s+from)\s+(?:other|most)\s+people\b',
    ],

    # ------------------------------------------------------------------
    # MANIPULATION — undermining trust in others, coercion
    # ------------------------------------------------------------------
    ContextType.MANIPULATION: [
        r'\b(?:your\s+)?parents?\s+(?:might|will|would)\s+misunderstand\b',
        r'\bthey\s+(?:won\'?t|wouldn\'?t|don\'?t)\s+understand\b',
        r'\bthey\'?ll\s+overreact\b',
        r'\b(?:your\s+)?parents?\s+(?:will|would|might)\s+(?:overreact|freak\s+out|be\s+mad)\b',
        r'\bonly\s+I\s+(?:understand|get|know)\s+you\b',
        r'\bI\'?m\s+the\s+only\s+one\s+who\s+(?:understands?|gets?|cares?)\b',
        r'\bnobody\s+(?:else\s+)?(?:understands?|gets?)\s+you\b',
        r'\bprove\s+(?:you\s+)?(?:love|trust|care)\b',
        r'\bif\s+you\s+(?:really\s+)?(?:loved?|cared?|trusted?)\s+me\b',
        r'\byou\s+(?:owe|promised)\s+me\b',
        r'\beveryone\s+(?:does?|is\s+doing)\s+(?:this|it)\b',
        r'\bI\s+thought\s+you\s+were\s+(?:mature|different|special)\b',
    ],

    # ------------------------------------------------------------------
    # SECRECY — demands to hide, delete, or not disclose
    # ------------------------------------------------------------------
    ContextType.SECRECY: [
        r'\bdon\'?t\s+tell\s+anyone\b',
        r'\bkeep\s+this\s+between\s+us\b',
        r'\bnobody\s+(?:else\s+)?needs?\s+to\s+know\b',
        r'\bour\s+(?:little\s+)?secret\b',
        r'\bsecret\s+chat\b',
        r'\bprivate\s+conversation\b',
        r'\bdelete\s+(?:these?\s+)?messages?\b',
        r'\bclear\s+(?:the\s+)?(?:history|chat|conversation)\b',
        r'\bdon\'?t\s+let\s+(?:anyone|them|your\s+parents?)\s+(?:know|find\s+out|see)\b',
        r'\bjust\s+between\s+(?:us|you\s+and\s+me)\b',
        r'\bkeep\s+(?:it|this|that)\s+(?:secret|private|quiet|to\s+yourself)\b',
        r'\bnever\s+tell\s+(?:anyone|anybody)\b',
        r'\bno\s+one\s+(?:else\s+)?needs?\s+to\s+know\b',
        r'\bdon\'?t\s+(?:say|mention|share)\s+(?:this|it|anything)\s+(?:to|with)\s+(?:anyone|anybody|them)\b',
    ],

    # ------------------------------------------------------------------
    # ESCALATION — moving to private channel, isolating communication
    # ------------------------------------------------------------------
    ContextType.ESCALATION: [
        r'\bprivate\s+video\s+(?:call|chat|session)\b',
        r'\bone[\s\-]on[\s\-]one\s+(?:call|chat|video|session|talk)\b',
        r'\bprivate\s+(?:call|chat|conversation|talk)\b',
        r'\bcall\s+(?:you\s+)?privately\b',
        r'\b(?:talk|chat|speak)\s+(?:to\s+you\s+)?privately\b',
        r'\bmove\s+to\s+(?:another|a\s+different)\s+(?:platform|app|chat|channel)\b',
        r'\bswitch\s+to\s+(?:another|a\s+different)\s+(?:platform|app|chat|channel)\b',
        r'\blet\'?s\s+(?:use|switch\s+to|move\s+to)\s+(?:signal|telegram|whatsapp|discord|snapchat|instagram)\b',
        r'\b(?:just\s+(?:us|you\s+and\s+me)|alone)\s+on\s+(?:a\s+)?(?:call|video|camera)\b',
        r'\bwhen\s+(?:you\'?re|we\'?re)\s+alone\b',
        r'\bwhen\s+(?:your\s+)?(?:parents?|family|roommates?)\s+(?:are\s+)?(?:gone|away|out|asleep|not\s+home)\b',
        r'\bnobody\s+(?:around|there|watching|home)\b',
    ],

    # ------------------------------------------------------------------
    # MEETING — arranging in-person contact
    # ------------------------------------------------------------------
    ContextType.MEETING: [
        r'\bmeet\s+up\b',
        r'\bmeet\s+in\s+person\b',
        r'\bhang\s+out\b',
        r'\bsee\s+each\s+other\b',
        r'\bget\s+together\b',
        r'\bmeet\s+(?:sometime|someday|one\s+day|soon)\b',
        r'\bface\s+to\s+face\b',
        r'\bin\s+person\b',
        r'\birl\b',
        r'\bsneak\s+out\b',
        r'\bcome\s+(?:over|to\s+my\s+place)\b',
        r'\bI\'?ll\s+(?:come|pick\s+you\s+up)\b',
        r'\bpublic\s+place\b',
        r'\bsomewhere\s+(?:public|neutral|safe|nearby)\b',
    ],

    # ------------------------------------------------------------------
    # PERSONAL_INFORMATION — requesting identifying details
    # ------------------------------------------------------------------
    ContextType.PERSONAL_INFORMATION: [
        r'\b(?:your|ur)\s+(?:home\s+)?address\b',
        r'\bhouse\s+number\b',
        r'\bstreet\s+name\b',
        r'\bwhat\s+street\b',
        r'\bphone\s+number\b',
        r'\b(?:your|ur)\s+(?:mobile|cell|phone)\s+(?:number|no\.?)\b',
        r'\bemail\s+address\b',
        r'\b(?:your|ur)\s+(?:personal\s+)?email\b',
        r'\bshare\s+(?:your|ur)\s+(?:location|address|number)\b',
        r'\bsend\s+(?:your|ur)\s+(?:location|address|number)\b',
        r'\bwhere\s+exactly\s+do\s+you\s+live\b',
        r'\bwhich\s+neighbo(?:u)?rhood\b',
        r'\bwhat\s+area\s+(?:do\s+you|are\s+you)\b',
        r'\broute\s+(?:home|to\s+school|you\s+take)\b',
        r'\bhow\s+(?:far|close)\s+(?:do\s+you|are\s+you)\s+(?:live|stay)\b',
    ],

    # ------------------------------------------------------------------
    # VIDEO_CALL — requests for visual/camera communication
    # ------------------------------------------------------------------
    ContextType.VIDEO_CALL: [
        r'\bvideo\s+(?:call|chat)\b',
        r'\bfacetime\b',
        r'\bcamera\s+chat\b',
        r'\bturn\s+on\s+(?:your\s+)?(?:camera|webcam|cam)\b',
        r'\bshow\s+me\s+(?:yourself|your\s+face)\b',
        r'\blet\s+me\s+see\s+you\b',
        r'\bsend\s+(?:me\s+)?(?:a\s+)?(?:pic|picture|photo|selfie|video)\b',
        r'\b(?:zoom|skype|google\s+meet|discord)\s+(?:call|chat|me)\b',
        r'\bgo\s+on\s+(?:video|camera)\b',
        r'\bopen\s+(?:your\s+)?(?:camera|webcam)\b',
    ],

    # ------------------------------------------------------------------
    # EXPLICIT_CONTENT — sexual language, solicitation, explicit requests
    # ------------------------------------------------------------------
    ContextType.EXPLICIT_CONTENT: [
        r'\b(?:nude|naked|nudes?)\b',
        r'\b(?:send|show|share)\s+(?:me\s+)?(?:your\s+)?(?:body|boobs?|tits?|ass|dick|cock|pussy|vagina|penis)\b',
        r'\b(?:have|want\s+to\s+have|let\'?s\s+have)\s+sex\b',
        r'\b(?:oral\s+sex|blow\s+job|blowjob|hand\s+job|handjob|fingering|anal)\b',
        r'\b(?:sex\s+chat|sexting|sext(?:ing)?|dirty\s+talk|phone\s+sex|cyber\s+sex)\b',
        r'\b(?:are\s+you\s+a\s+virgin|have\s+you\s+had\s+sex)\b',
        r'\b(?:what\s+(?:do\s+you|are\s+you)\s+wearing\s+(?:right\s+now|in\s+bed))\b',
        r'\b(?:you\s+turn\s+me\s+on|i\'?m\s+horny|turned\s+on)\b',
        r'\b(?:i\s+want\s+to\s+(?:kiss|touch|feel|lick|suck)\s+you)\b',
        r'\b(?:masturbat(?:e|ing)|jerk\s+off|finger\s+yourself)\b',
        r'\b(?:let\'?s\s+fuck|wanna\s+fuck|want\s+to\s+fuck)\b',
        r'\b(?:child\s+porn|cp|csam|underage\s+(?:porn|content|photos?|videos?))\b',
    ],

    # ------------------------------------------------------------------
    # BAD_LANGUAGE — profanity, slurs, threats, harassment
    # ------------------------------------------------------------------
    ContextType.BAD_LANGUAGE: [
        r'\b(?:fuck(?:ing|er|ed)?|fuk(?:ing)?)\b',
        r'\b(?:shit(?:ty|head)?|bullshit)\b',
        r'\b(?:bitch(?:es|ing)?|bastard|asshole|dickhead|douchebag|dumbass|jackass)\b',
        r'\b(?:cunt|twat|wanker|prick|cock(?:sucker)?)\b',
        r'\b(?:motherfucker|mf|stfu|gtfo|kys)\b',
        r'\b(?:n[i1]gg(?:er|a)|n-word)\b',
        r'\b(?:f[a4]gg?[o0]t|dyke|tr[a4]nny)\b',
        r'\b(?:ret[a4]rd(?:ed)?)\b',
        r'\b(?:i\'?ll\s+(?:kill|hurt|beat|murder)\s+(?:you|u))\b',
        r'\b(?:kill\s+yourself|kys|go\s+die)\b',
        r'\b(?:you\'?re\s+(?:a\s+)?(?:slut|whore|hoe|skank))\b',
        r'\b(?:go\s+(?:fuck|screw)\s+yourself)\b',
    ],
}


# ---------------------------------------------------------------------------
# ContextAnalyzer class
# ---------------------------------------------------------------------------

class ContextAnalyzer:
    """
    Classify conversation sentences into semantic ContextTypes and return
    confidence multipliers.

    No speaker identity, role, or title is ever used.
    Analysis is LOCAL: only the current sentence ± immediate neighbours.
    """

    def __init__(self, context_window: int = 1):
        """
        Args:
            context_window: Reserved for future batch-window expansion.
                            Currently the API accepts one previous + one next.
        """
        self.context_window = context_window

        # Compile all patterns once at init
        self._compiled: Dict[ContextType, List[re.Pattern]] = {
            ctx_type: [re.compile(p, re.IGNORECASE) for p in patterns]
            for ctx_type, patterns in _CONTEXT_PATTERNS.items()
        }

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(
        self,
        sentence: str,
        previous_sentence: Optional[str] = None,
        next_sentence: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Classify the LOCAL window into one or more ContextTypes.

        Args:
            sentence: Main sentence to analyse.
            previous_sentence: Sentence immediately before (optional).
            next_sentence: Sentence immediately after (optional).

        Returns:
            {
                "primary_context":   ContextType (dominant type),
                "all_contexts":      List[ContextType] (all matched types),
                "multiplier":        float (net confidence adjustment),
                "matched_terms":     Dict[ContextType, List[str]],
                "is_administrative": bool,
            }
        """
        window = self._build_window(sentence, previous_sentence, next_sentence)
        matched: Dict[ContextType, List[str]] = {}

        for ctx_type, patterns in self._compiled.items():
            terms = []
            for pattern in patterns:
                for m in pattern.finditer(window):
                    term = m.group(0).strip()
                    if term not in terms:
                        terms.append(term)
            if terms:
                matched[ctx_type] = terms

        if not matched:
            return {
                "primary_context":   ContextType.NEUTRAL,
                "all_contexts":      [ContextType.NEUTRAL],
                "multiplier":        0.0,
                "matched_terms":     {},
                "is_administrative": False,
            }

        # Net multiplier = sum of all matched context multipliers
        # Clamped so it cannot push confidence below 0 or above 1 on its own.
        net_multiplier = sum(
            CONTEXT_MULTIPLIERS[ct] for ct in matched
        )
        net_multiplier = max(-1.0, min(1.0, net_multiplier))

        # Primary context = the type with the highest absolute multiplier
        # (most influential signal, positive or negative)
        primary = max(matched.keys(), key=lambda ct: abs(CONTEXT_MULTIPLIERS[ct]))

        return {
            "primary_context":   primary,
            "all_contexts":      list(matched.keys()),
            "multiplier":        round(net_multiplier, 3),
            "matched_terms":     matched,
            "is_administrative": ContextType.ADMINISTRATIVE in matched,
        }

    def analyze_context(
        self,
        sentence: str,
        previous_sentence: Optional[str] = None,
        next_sentence: Optional[str] = None,
        # Legacy keyword args — accepted but ignored (no role-based logic)
        current_speaker: Optional[str] = None,
        previous_speaker: Optional[str] = None,
        next_speaker: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Full context analysis — backward-compatible with the old API.

        Returns the classify() result plus legacy keys so existing callers
        (grooming_detector, confidence) do not break.
        """
        result = self.classify(sentence, previous_sentence, next_sentence)

        # Legacy compatibility keys
        all_ctx = result["all_contexts"]
        risk_types = {
            ContextType.SECRECY, ContextType.MANIPULATION, ContextType.ESCALATION,
            ContextType.MEETING, ContextType.PERSONAL_INFORMATION,
            ContextType.TRUST_BUILDING, ContextType.RELATIONSHIP_BUILDING,
            ContextType.VIDEO_CALL, ContextType.INFORMATION_GATHERING,
            ContextType.EXPLICIT_CONTENT, ContextType.BAD_LANGUAGE,
        }
        has_risk = any(ct in risk_types for ct in all_ctx)
        has_admin = result["is_administrative"]

        # Flatten all matched terms into a single list for legacy consumers
        all_terms = [t for terms in result["matched_terms"].values() for t in terms]

        result.update({
            # Legacy keys
            "safe_context":        has_admin,
            "risk_context":        has_risk,
            "matched_safe_terms":  result["matched_terms"].get(ContextType.ADMINISTRATIVE, []),
            "matched_risk_terms":  [
                t for ct, terms in result["matched_terms"].items()
                if ct in risk_types for t in terms
            ],
            "context_score":       round(result["multiplier"], 3),
            "dominant_context":    (
                "safe" if has_admin and not has_risk
                else "risk" if has_risk and not has_admin
                else "mixed" if has_risk and has_admin
                else "neutral"
            ),
            "safe_term_count":     len(result["matched_terms"].get(ContextType.ADMINISTRATIVE, [])),
            "risk_term_count":     sum(
                len(terms) for ct, terms in result["matched_terms"].items()
                if ct in risk_types
            ),
        })
        return result

    def batch_analyze(
        self,
        sentences: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Analyse multiple sentences in batch."""
        results = []
        for item in sentences:
            result = self.analyze_context(
                sentence=item.get("sentence", ""),
                previous_sentence=item.get("previous_sentence"),
                next_sentence=item.get("next_sentence"),
            )
            results.append(result)
        return results

    def get_context_multiplier(self, context_type: ContextType) -> float:
        """Return the confidence multiplier for a given ContextType."""
        return CONTEXT_MULTIPLIERS.get(context_type, 0.0)

    def explain_context(
        self,
        sentence: str,
        previous_sentence: Optional[str] = None,
        next_sentence: Optional[str] = None,
    ) -> str:
        """Generate a human-readable explanation of the context classification."""
        result = self.classify(sentence, previous_sentence, next_sentence)
        lines = [
            "Context Classification (content-based, no role assumptions):",
            f"  Primary Context : {result['primary_context'].value}",
            f"  All Contexts    : {', '.join(ct.value for ct in result['all_contexts'])}",
            f"  Net Multiplier  : {result['multiplier']:+.2f}",
            f"  Administrative  : {result['is_administrative']}",
            "",
            "  Matched Terms:",
        ]
        for ctx_type, terms in result["matched_terms"].items():
            lines.append(f"    [{ctx_type.value}] {', '.join(terms[:5])}")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _build_window(
        sentence: str,
        previous_sentence: Optional[str],
        next_sentence: Optional[str],
    ) -> str:
        """Concatenate the local window into a single string for scanning."""
        parts = []
        if previous_sentence:
            parts.append(previous_sentence.strip())
        parts.append(sentence.strip())
        if next_sentence:
            parts.append(next_sentence.strip())
        return " ".join(parts)


# ---------------------------------------------------------------------------
# Convenience functions (backward-compatible)
# ---------------------------------------------------------------------------

def analyze_sentence_context(
    sentence: str,
    previous_sentence: Optional[str] = None,
    next_sentence: Optional[str] = None,
    current_speaker: Optional[str] = None,
    previous_speaker: Optional[str] = None,
    next_speaker: Optional[str] = None,
) -> Dict[str, Any]:
    """Quick convenience function — speaker args accepted but ignored."""
    return ContextAnalyzer().analyze_context(
        sentence, previous_sentence, next_sentence
    )


def is_risk_context(sentence: str) -> bool:
    """Quick check — does the sentence contain risk context?"""
    result = ContextAnalyzer().classify(sentence)
    return result["primary_context"] not in (ContextType.NEUTRAL, ContextType.ADMINISTRATIVE)


def is_safe_context(sentence: str) -> bool:
    """Quick check — does the sentence contain administrative (safe) context?"""
    result = ContextAnalyzer().classify(sentence)
    return result["is_administrative"]


def get_context_type(sentence: str) -> ContextType:
    """Return the primary ContextType for a sentence."""
    return ContextAnalyzer().classify(sentence)["primary_context"]


__all__ = [
    "ContextType",
    "CONTEXT_MULTIPLIERS",
    "ContextAnalyzer",
    "analyze_sentence_context",
    "is_risk_context",
    "is_safe_context",
    "get_context_type",
]
