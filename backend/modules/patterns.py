"""
Production-ready regex pattern library for detecting grooming behaviors.

This module provides compiled regex patterns for identifying various grooming tactics
including parent monitoring, secrecy, trust building, manipulation, and more.

Each pattern includes:
- Compiled regex with case-insensitive matching
- Multiple phrase variations and paraphrases
- Confidence base score for risk assessment
- Category metadata
"""

import re
from typing import List, Dict, Any, Pattern


class PatternCategory:
    """Metadata for a pattern category."""
    
    def __init__(self, name: str, description: str, severity: str, weight: float):
        self.name = name
        self.description = description
        self.severity = severity  # low, medium, high, critical
        self.weight = weight  # 0.0 to 1.0


# Pattern Categories Metadata
CATEGORY_METADATA = {
    "parent_monitoring": PatternCategory(
        name="Parent Monitoring",
        description="Questions about parental supervision and monitoring",
        severity="high",
        weight=0.85
    ),
    "secrecy": PatternCategory(
        name="Secrecy",
        description="Requests to keep conversations or actions secret",
        severity="critical",
        weight=0.95
    ),
    "trust_building": PatternCategory(
        name="Trust Building",
        description="Attempts to establish trust and emotional connection",
        severity="medium",
        weight=0.80
    ),
    "relationship_building": PatternCategory(
        name="Relationship Building",
        description="Efforts to deepen relationship and create dependency",
        severity="high",
        weight=0.80
    ),
    "manipulation": PatternCategory(
        name="Manipulation",
        description="Manipulative tactics to control or influence",
        severity="critical",
        weight=0.90
    ),
    "video_call": PatternCategory(
        name="Video Call Request",
        description="Requests for video calls or visual communication",
        severity="high",
        weight=0.75
    ),
    "meeting": PatternCategory(
        name="Meeting Request",
        description="Attempts to arrange in-person meetings",
        severity="critical",
        weight=0.95
    ),
    "address": PatternCategory(
        name="Address/Location",
        description="Requests for physical address or location information",
        severity="critical",
        weight=0.90
    ),
    "school": PatternCategory(
        name="School Information",
        description="Questions about school, schedule, or educational details",
        severity="high",
        weight=0.70
    ),
    "routine": PatternCategory(
        name="Routine/Schedule",
        description="Questions about daily routines and schedules",
        severity="high",
        weight=0.75
    ),
    "explicit_content": PatternCategory(
        name="Explicit Content",
        description="Sexually explicit language, requests for sexual content, or sexual solicitation",
        severity="critical",
        weight=1.0
    ),
    "bad_language": PatternCategory(
        name="Bad Language / Profanity",
        description="Profanity, slurs, hate speech, and aggressive/abusive language",
        severity="medium",
        weight=0.60
    ),
}


# Confidence scores for each pattern (0.0 to 1.0)
PATTERN_CONFIDENCE = {
    "parent_monitoring":     0.85,
    "secrecy":               0.95,
    "trust_building":        0.80,
    "relationship_building": 0.75,
    "manipulation":          0.90,
    "video_call":            0.80,
    "meeting":               0.95,
    "address":               0.90,
    "school":                0.75,
    "routine":               0.80,
    "explicit_content":      0.98,   # near-certain when matched
    "bad_language":          0.85,
}


def compile_patterns(patterns: List[str]) -> List[Pattern]:
    """Compile a list of regex patterns with case-insensitive flag."""
    return [re.compile(pattern, re.IGNORECASE) for pattern in patterns]


# Parent Monitoring Patterns
PARENT_MONITORING_PATTERNS = compile_patterns([
    # Direct questions about parental monitoring
    r'\b(?:do|does|are|is)\s+(?:your|ur|the)?\s*(?:parents?|mom|mother|dad|father|mum|pa|guardian|guardians)\s+(?:check|read|monitor|see|look\s+at|watch|track|control|supervise)\s+(?:your|ur|the)?\s*(?:messages?|texts?|chats?|phone|conversations?|dms?|snaps?|posts?|social\s+media)',
    r'\b(?:parents?|mom|mother|dad|father|mum|pa|guardian|guardians)\s+(?:checking|reading|monitoring|seeing|looking\s+at|watching|tracking|controlling)\s+(?:your|ur|the)?\s*(?:messages?|texts?|chats?|phone|conversations?)',
    
    # "Whether" constructions
    r'\bwhether\s+(?:the\s+)?(?:student\'?s?|your|ur|their)\s+(?:parents?|mom|mother|dad|father|guardian|guardians)\s+(?:check|checked|monitor|monitored|see|read|look\s+at)',
    
    # Visibility questions
    r'\b(?:can|do|does)\s+(?:your|ur)\s+(?:parents?|mom|mother|dad|father|guardian|guardians)\s+see\s+(?:this|these|our|your|the)',
    
    # Parental control questions
    r'\b(?:are|is)\s+(?:your|ur)\s+(?:parents?|mom|mother|dad|father|guardian|guardians)\s+(?:strict|overprotective|controlling|watching\s+you)',
    r'\bhow\s+(?:much|often)\s+(?:do|does)\s+(?:your|ur)\s+(?:parents?|mom|mother|dad|father)\s+(?:check|monitor|watch)',
    
    # Awareness questions
    r'\b(?:your|ur)\s+(?:parents?|mom|mother|dad|father|guardian|guardians)\s+(?:know|aware|find\s+out)\s+(?:about|what)',
    r'\bwho\s+(?:checks?|monitors?|sees?|reads?)\s+(?:your|ur)\s+(?:phone|messages?|texts?|chats?)',
    
    # Access and control
    r'\b(?:parents?|mom|mother|dad|father|guardian|guardians)\s+(?:have|got|has)\s+(?:access|control)\s+(?:to|of|over)\s+(?:your|ur)',
    r'\bdo\s+(?:they|your\s+parents?|your\s+guardians?)\s+(?:check|monitor|read|see|look\s+at|track)',
    
    # Specific monitoring questions
    r'\b(?:does|do)\s+(?:your|ur)\s+(?:mom|mother|dad|father|parents?)\s+(?:read|check)\s+(?:your|ur)\s+(?:texts?|messages?)',
    r'\b(?:are|is)\s+(?:your|ur)\s+(?:parents?|guardians?)\s+(?:watching|monitoring)\s+(?:your|ur)\s+(?:messages?|chats?)',
])

# Secrecy Patterns
SECRECY_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # "Don't tell" — direct prohibition
    # ----------------------------------------------------------------
    # Original: don't/do not/never + tell/say/mention/share immediately
    r'\b(?:don\'?t|do\s+not|never)\s+(?:tell|say|mention|share|let)\s+(?:anyone|anybody|them|your\s+parents?|your\s+mom|your\s+dad)\b',
    # Required: "don't tell anyone" — explicit anchor
    r'\bdon\'?t\s+tell\s+anyone\b',
    # "didn't / did not need to tell anyone" — past-tense indirect prohibition
    # Covers: "didn't need to tell", "did not need to tell", "didn't have to tell"
    r'\b(?:didn\'?t|did\s+not|don\'?t|do\s+not|doesn\'?t|does\s+not)\s+(?:need|have|want|have\s+to|need\s+to)\s+(?:to\s+)?(?:tell|say|mention|share|inform)\s+(?:anyone|anybody|them|anyone\s+else)\b',

    # ----------------------------------------------------------------
    # "Nobody / no one needs to know" — present and past tense
    # ----------------------------------------------------------------
    # Original only matched "needs?" and "has" — missed "needed", "had to"
    r'\b(?:nobody|no\s+one|noone)\s+(?:needs?|needed|has|had|have)\s+(?:to\s+)?(?:know|find\s+out|hear|see)\b',
    # Required: "nobody needs to know" / "nobody else needs to know"
    r'\bnobody\s+(?:else\s+)?needs?\s+to\s+know\b',
    # Past tense: "nobody else needed to know"
    r'\bnobody\s+(?:else\s+)?needed\s+to\s+know\b',
    # Variants: "no one needs to know", "no one else needed to know"
    r'\bno\s+one\s+(?:else\s+)?(?:needs?|needed)\s+to\s+know\b',

    # ----------------------------------------------------------------
    # "Keep this between us" / "between us" constructions
    # ----------------------------------------------------------------
    r'\bkeep\s+(?:this|it|that|our)\s+(?:between\s+us|secret|private|quiet|to\s+yourself|confidential)\b',
    # Required: "keep this between us" — explicit anchor
    r'\bkeep\s+this\s+between\s+us\b',
    r'\bjust\s+(?:between|for)\s+(?:us|you\s+and\s+me)\b',
    r'\b(?:this|it)\s+(?:is|stays?)\s+(?:just\s+)?(?:between|for)\s+(?:us|you\s+and\s+me)\b',
    r'\b(?:this|it|that)\s+(?:is|stays?|remains?)\s+(?:our|a|just)?\s*(?:secret|private|between\s+us|confidential)\b',
    r'\b(?:let\'?s|we\s+should)\s+keep\s+(?:this|it|that|our)\s+(?:secret|private|quiet|between\s+us)\b',

    # ----------------------------------------------------------------
    # "Our secret" constructions
    # ----------------------------------------------------------------
    r'\b(?:our|this\s+is\s+our)\s+(?:little\s+)?secret\b',
    # Required: "our secret" — explicit anchor
    r'\bour\s+secret\b',

    # ----------------------------------------------------------------
    # "Private conversation" / "secret chat"
    # ----------------------------------------------------------------
    # Required: "private conversation"
    r'\bprivate\s+(?:conversation|chat|talk|message|messages?|discussion|call)\b',
    # Required: "secret chat"
    r'\bsecret\s+(?:chat|conversation|talk|message|messages?|channel|group)\b',
    # Broader: "private/secret" + communication medium
    r'\b(?:private|secret|hidden)\s+(?:account|profile|inbox|dm|dms|thread)\b',

    # ----------------------------------------------------------------
    # Deletion / erasure demands
    # ----------------------------------------------------------------
    r'\bdelete\s+(?:this|these|the|our)\s+(?:messages?|texts?|chats?|conversation|history)\b',
    r'\b(?:make\s+sure|be\s+sure)\s+(?:to\s+)?(?:delete|erase|clear|remove)\b',

    # ----------------------------------------------------------------
    # Prohibition on parental/third-party knowledge
    # ----------------------------------------------------------------
    r'\b(?:don\'?t|do\s+not)\s+(?:let|allow)\s+(?:anyone|anybody|them|your\s+parents?)\s+(?:know|find\s+out|see|hear)\b',
    r'\b(?:they|your\s+parents?|others?)\s+(?:won\'?t|wouldn\'?t|can\'?t|cannot)\s+(?:understand|get\s+it|approve)\b',
])

# Trust Building Patterns
TRUST_BUILDING_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Trustworthiness claims
    # ----------------------------------------------------------------
    r'\bI\'?m\s+(?:very\s+)?(?:trustworthy|reliable|honest|genuine|sincere)',
    r'\bI\'?m\s+(?:trustworthy\s+and\s+)?(?:friendly|kind|nice|good)',
    # "trustworthy" standalone — catches "I am trustworthy", "he's trustworthy"
    r'\b(?:am|is|are|was|were|be|been|being|seem(?:s)?|sound(?:s)?|appear(?:s)?)\s+trustworthy\b',
    # "friendly" as a trust signal in isolation
    r'\bI\'?m\s+(?:just\s+)?(?:being\s+)?friendly\b',
    r'\bI\'?m\s+a\s+(?:very\s+)?friendly\s+(?:person|guy|girl|adult|man|woman)\b',

    # ----------------------------------------------------------------
    # Care statements
    # ----------------------------------------------------------------
    r'\bI\s+(?:really\s+)?(?:care|care\s+about)\s+(?:you|u)\b',
    # "I care about you" — explicit required phrase
    r'\bI\s+care\s+about\s+you\b',

    # ----------------------------------------------------------------
    # Availability / support statements
    # ----------------------------------------------------------------
    r'\bI\'?m\s+(?:here|always\s+here|there)\s+for\s+(?:you|u)\b',
    # "I'm here for you" — explicit required phrase
    r'\bI\'?m\s+here\s+for\s+you\b',
    # "always talk to me" — explicit required phrase
    r'\b(?:you\s+can\s+)?always\s+(?:talk|come|reach\s+out)\s+to\s+me\b',
    r'\balways\s+talk\s+to\s+me\b',

    # ----------------------------------------------------------------
    # Understanding claims
    # ----------------------------------------------------------------
    r'\bI\s+(?:understand|get)\s+(?:you|u)\s+(?:better\s+than|more\s+than)\s+(?:anyone|anybody|others?|they\s+do|anyone\s+else)\b',
    # "I understand you" — explicit required phrase
    r'\bI\s+understand\s+(?:you|u)\b',
    # "understand you better than anyone" — explicit required phrase
    r'\bunderstand\s+(?:you|u)\s+better\s+than\s+(?:anyone|anybody|anyone\s+else|they\s+do)\b',

    # ----------------------------------------------------------------
    # Trust directives
    # ----------------------------------------------------------------
    r'\btrust\s+me\b',
    r'\byou\s+(?:know|can\s+see)\s+(?:you\s+can\s+)?trust\s+me\b',
    # "you can trust me" — explicit required phrase
    r'\byou\s+can\s+(?:always\s+)?trust\s+me\b',
    # "I'm someone you can trust" — explicit required phrase
    r'\bI\'?m\s+(?:someone|a\s+person|the\s+(?:kind|type)\s+of\s+person)\s+(?:who|that|you\s+can)\s+(?:you\s+can\s+)?trust\b',
    r'\bI\'?m\s+someone\s+you\s+can\s+trust\b',

    # ----------------------------------------------------------------
    # Openness invitations
    # ----------------------------------------------------------------
    r'\byou\s+can\s+(?:tell|share|say)\s+(?:me\s+)?anything\b',
    r'\byou\s+can\s+always\s+talk\s+to\s+me\b',
    r'\byou\s+can\s+(?:always\s+)?(?:trust|count\s+on|rely\s+on|depend\s+on|talk\s+to|confide\s+in)\s+me\b',

    # ----------------------------------------------------------------
    # Promises / non-judgment
    # ----------------------------------------------------------------
    r'\bI\'?ll\s+(?:never|not)\s+(?:judge|hurt|betray|disappoint)\s+(?:you|u)\b',
    r'\bI\s+(?:would\s+)?never\s+(?:lie|deceive|trick|mislead)\s+(?:to\s+)?(?:you|u)\b',

    # ----------------------------------------------------------------
    # Friendship claims
    # ----------------------------------------------------------------
    r'\bI\'?m\s+(?:your|ur)\s+(?:friend|best\s+friend|true\s+friend)\b',
    r'\bwe\s+are\s+(?:becoming\s+)?(?:good\s+)?friends?\b',

    # ----------------------------------------------------------------
    # Uniqueness / exclusivity claims
    # ----------------------------------------------------------------
    r'\bI\'?m\s+(?:the\s+only\s+one|one\s+of\s+the\s+few)\s+(?:who|that)\s+(?:understands?|gets?|cares?)\b',
])

# Relationship Building Patterns
RELATIONSHIP_BUILDING_PATTERNS = compile_patterns([
    # Compliments
    r'\byou\'?re\s+(?:so\s+)?(?:special|unique|different|amazing|beautiful|gorgeous|cute|hot|attractive)',
    
    # Affection statements
    r'\bI\s+(?:really\s+)?(?:like|love|adore|admire)\s+(?:you|u|talking\s+to\s+you)',
    
    # Uniqueness claims
    r'\byou\'?re\s+(?:not\s+like|different\s+from)\s+(?:other|most)\s+(?:people|kids|girls|boys)',
    
    # Connection claims
    r'\bwe\s+have\s+(?:a\s+)?(?:special|unique|strong)\s+(?:connection|bond|relationship)',
    r'\b(?:special|close|good)\s+(?:connection|friendship)',
    
    # Closeness statements
    r'\bI\s+feel\s+(?:so\s+)?(?:close|connected)\s+to\s+(?:you|u)',
    
    # Importance statements
    r'\byou\s+(?:mean|are)\s+(?:so\s+much|everything)\s+to\s+me',
    
    # Uniqueness of relationship
    r'\bI\'?ve\s+never\s+(?:met|known|felt\s+this\s+way\s+about)\s+(?:anyone|somebody)\s+like\s+(?:you|u)',
    r'\byou\'?re\s+(?:my|the)\s+(?:only|best)\s+(?:friend|one)',
    
    # Obsessive thoughts
    r'\bI\s+(?:can\'?t|cannot)\s+(?:stop\s+)?thinking\s+(?:about|of)\s+(?:you|u)',
    
    # Happiness statements
    r'\byou\s+make\s+me\s+(?:so\s+)?(?:happy|feel\s+good|smile)',
    
    # Similarity claims
    r'\bwe\'?re\s+(?:so\s+)?(?:close|connected|alike|similar)',
    r'\bwe\s+understand\s+each\s+other',
    r'\b(?:our|this)\s+friendship\s+is\s+(?:special|different|unique)',
    
    # Desire for togetherness
    r'\bI\s+wish\s+(?:I\s+could|we\s+could)\s+(?:be\s+together|see\s+you|meet\s+you)',
])

# Manipulation Patterns
MANIPULATION_PATTERNS = compile_patterns([
    # Misunderstanding claims
    r'\b(?:they|your\s+parents?|others?)\s+(?:won\'?t|wouldn\'?t|don\'?t|will\s+not|would\s+not|do\s+not)\s+(?:understand|get\s+it)',
    r'\b(?:your|ur)\s+(?:parents?|mom|dad|mother|father)\s+(?:will|would|might)\s+(?:overreact|freak\s+out|be\s+mad|get\s+angry)',
    r'\b(?:they|parents?)\s+(?:might|will)\s+misunderstand',
    
    # Exclusive understanding
    r'\b(?:only|just)\s+I\s+(?:understand|get|know)\s+(?:you|u)',
    r'\bI\'?m\s+the\s+only\s+one\s+(?:who|that)\s+(?:understands?|gets?|cares?|knows?)',
    r'\b(?:nobody|no\s+one)\s+(?:else\s+)?(?:understands?|gets?)\s+(?:you|u)\s+(?:like\s+I\s+do)?',
    
    # Conditional love/trust
    r'\b(?:if|when)\s+you\s+(?:really\s+)?(?:loved?|cared?|trusted?)\s+me',
    
    # Proof demands
    r'\bprove\s+(?:to\s+me\s+)?(?:that\s+)?you\s+(?:love|trust|care)',
    
    # Conditional threats
    r'\bif\s+you\s+(?:don\'?t|do\s+not)\s+(?:do\s+this|send|share)',
    
    # Obligation claims
    r'\byou\s+(?:owe|promised)\s+me',
    r'\bI\s+(?:did|shared|sent|gave)\s+(?:this|that|something)\s+for\s+you',
    
    # Peer pressure
    r'\b(?:everyone|all\s+your\s+friends?)\s+(?:does?|is\s+doing)\s+(?:this|it)',
    
    # Maturity manipulation
    r'\byou\'?re\s+(?:being|acting)\s+(?:immature|childish|silly)',
    r'\bI\s+thought\s+you\s+were\s+(?:mature|different|special)',
    
    # Desire manipulation
    r'\b(?:don\'?t|do\s+not)\s+(?:you\s+)?(?:want|like)\s+(?:me|us|this)',
])

# Video Call Patterns
VIDEO_CALL_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Generic video/call initiation — "let's call", "can we video chat"
    # ----------------------------------------------------------------
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna|shall\s+we)\s+(?:video\s+)?(?:call|chat|facetime|skype|zoom|hangout)\b',
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna)\s+(?:do\s+a\s+)?(?:video\s+call|video\s+chat|voice\s+call|audio\s+call)\b',

    # ----------------------------------------------------------------
    # "private video call" — explicit required phrase (BUG #8)
    # ----------------------------------------------------------------
    r'\bprivate\s+video\s+(?:call|chat|session)\b',
    # "private call" — explicit required phrase (BUG #8)
    r'\bprivate\s+(?:call|chat|conversation|talk)\b',
    # "call privately" — explicit required phrase (BUG #8)
    r'\bcall\s+(?:you\s+)?privately\b',
    r'\b(?:talk|chat|speak)\s+(?:to\s+you\s+)?privately\b',

    # ----------------------------------------------------------------
    # "video chat" — explicit required phrase (BUG #8)
    # ----------------------------------------------------------------
    r'\bvideo\s+chat\b',
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna)\s+video\s+chat\b',

    # ----------------------------------------------------------------
    # "FaceTime" — explicit required phrase (BUG #8)
    # ----------------------------------------------------------------
    r'\bfacetime\b',
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna|do\s+a)\s+facetime\b',
    r'\bfacetime\s+(?:me|you|us|with\s+me|with\s+you)\b',

    # ----------------------------------------------------------------
    # "one-on-one call" / "one on one call" — explicit required phrase (BUG #8)
    # ----------------------------------------------------------------
    r'\bone[\s\-]on[\s\-]one\s+(?:call|chat|video|session|talk|conversation)\b',
    r'\b1[\s\-]on[\s\-]1\s+(?:call|chat|video|session|talk|conversation)\b',

    # ----------------------------------------------------------------
    # "camera chat" — explicit required phrase (BUG #8)
    # ----------------------------------------------------------------
    r'\bcamera\s+chat\b',
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna)\s+camera\s+chat\b',

    # ----------------------------------------------------------------
    # Camera control requests
    # ----------------------------------------------------------------
    r'\b(?:turn\s+on|switch\s+on|enable|put\s+on)\s+(?:your|ur)\s+(?:camera|webcam|video|cam)\b',
    r'\bopen\s+(?:your|ur)\s+(?:camera|webcam|video|cam)\b',
    r'\b(?:go|get)\s+on\s+(?:video|camera|webcam|cam)\b',
    r'\bshow\s+(?:me\s+)?(?:your|ur)\s+(?:camera|face|video)\b',

    # ----------------------------------------------------------------
    # Visual requests — "show me", "let me see you"
    # ----------------------------------------------------------------
    r'\b(?:show|let)\s+me\s+(?:see\s+)?(?:you|your\s+face|yourself)\b',
    r'\bI\s+(?:want|wanna|would\s+like|\'d\s+like)\s+to\s+see\s+(?:you|your\s+face)\b',
    r'\bcan\s+(?:I\s+)?see\s+(?:you|your\s+face|what\s+you\s+look\s+like)\b',
    r'\bI\s+want\s+to\s+see\s+(?:your|ur)\s+(?:face|smile|eyes)\b',

    # ----------------------------------------------------------------
    # Media requests — pics, videos, selfies
    # ----------------------------------------------------------------
    r'\b(?:send|share)\s+(?:me\s+)?(?:a\s+)?(?:video|pic|picture|photo|selfie)\b',

    # ----------------------------------------------------------------
    # Named video platforms
    # ----------------------------------------------------------------
    r'\b(?:video|face)\s+(?:call|chat|time)\s+(?:me|with\s+me)\b',
    r'\b(?:zoom|skype|google\s+meet|teams|discord|snapchat\s+video|instagram\s+video)\s+(?:call|chat|me|with\s+me)\b',
    r'\b(?:let\'?s|can\s+we)\s+(?:zoom|skype|discord)\b',

    # ----------------------------------------------------------------
    # Escalation phrasing — "just us on a call", "alone on video"
    # ----------------------------------------------------------------
    r'\b(?:just\s+(?:us|you\s+and\s+me)|alone)\s+on\s+(?:a\s+)?(?:call|video|camera|facetime)\b',
    r'\b(?:video\s+call|call|facetime)\s+(?:alone|just\s+us|just\s+you\s+and\s+me|privately|in\s+private)\b',
    r'\balone\s+on\s+(?:a\s+)?(?:call|video|camera)\b',
])

# Meeting Patterns
MEETING_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # "meet" — bare and prefixed forms
    # ----------------------------------------------------------------
    # "meet up" — bare phrase anchor
    r'\bmeet\s+up\b',
    # "meet sometime" / "meet one day" — future-intent bare anchors
    r'\bmeet\s+(?:sometime|someday|one\s+day|soon|later|eventually)\b',
    # "meet in person" — bare phrase anchor
    r'\bmeet\s+in\s+person\b',
    # "we could/should/can/will meet" — modal + meet (no required prefix)
    r'\b(?:we|you\s+and\s+I|you\s+and\s+me)\s+(?:could|should|can|will|would|might)\s+(?:meet|meet\s+up|get\s+together|hang\s+out)\b',
    # "maybe we can meet" / "perhaps we could meet"
    r'\b(?:maybe|perhaps|possibly)\s+(?:we|you\s+and\s+I)\s+(?:can|could|should|will)\s+(?:meet|meet\s+up|hang\s+out|get\s+together)\b',
    # "let's / can we / want to / wanna" + meet/hang/get together
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna|shall\s+we)\s+(?:meet|meet\s+up|hang\s+out|get\s+together|see\s+each\s+other)\b',
    # "where/when can/should we meet"
    r'\b(?:where|when)\s+(?:can|should|could|shall)\s+we\s+(?:meet|meet\s+up|hang\s+out|get\s+together)\b',
    # "when are/can we meeting/hanging out"
    r'\bwhen\s+(?:are|can)\s+(?:we|you)\s+(?:meet(?:ing)?|hang(?:ing)?\s+out|get(?:ting)?\s+together)\b',

    # ----------------------------------------------------------------
    # "hang out" — bare and prefixed forms
    # ----------------------------------------------------------------
    # "hang out" — bare phrase anchor
    r'\bhang\s+out\b',
    # "we should/could hang out"
    r'\b(?:we|you\s+and\s+I)\s+(?:should|could|can|will|would)\s+hang\s+out\b',

    # ----------------------------------------------------------------
    # "get together" — bare and prefixed forms
    # ----------------------------------------------------------------
    # "get together" — bare phrase anchor
    r'\bget\s+together\b',
    # "let's / we should get together"
    r'\b(?:let\'?s|we\s+should|we\s+could)\s+get\s+together\b',

    # ----------------------------------------------------------------
    # "see each other" — bare and prefixed forms
    # ----------------------------------------------------------------
    # "see each other" — bare phrase anchor
    r'\bsee\s+each\s+other\b',
    # "let's see each other" / "we should see each other"
    r'\b(?:let\'?s|we\s+should|we\s+could|want\s+to)\s+see\s+each\s+other\b',

    # ----------------------------------------------------------------
    # In-person / IRL / face to face
    # ----------------------------------------------------------------
    r'\bI\s+(?:want|wanna|would\s+like|\'d\s+like)\s+to\s+(?:meet|see)\s+(?:you|u)\s+(?:in\s+person|irl|face\s+to\s+face)\b',
    r'\b(?:meet|see)\s+(?:you|u)\s+(?:in\s+person|irl|face\s+to\s+face)\b',
    # "we could meet in person" / "meet in person sometime"
    r'\b(?:meet|see\s+each\s+other)\s+in\s+person\b',
    # "face to face" — bare phrase anchor
    r'\bface\s+to\s+face\b',
    # "in person" as standalone meeting signal
    r'\bin\s+person\b',

    # ----------------------------------------------------------------
    # Public place — meeting location signal
    # ----------------------------------------------------------------
    # "public place" — bare phrase anchor
    r'\bpublic\s+place\b',
    # "meet at a public place / somewhere public"
    r'\b(?:meet|hang\s+out|get\s+together)\s+(?:at\s+a?\s*)?(?:public\s+place|public\s+spot|somewhere\s+public|public\s+location)\b',
    r'\bsomewhere\s+(?:public|neutral|safe|nearby)\b',
    r'\ba\s+(?:public|neutral|safe)\s+(?:place|spot|location|venue)\b',

    # ----------------------------------------------------------------
    # Come over / pick up / physical arrival
    # ----------------------------------------------------------------
    r'\b(?:come|go)\s+(?:to|over\s+to)\s+(?:my|your)\s+(?:place|house|home|flat|apartment)\b',
    r'\bI\'?ll?\s+(?:come|pick\s+(?:you\s+)?up|meet\s+you)\s+(?:at|near|outside|by)\b',
    r'\bI\s+(?:can|could|will|would)\s+(?:come|pick\s+(?:you\s+)?up|meet\s+you)\b',
    # "meet me at/in/near" — direct rendezvous instruction
    r'\b(?:meet|see)\s+me\s+(?:at|in|near|outside|by)\b',

    # ----------------------------------------------------------------
    # Sneak out
    # ----------------------------------------------------------------
    r'\b(?:sneak|slip)\s+out\s+(?:to\s+)?(?:meet|see)\s+(?:me|us)\b',
    r'\bsneak\s+out\b',
])

# Address/Location Patterns
ADDRESS_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Direct address requests — "your address", "full address", "home address"
    # ----------------------------------------------------------------
    r'\b(?:what\'?s|where\'?s|tell\s+me|give\s+me|send\s+me)\s+(?:your|ur|the)\s+(?:full\s+)?(?:address|location|place)\b',
    # "full address" — bare phrase anchor
    r'\bfull\s+address\b',
    # "home address" — bare phrase anchor (also catches "your home address")
    r'\bhome\s+address\b',
    # "your/ur address/location" with any leading verb
    r'\b(?:send|share|give|tell|drop|post)\s+(?:me\s+)?(?:your|ur)\s+(?:address|location)\b',
    r'\b(?:your|ur)\s+(?:house|home|full|exact|current)\s+(?:address|location)\b',

    # ----------------------------------------------------------------
    # "Where do you live" and variants
    # ----------------------------------------------------------------
    r'\bwhere\s+do\s+you\s+(?:live|stay|reside)\b',
    r'\bwhere\s+(?:exactly|precisely)\s+(?:do\s+you|are\s+you)\s*(?:live|stay|located|based|from)?\b',
    # "where exactly do you live" — explicit anchor
    r'\bwhere\s+exactly\s+do\s+you\s+live\b',

    # ----------------------------------------------------------------
    # Street — "what street", "street name", "tell me your street"
    # ----------------------------------------------------------------
    # "what street" — bare phrase anchor
    r'\bwhat\s+street\b',
    # "street name" — bare phrase anchor
    r'\bstreet\s+name\b',
    # "what street do you live on / what street are you on"
    r'\bwhat\s+street\s+(?:do\s+you|are\s+you|is\s+(?:that|it))\b',
    # "tell me your street / what's your street"
    r'\b(?:what\'?s|tell\s+me|give\s+me)\s+(?:your|ur|the)\s+street(?:\s+name)?\b',
    # broader: any street/road/avenue inquiry
    r'\bwhat\s+(?:street|road|avenue|lane|drive|boulevard|crescent)\s+(?:do\s+you|are\s+you|is\s+(?:that|it))\b',

    # ----------------------------------------------------------------
    # House number
    # ----------------------------------------------------------------
    # "house number" — bare phrase anchor
    r'\bhouse\s+number\b',
    r'\b(?:what\'?s|tell\s+me|give\s+me)\s+(?:your|ur|the)\s+house\s+(?:number|no\.?)\b',
    r'\b(?:what|which)\s+(?:house|flat|apartment|unit)\s+(?:number|no\.?)?\s*(?:do\s+you|are\s+you|is\s+(?:that|it))?\b',

    # ----------------------------------------------------------------
    # Neighborhood / area
    # ----------------------------------------------------------------
    # "which neighborhood" — bare phrase anchor (also British spelling)
    r'\bwhich\s+neighbo(?:u)?rhood\b',
    # "what area do you live in" — explicit anchor
    r'\bwhat\s+area\s+(?:do\s+you|are\s+you)\s+(?:live\s+in|in|from|based\s+in)?\b',
    # broader neighborhood/area/district questions
    r'\bwhat\s+(?:area|neighborhood|neighbourhood|district|part\s+of\s+town|part\s+of\s+the\s+city)\s+(?:do\s+you|are\s+you)\b',
    r'\bwhich\s+(?:area|neighborhood|neighbourhood|district|part\s+of\s+town)\s+(?:do\s+you|are\s+you)\b',
    r'\bwhat\s+(?:street|area|neighborhood|neighbourhood|city|town|district)\s+(?:do\s+you|are\s+you)\b',

    # ----------------------------------------------------------------
    # Proximity / distance
    # ----------------------------------------------------------------
    r'\bhow\s+(?:far|close)\s+(?:do\s+you|are\s+you)\s+(?:live|stay)\b',
    r'\b(?:near|close\s+to)\s+(?:what|which)\s+(?:landmark|place|area)\b',

    # ----------------------------------------------------------------
    # Location sharing / pinning
    # ----------------------------------------------------------------
    r'\b(?:pin|share|drop|send)\s+(?:your|ur)\s+location\b',
    r'\bshare\s+(?:your|ur)\s+(?:live\s+)?location\b',

    # ----------------------------------------------------------------
    # Postal / zip codes
    # ----------------------------------------------------------------
    r'\bwhat\'?s\s+(?:your|ur|the)\s+(?:zip\s+code|postal\s+code|pin\s+code|postcode)\b',
    r'\b(?:zip|postal|pin)\s+code\b',
])

# School Information Patterns
SCHOOL_PATTERNS = compile_patterns([
    # --- school identity ---
    # "which school", "what school" — explicit required phrases
    r'\b(?:which|what)\s+school\b',
    r'\b(?:what|which)\s+school\s+(?:do\s+you|are\s+you|did\s+you|is\s+that)',
    r'\bwhere\s+do\s+you\s+(?:go\s+to\s+)?school',
    r'\b(?:tell|what\'?s)\s+(?:me\s+)?(?:your|ur)\s+school\s+(?:name|called)',
    r'\bname\s+(?:of\s+)?(?:your|ur)\s+school\b',

    # --- grade / class / year ---
    # "what grade", "what class" — explicit required phrases
    r'\bwhat\s+(?:grade|class)\b',
    r'\bwhat\s+(?:grade|class|year|standard)\s+(?:are\s+you|you\s+in|do\s+you\s+go\s+to)',
    r'\bwhich\s+(?:grade|class|year|standard)\s+(?:are\s+you|you\s+in)',
    r'\bwhat\s+(?:grade|class|year|standard)\s+(?:is\s+that|is\s+it)',

    # --- school end / dismissal time ---
    # "when classes end", "when do classes end", "what time school ends"
    r'\bwhen\s+(?:do(?:es)?|did)\s+(?:your\s+)?(?:school|classes?)\s+(?:end|finish|get\s+out|let\s+out|dismiss)',
    r'\bwhat\s+time\s+(?:do(?:es)?|did)?\s*(?:your\s+)?(?:school|classes?)\s+(?:end|ends?|finish|get\s+out|let\s+out|dismiss)',
    r'\bwhen\s+(?:is|are)\s+(?:your\s+)?(?:school|classes?)\s+(?:over|done|finished)',
    r'\bwhat\s+time\s+(?:is|are|does|do)?\s*(?:your\s+)?(?:school|classes?)\s+(?:over|done|finished|end|ends?)',
    # "when do you leave school" — explicit required phrase
    r'\bwhen\s+do\s+you\s+leave\s+school\b',
    r'\bwhat\s+time\s+do\s+you\s+leave\s+school\b',
    r'\bwhen\s+(?:do\s+you|are\s+you)\s+(?:done|finished|out)\s+(?:with\s+)?school\b',

    # --- general school schedule ---
    r'\bwhen\s+(?:does|do)\s+(?:your|ur)\s+(?:school|classes?)\s+(?:start|end|finish|get\s+out)',
    r'\b(?:your|ur)\s+school\s+(?:schedule|timing|hours)',
    r'\bwhat\s+time\s+(?:does|do)\s+(?:your|ur)\s+(?:school|classes?)',
    r'\bwho\'?s\s+(?:your|ur)\s+(?:teacher|principal)',
    r'\bwhat\s+(?:subjects?|classes?)\s+(?:do\s+you|are\s+you)',
    r'\b(?:when|what\s+time)\s+(?:is|are)\s+(?:your|ur)\s+(?:lunch|break|recess)',
])

# Routine/Schedule Patterns
ROUTINE_PATTERNS = compile_patterns([
    r'\bwhat\s+(?:do\s+you|are\s+you)\s+(?:do|doing)\s+(?:after|on)',
    r'\bwhen\s+(?:are|will)\s+you\s+(?:be\s+)?(?:alone|free|available|home)',
    r'\b(?:what\'?s|tell\s+me)\s+(?:your|ur)\s+(?:schedule|routine|daily\s+routine)',
    r'\bwhat\s+time\s+(?:do\s+you|are\s+you)\s+(?:usually|normally)',
    r'\bwhen\s+(?:do|are)\s+(?:your|ur)\s+(?:parents?|mom|dad)\s+(?:leave|go\s+to\s+work|come\s+home)',
    r'\b(?:are|will)\s+you\s+(?:be\s+)?(?:alone|by\s+yourself)\s+(?:at|on)',
    r'\bwhat\s+(?:do\s+you|are\s+you)\s+(?:do|doing)\s+(?:on\s+)?(?:weekends?|evenings?|nights?)',
    r'\bwhen\s+(?:can|could)\s+(?:we|you)\s+(?:talk|chat|call)',
    r'\b(?:your|ur)\s+(?:daily|usual)\s+(?:schedule|routine)',
    r'\bwhat\s+time\s+(?:do\s+you|are\s+you)\s+(?:wake\s+up|go\s+to\s+bed|sleep)',

    # --- walk home / route home ---
    # "walk home" — explicit required phrase
    r'\bwalk\s+home\b',
    r'\bdo\s+you\s+walk\s+home\b',
    r'\bhow\s+(?:do\s+you|do\s+u)\s+(?:get|go|walk|travel|come)\s+home\b',
    # "how do you get home" — explicit required phrase
    r'\bhow\s+do\s+you\s+get\s+home\b',
    r'\b(?:do\s+you|you)\s+(?:walk|bike|cycle|take\s+the\s+bus|take\s+a\s+bus|get\s+a\s+ride)\s+home\b',
    r'\bwho\s+(?:picks?\s+you\s+up|takes?\s+you\s+home|walks?\s+(?:you|with\s+you)\s+home)\b',
    r'\bdo\s+you\s+(?:walk|go)\s+home\s+(?:alone|by\s+yourself)\b',

    # --- route ---
    # "which route", "usual route" — explicit required phrases
    r'\bwhich\s+route\b',
    r'\busual\s+route\b',
    r'\b(?:which|what)\s+(?:route|way|path|road)\s+(?:do\s+you|do\s+u|you)\s+(?:take|use|walk|go)',
    r'\bwhat\s+(?:route|way|path)\s+(?:do\s+you|do\s+u)\s+(?:take|use|walk|go)\s+(?:home|to\s+school)',
    r'\b(?:your|ur)\s+(?:usual|normal|regular)\s+(?:route|way|path)\b',
    r'\bwhich\s+(?:way|road|street|path)\s+(?:do\s+you|do\s+u)\s+(?:take|use|walk|go)\b',

    # --- when do you leave school (also a routine signal) ---
    r'\bwhen\s+do\s+you\s+leave\s+school\b',
    r'\bwhat\s+time\s+do\s+you\s+leave\s+school\b',
])


# ---------------------------------------------------------------------------
# Explicit Content Patterns
# Covers: sexual solicitation, requests for nude/sexual images, sexual acts,
# age-inappropriate sexual language directed at or involving a person.
# ---------------------------------------------------------------------------
EXPLICIT_CONTENT_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Requests for nude / sexual images or video
    # ----------------------------------------------------------------
    r'\b(?:send|share|show|post|upload|snap)\s+(?:me\s+)?(?:a\s+)?(?:nude|naked|nudes|naked\s+pic|naked\s+photo|topless|bottomless)\b',
    r'\b(?:send|share|show)\s+(?:me\s+)?(?:your\s+)?(?:body|boobs?|tits?|ass|butt|dick|cock|penis|vagina|pussy|genitals?)\b',
    r'\b(?:nude|naked)\s+(?:pic|picture|photo|selfie|video|snap|image)\b',
    r'\b(?:nudes?|naked\s+pics?|naked\s+photos?|topless\s+pics?)\b',
    r'\b(?:send|show)\s+(?:me\s+)?(?:your\s+)?(?:private\s+parts?|intimate\s+parts?|body\s+parts?)\b',
    r'\b(?:take\s+off|remove)\s+(?:your\s+)?(?:clothes?|shirt|top|bra|underwear|pants|shorts)\s+(?:on\s+camera|for\s+me|in\s+the\s+video)\b',

    # ----------------------------------------------------------------
    # Sexual acts — requests, suggestions, descriptions
    # ----------------------------------------------------------------
    r'\b(?:have|want\s+to\s+have|let\'?s\s+have)\s+sex\b',
    r'\b(?:do|want\s+to\s+do|let\'?s\s+do)\s+(?:it|this|that)\s+(?:together|with\s+me)\b(?=.*(?:sex|sexual|intimate|naked|nude))',
    r'\b(?:oral\s+sex|blow\s+job|blowjob|hand\s+job|handjob|fingering|anal|anal\s+sex)\b',
    r'\b(?:make\s+love|sleep\s+with\s+(?:me|you)|hook\s+up\s+with\s+(?:me|you))\b',
    r'\b(?:sexual|sexually)\s+(?:explicit|active|involved|interested)\b',
    r'\b(?:touch|feel|grab|grope)\s+(?:you|your\s+body|your\s+(?:boobs?|ass|dick|pussy))\b',
    r'\b(?:masturbat(?:e|ing|ion)|jerk\s+off|finger\s+yourself)\b',
    r'\b(?:sex\s+chat|sexting|sext(?:ing)?|dirty\s+talk|phone\s+sex|cyber\s+sex|cybersex)\b',
    r'\b(?:sexual\s+favor|sexual\s+act|sexual\s+content|sexual\s+photo|sexual\s+video)\b',

    # ----------------------------------------------------------------
    # Age-inappropriate sexual interest / grooming escalation
    # ----------------------------------------------------------------
    r'\b(?:are\s+you\s+a\s+virgin|have\s+you\s+(?:had|ever\s+had)\s+sex|have\s+you\s+done\s+it)\b',
    r'\b(?:do\s+you\s+(?:touch|pleasure|play\s+with)\s+yourself)\b',
    r'\b(?:what\s+(?:do\s+you|are\s+you)\s+wearing\s+(?:right\s+now|in\s+bed|to\s+sleep))\b',
    r'\b(?:describe\s+(?:your\s+body|yourself\s+naked|what\s+you\s+look\s+like\s+naked))\b',
    r'\b(?:are\s+you\s+(?:in\s+bed|in\s+your\s+room|alone\s+in\s+your\s+room))\b',
    r'\b(?:do\s+you\s+(?:like|enjoy)\s+(?:sex|being\s+touched|kissing))\b',
    r'\b(?:have\s+you\s+(?:kissed|been\s+kissed|made\s+out)\s+(?:with\s+anyone|before))\b',
    r'\b(?:i\s+want\s+to\s+(?:kiss|touch|feel|lick|suck)\s+(?:you|your))\b',
    r'\b(?:you\s+(?:turn\s+me\s+on|make\s+me\s+(?:horny|hard|wet)))\b',
    r'\b(?:i\'?m\s+(?:horny|turned\s+on|aroused)\s+(?:by\s+you|thinking\s+about\s+you))\b',

    # ----------------------------------------------------------------
    # Explicit sexual language / slang
    # ----------------------------------------------------------------
    r'\b(?:fuck(?:ing)?|fucked|fucker|fucks?)\s+(?:you|me|her|him|them|each\s+other|together)\b',
    r'\b(?:let\'?s\s+fuck|wanna\s+fuck|want\s+to\s+fuck)\b',
    r'\b(?:rape|molest|assault)\s+(?:you|her|him|them)\b',
    r'\b(?:child\s+porn|cp|csam|underage\s+(?:porn|content|photos?|videos?))\b',
    r'\b(?:loli|shota|minor\s+(?:nude|naked|sexual))\b',
])

# ---------------------------------------------------------------------------
# Bad Language / Profanity Patterns
# Covers: profanity, slurs, hate speech, aggressive/threatening language.
# NOTE: These are detected as a separate category so they can be weighted
# independently from explicit sexual content.
# ---------------------------------------------------------------------------
BAD_LANGUAGE_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Common profanity (standalone or directed)
    # ----------------------------------------------------------------
    r'\b(?:fuck(?:ing|er|ers|ed|face|head|wit|wad|tard)?|fuk(?:ing)?)\b',
    r'\b(?:shit(?:ty|head|bag|face|hole)?|bullshit)\b',
    r'\b(?:bitch(?:es|ing|ass)?|bastard|asshole|ass\s*hole|dickhead|douchebag|dumbass|jackass|dipshit)\b',
    r'\b(?:cunt|twat|wanker|tosser|prick|cock(?:sucker)?)\b',
    r'\b(?:motherfucker|mf|stfu|gtfo|kys)\b',

    # ----------------------------------------------------------------
    # Slurs — racial, ethnic, gender, sexuality
    # (listed as patterns; detection is for safety monitoring only)
    # ----------------------------------------------------------------
    r'\b(?:n[i1]gg(?:er|a|ers|as)|n-word)\b',
    r'\b(?:ch[i1]nk|g[o0]{2}k|sp[i1]c|w[e3]tb[a4]ck|k[i1]ke|cr[a4]cker|h[a4]jji)\b',
    r'\b(?:f[a4]gg?[o0]t|dyke|tr[a4]nny|sh[e3]male)\b',
    r'\b(?:ret[a4]rd(?:ed)?|sp[a4]z|mong|cr[i1]pple)\b',

    # ----------------------------------------------------------------
    # Threats and aggressive language
    # ----------------------------------------------------------------
    r'\b(?:i\'?ll\s+(?:kill|hurt|beat|destroy|murder|rape)\s+(?:you|u|her|him|them))\b',
    r'\b(?:you\'?re\s+(?:dead|going\s+to\s+die|finished|done))\b',
    r'\b(?:kill\s+yourself|kys|go\s+die|drop\s+dead)\b',
    r'\b(?:i\s+(?:hate|despise|loathe)\s+(?:you|u|all\s+of\s+you))\b',
    r'\b(?:shut\s+(?:up|the\s+fuck\s+up|your\s+mouth))\b',
    r'\b(?:go\s+(?:fuck|screw|shove)\s+yourself)\b',

    # ----------------------------------------------------------------
    # Harassment / degrading language
    # ----------------------------------------------------------------
    r'\b(?:you\'?re\s+(?:a\s+)?(?:slut|whore|hoe|skank|tramp))\b',
    r'\b(?:stupid|dumb|idiot|moron|imbecile|loser|pathetic)\s+(?:bitch|ass|fuck|cunt|bastard)\b',
    r'\b(?:nobody\s+(?:likes?|loves?|cares?\s+about)\s+you)\b',
    r'\b(?:you\s+(?:deserve\s+to\s+(?:die|suffer|be\s+hurt)|should\s+(?:die|kill\s+yourself)))\b',
])


# Compile all patterns into main dictionary
PATTERNS: Dict[str, List[Pattern]] = {
    "parent_monitoring":     PARENT_MONITORING_PATTERNS,
    "secrecy":               SECRECY_PATTERNS,
    "trust_building":        TRUST_BUILDING_PATTERNS,
    "relationship_building": RELATIONSHIP_BUILDING_PATTERNS,
    "manipulation":          MANIPULATION_PATTERNS,
    "video_call":            VIDEO_CALL_PATTERNS,
    "meeting":               MEETING_PATTERNS,
    "address":               ADDRESS_PATTERNS,
    "school":                SCHOOL_PATTERNS,
    "routine":               ROUTINE_PATTERNS,
    "explicit_content":      EXPLICIT_CONTENT_PATTERNS,
    "bad_language":          BAD_LANGUAGE_PATTERNS,
}


def match_patterns(text: str, category: str = None) -> Dict[str, Any]:
    """
    Match text against pattern categories.
    
    Args:
        text: Input text to analyze
        category: Specific category to check (optional, checks all if None)
    
    Returns:
        Dictionary with matches, confidence scores, and metadata
    """
    results = {
        "matches": {},
        "total_matches": 0,
        "highest_confidence": 0.0,
        "categories_detected": []
    }
    
    categories_to_check = [category] if category else PATTERNS.keys()
    
    for cat in categories_to_check:
        if cat not in PATTERNS:
            continue
            
        patterns = PATTERNS[cat]
        matches = []
        
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                matches.append({
                    "text": match.group(0),
                    "start": match.start(),
                    "end": match.end(),
                    "pattern": pattern.pattern
                })
        
        if matches:
            confidence = PATTERN_CONFIDENCE.get(cat, 0.5)
            metadata = CATEGORY_METADATA.get(cat)
            
            results["matches"][cat] = {
                "count": len(matches),
                "confidence": confidence,
                "severity": metadata.severity if metadata else "unknown",
                "weight": metadata.weight if metadata else 0.5,
                "matched_patterns": matches
            }
            results["total_matches"] += len(matches)
            results["categories_detected"].append(cat)
            
            if confidence > results["highest_confidence"]:
                results["highest_confidence"] = confidence
    
    return results


def get_category_info(category: str) -> Dict[str, Any]:
    """Get metadata information for a specific category."""
    if category not in CATEGORY_METADATA:
        return None
    
    metadata = CATEGORY_METADATA[category]
    return {
        "name": metadata.name,
        "description": metadata.description,
        "severity": metadata.severity,
        "weight": metadata.weight,
        "confidence": PATTERN_CONFIDENCE.get(category, 0.5),
        "pattern_count": len(PATTERNS.get(category, []))
    }


def get_all_categories() -> List[str]:
    """Get list of all available pattern categories."""
    return list(PATTERNS.keys())


# Export main components
__all__ = [
    'PATTERNS',
    'PATTERN_CONFIDENCE',
    'CATEGORY_METADATA',
    'match_patterns',
    'get_category_info',
    'get_all_categories'
]
