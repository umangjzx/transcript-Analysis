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
    "personal_information": PatternCategory(
        name="Personal Information",
        description="Requests for or disclosure of personal identifiers such as phone numbers, email addresses, social media handles, age, real name, or other PII",
        severity="high",
        weight=0.85
    ),
    "gift_bribery": PatternCategory(
        name="Gift / Bribery",
        description="Offers of gifts, money, game items, or other incentives to gain compliance or trust",
        severity="high",
        weight=0.80
    ),
    "isolation": PatternCategory(
        name="Isolation",
        description="Attempts to isolate the child from friends, family, or support networks",
        severity="critical",
        weight=0.90
    ),
    "desensitization": PatternCategory(
        name="Desensitization / Normalizing",
        description="Attempts to normalize inappropriate behaviour or make the child feel it is acceptable",
        severity="high",
        weight=0.85
    ),
    "emotional_exploitation": PatternCategory(
        name="Emotional Exploitation",
        description="Using emotional dependency, guilt, or self-harm threats to control the child",
        severity="critical",
        weight=0.95
    ),
    "threats_coercion": PatternCategory(
        name="Threats / Coercion",
        description="Explicit threats, blackmail, or coercive language to force compliance",
        severity="critical",
        weight=1.0
    ),
    "gaming_luring": PatternCategory(
        name="Gaming / Platform Luring",
        description="Using online games or platforms to initiate contact or move to private channels",
        severity="high",
        weight=0.75
    ),
    "age_deception": PatternCategory(
        name="Age Deception",
        description="Misrepresenting age or minimising age differences to appear non-threatening",
        severity="high",
        weight=0.85
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
    "personal_information":  0.90,
    "gift_bribery":          0.85,
    "isolation":             0.88,
    "desensitization":       0.82,
    "emotional_exploitation": 0.90,
    "threats_coercion":      0.95,
    "gaming_luring":         0.78,
    "age_deception":         0.85,
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


# ---------------------------------------------------------------------------
# Gift / Bribery Patterns
# Covers: offers of gifts, money, game currency, items, or other incentives
# used to gain trust, compliance, or reciprocal behaviour from a child.
# ---------------------------------------------------------------------------
GIFT_BRIBERY_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Direct gift/present offers
    # ----------------------------------------------------------------
    r'\bI\'?(?:ll|will|can|could|want\s+to)\s+(?:buy|get|send|give|bring|purchase)\s+(?:you|u)\s+(?:a\s+)?(?:gift|present|surprise|treat|reward)\b',
    r'\bI\'?(?:ll|will|can|could)\s+(?:buy|get|send|give)\s+(?:you|u)\s+(?:anything|whatever\s+you\s+want|something\s+nice|something\s+special)\b',
    r'\b(?:want|wanna|would\s+like)\s+to\s+(?:send|give|buy|get)\s+(?:you|u)\s+(?:a\s+)?(?:gift|present|surprise|treat)\b',
    r'\bI\s+(?:have|got)\s+(?:a\s+)?(?:gift|present|surprise|treat)\s+for\s+(?:you|u)\b',

    # ----------------------------------------------------------------
    # Money / financial offers
    # ----------------------------------------------------------------
    r'\bI\'?(?:ll|will|can|could)\s+(?:give|send|pay|transfer)\s+(?:you|u)\s+(?:money|cash|funds|dollars?|pounds?|euros?|rupees?)\b',
    r'\bI\'?(?:ll|will)\s+pay\s+(?:you|u|for\s+it|for\s+that)\b',
    r'\b(?:here\'?s|take)\s+(?:some\s+)?(?:money|cash)\b',
    r'\bI\'?(?:ll|will|can)\s+(?:send|transfer)\s+(?:you|u)\s+(?:money|cash|funds)\b',

    # ----------------------------------------------------------------
    # Gift cards / vouchers
    # ----------------------------------------------------------------
    r'\bI\'?(?:ll|will|can|could)\s+(?:send|give|buy|get)\s+(?:you|u)\s+(?:a\s+)?(?:gift\s+card|voucher|coupon|promo\s+code|discount\s+code)\b',
    r'\b(?:gift\s+card|amazon\s+card|itunes\s+card|google\s+play\s+card|steam\s+card|roblox\s+card)\s+for\s+(?:you|u)\b',
    r'\b(?:can|could|I\'?(?:ll|will))\s+(?:send|get)\s+(?:you|u)\s+(?:a\s+)?(?:gift\s+card|voucher|code)\b',

    # ----------------------------------------------------------------
    # Gaming currency / in-game items
    # ----------------------------------------------------------------
    r'\bI\'?(?:ll|will|can|could)\s+(?:give|send|buy|get)\s+(?:you|u)\s+(?:robux|v-bucks|vbucks|gems?|coins?|credits?|skins?|items?|loot)\b',
    r'\b(?:free\s+)?(?:robux|v-bucks|vbucks|gems?|coins?|credits?)\s+for\s+(?:you|u)\b',
    r'\bI\'?(?:ll|will|can)\s+(?:buy|get)\s+(?:you|u)\s+(?:that\s+)?(?:game|skin|item|weapon|character|pass|membership|subscription)\b',

    # ----------------------------------------------------------------
    # Specific desirable items
    # ----------------------------------------------------------------
    r'\bI\'?(?:ll|will|can|could)\s+(?:buy|get)\s+(?:you|u)\s+(?:a\s+)?(?:phone|iphone|laptop|tablet|console|playstation|xbox|nintendo|airpods|headphones)\b',
    r'\bI\'?(?:ll|will|can)\s+(?:buy|get)\s+(?:you|u)\s+(?:whatever|anything)\s+(?:you\s+want|you\s+need|you\s+like)\b',
    r'\bI\'?(?:ll|will|can|could)\s+get\s+(?:you|u)\s+(?:that|the)\s+(?:phone|game|item|thing)\s+(?:you\s+wanted|you\s+like)\b',

    # ----------------------------------------------------------------
    # Conditional / transactional framing
    # ----------------------------------------------------------------
    r'\bif\s+you\s+(?:do\s+this|send\s+me|share|help\s+me|be\s+nice)\s+I\'?(?:ll|will)\s+(?:give|buy|send|pay|get)\b',
    r'\bI\'?(?:ll|will)\s+(?:give|buy|send|pay|get)\s+(?:you|u)\s+.{0,30}\s+if\s+you\b',
    r'\b(?:as\s+a\s+)?(?:reward|payment|thank\s+you\s+gift|bonus)\s+for\s+(?:you|u|doing\s+this|being\s+good)\b',
    r'\bI\s+(?:want\s+to|wanna)\s+(?:spoil|treat|reward)\s+(?:you|u)\b',
])

# ---------------------------------------------------------------------------
# Isolation Patterns
# Covers: attempts to separate the child from friends, family, or support
# networks; discrediting people in the child's life.
# ---------------------------------------------------------------------------
ISOLATION_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Discrediting friends
    # ----------------------------------------------------------------
    r'\byour\s+(?:friends?|mates?|classmates?|peers?)\s+(?:don\'?t|do\s+not|doesn\'?t|does\s+not)\s+(?:really\s+)?(?:care|like|love|understand|appreciate)\s+(?:you|u)\b',
    # "Your friends don't really care about you" — with "about"
    r'\byour\s+(?:friends?|mates?|classmates?|peers?)\s+(?:don\'?t|do\s+not|doesn\'?t|does\s+not)\s+(?:really\s+)?(?:care\s+about|care\s+for)\s+(?:you|u)\b',
    r'\byour\s+(?:friends?|mates?)\s+(?:are|were)\s+(?:just\s+)?(?:using|taking\s+advantage\s+of|manipulating|lying\s+to)\s+(?:you|u)\b',
    r'\b(?:those|your)\s+(?:friends?|mates?)\s+(?:are|aren\'?t)\s+(?:real|true|good|genuine)\s+(?:friends?|people)\b',
    r'\b(?:they|your\s+friends?)\s+(?:don\'?t|do\s+not)\s+(?:really\s+)?(?:care|understand|appreciate)\s+(?:you|u)\b',
    # "they are just using you" — bare form
    r'\b(?:they|your\s+(?:friends?|mates?))\s+(?:are|were)\s+(?:just\s+)?(?:using|using\s+you|taking\s+advantage)\b',
    r'\byou\s+(?:don\'?t|do\s+not)\s+need\s+(?:them|those\s+friends?|anyone\s+else)\b',
    r'\b(?:stay\s+away|keep\s+away|distance\s+yourself)\s+from\s+(?:them|your\s+friends?|those\s+people)\b',
    r'\b(?:those|your)\s+(?:friends?|people)\s+(?:are\s+)?(?:bad|toxic|fake|not\s+good)\s+(?:for\s+you|influences?)\b',

    # ----------------------------------------------------------------
    # Discrediting family
    # ----------------------------------------------------------------
    r'\byour\s+(?:family|parents?|mom|dad|mother|father)\s+(?:don\'?t|do\s+not|doesn\'?t|does\s+not)\s+(?:really\s+)?(?:care|love|understand|appreciate|support)\s+(?:you|u)\b',
    r'\byour\s+(?:family|parents?|mom|dad)\s+(?:don\'?t|do\s+not)\s+(?:deserve|get)\s+(?:you|u)\b',
    r'\byour\s+(?:family|parents?)\s+(?:are|were)\s+(?:holding\s+you\s+back|controlling\s+you|too\s+strict|toxic)\b',

    # ----------------------------------------------------------------
    # "You only need me"
    # ----------------------------------------------------------------
    r'\byou\s+(?:only\s+)?(?:have|need)\s+me\b',
    r'\bI\'?m\s+(?:all\s+you\s+need|the\s+only\s+one\s+(?:who\s+)?(?:cares?|loves?|understands?)\s+(?:you|u))\b',
    # "I'm the only one who truly cares" — bare form
    r'\bI\'?m\s+the\s+only\s+one\s+(?:who\s+)?(?:truly\s+|really\s+)?(?:cares?|loves?|understands?|gets?\s+(?:you|u))\b',
    r'\byou\s+(?:don\'?t|do\s+not)\s+need\s+(?:anyone|anybody)\s+(?:else|but\s+me)\b',
    r'\bI\'?m\s+(?:here|always\s+here)\s+(?:for\s+you|when\s+they\'?re\s+not)\b',
    r'\b(?:they|everyone\s+else)\s+(?:will\s+)?(?:leave|abandon|hurt|betray)\s+(?:you|u)\b',

    # ----------------------------------------------------------------
    # Encouraging withdrawal
    # ----------------------------------------------------------------
    r'\b(?:stop\s+talking|don\'?t\s+talk)\s+to\s+(?:them|your\s+friends?|those\s+people)\b',
    r'\b(?:ignore|avoid|cut\s+off|block)\s+(?:them|your\s+friends?|those\s+people|everyone\s+else)\b',
    r'\byou\s+(?:should|need\s+to)\s+(?:focus\s+on|spend\s+time\s+with)\s+(?:me|us)\s+(?:instead|more)\b',
])

# ---------------------------------------------------------------------------
# Desensitization / Normalizing Patterns
# Covers: attempts to make inappropriate behaviour seem normal, acceptable,
# or common — a key grooming tactic before escalation.
# ---------------------------------------------------------------------------
DESENSITIZATION_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # "It's normal / natural"
    # ----------------------------------------------------------------
    r'\bit\'?s\s+(?:totally|completely|perfectly|absolutely|quite|very)?\s*(?:normal|natural|okay|ok|fine|common|acceptable|harmless)\s+(?:to|for)\b',
    r'\bthis\s+is\s+(?:totally|completely|perfectly|absolutely|quite)?\s*(?:normal|natural|okay|ok|fine|common|acceptable|harmless)\b',
    r'\b(?:nothing|not)\s+(?:wrong|bad|weird|strange|unusual|inappropriate)\s+(?:with|about)\s+(?:this|it|that|doing\s+this)\b',
    r'\bthere\'?s\s+nothing\s+(?:wrong|bad|weird|strange|unusual)\s+(?:with|about)\s+(?:this|it|that)\b',

    # ----------------------------------------------------------------
    # "Everyone does it"
    # ----------------------------------------------------------------
    r'\b(?:everyone|everybody|all\s+(?:kids?|teens?|people|boys?|girls?))\s+(?:does?|is\s+doing|has\s+done|talks?\s+about)\s+(?:this|it|these\s+things?)\b',
    r'\b(?:lots\s+of|many|most)\s+(?:kids?|teens?|people|boys?|girls?)\s+(?:your\s+age\s+)?(?:do|does|have\s+done|talk\s+about)\s+(?:this|it)\b',
    r'\bkids?\s+(?:your\s+age\s+)?(?:do|does|are\s+doing)\s+(?:this|it)\s+all\s+the\s+time\b',

    # ----------------------------------------------------------------
    # "It's not a big deal"
    # ----------------------------------------------------------------
    r'\bit\'?s\s+(?:not\s+a\s+big\s+deal|no\s+big\s+deal|just\s+a\s+(?:joke|game|bit\s+of\s+fun|laugh))\b',
    r'\b(?:don\'?t|do\s+not)\s+(?:be|get)\s+(?:embarrassed|shy|scared|worried|upset|weird)\s+(?:about\s+(?:this|it))?\b',
    # "Don't be embarrassed, it's natural" — bare form
    r'\b(?:don\'?t|do\s+not)\s+(?:be|feel)\s+(?:embarrassed|ashamed|shy)\b',
    r'\b(?:don\'?t|do\s+not)\s+(?:overthink|worry\s+about|stress\s+about)\s+(?:this|it)\b',
    r'\brelax\b.{0,20}\b(?:it\'?s\s+fine|it\'?s\s+okay|no\s+big\s+deal)\b',

    # ----------------------------------------------------------------
    # "This is what friends do"
    # ----------------------------------------------------------------
    r'\bthis\s+is\s+(?:what|how)\s+(?:friends?|people|we|couples?)\s+(?:do|talk|act|behave|communicate)\b',
    r'\b(?:friends?|people\s+who\s+care)\s+(?:do|share|talk\s+about)\s+(?:this|these\s+things?|stuff\s+like\s+this)\b',
    r'\bwe\'?re\s+(?:just\s+)?(?:friends?|having\s+fun|playing|joking|messing\s+around)\b',

    # ----------------------------------------------------------------
    # Minimising / dismissing concern
    # ----------------------------------------------------------------
    r'\byou\'?re\s+(?:overreacting|being\s+dramatic|too\s+sensitive|making\s+a\s+big\s+deal)\b',
    r'\b(?:calm\s+down|chill\s+out|relax)\s*,?\s*(?:it\'?s\s+(?:fine|okay|nothing|just\s+a\s+joke))?\b',
    r'\bI\s+(?:was\s+)?(?:just|only)\s+(?:joking|kidding|messing\s+around|playing|having\s+fun)\b',
    r'\b(?:it\'?s\s+)?(?:just\s+a\s+)?(?:joke|game|bit\s+of\s+fun|laugh|banter)\b',
])

# ---------------------------------------------------------------------------
# Emotional Exploitation Patterns
# Covers: emotional dependency, guilt-tripping, self-harm threats, and
# using the child's empathy to maintain control.
# ---------------------------------------------------------------------------
EMOTIONAL_EXPLOITATION_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Emotional dependency / "you're all I have"
    # ----------------------------------------------------------------
    r'\byou\'?re\s+(?:all\s+I\s+have|the\s+only\s+(?:one|person|thing)\s+(?:I\s+have|that\s+matters|in\s+my\s+life))\b',
    r'\bI\s+(?:have|got)\s+(?:nobody|no\s+one|nothing)\s+(?:else|but\s+you)\b',
    r'\bwithout\s+(?:you|u)\s+I\s+(?:have|got)\s+(?:nothing|nobody|no\s+one)\b',
    r'\byou\'?re\s+(?:my\s+)?(?:everything|the\s+only\s+reason\s+I\'?m\s+(?:okay|happy|alive|going))\b',

    # ----------------------------------------------------------------
    # Guilt-tripping about leaving / stopping contact
    # ----------------------------------------------------------------
    r'\bI\s+(?:would\s+be|will\s+be|am|\'m)\s+(?:so\s+)?(?:sad|devastated|heartbroken|destroyed|lost|broken)\s+(?:if\s+you|without\s+you)\b',
    # "I'll be devastated if you go" — bare form
    r'\bI\'?(?:ll|will|would)\s+be\s+(?:so\s+)?(?:devastated|heartbroken|destroyed|crushed|lost|broken)\s+if\s+you\b',
    r'\bif\s+you\s+(?:leave|go|stop\s+talking|block|ignore)\s+(?:me|us)\s+I\s+(?:will|would|might|could)\b',
    r'\bdon\'?t\s+(?:leave|go|stop\s+talking\s+to\s+me|block\s+me|ignore\s+me)\b',
    r'\bplease\s+don\'?t\s+(?:leave|go|stop|block|ignore)\s+(?:me|us)\b',
    r'\byou\'?re\s+(?:the\s+only\s+reason\s+I\'?m\s+(?:okay|happy|still\s+here|alive))\b',
    r'\bI\s+(?:need|can\'?t\s+live\s+without)\s+(?:you|u)\b',

    # ----------------------------------------------------------------
    # Self-harm / suicide threats as manipulation
    # ----------------------------------------------------------------
    r'\bI\s+(?:might|will|could|would)\s+(?:hurt|harm|kill)\s+myself\s+if\s+(?:you|u)\b',
    r'\bI\'?(?:ll|will)\s+(?:hurt|harm|kill)\s+myself\s+(?:if\s+you|without\s+you)\b',
    r'\bI\s+(?:don\'?t\s+want\s+to\s+(?:live|be\s+here)|want\s+to\s+die)\s+(?:if\s+you|without\s+you)\b',
    r'\bif\s+you\s+(?:leave|go|stop)\s+I\s+(?:don\'?t\s+know\s+what\s+I\'?(?:ll|will)\s+do|might\s+do\s+something\s+stupid)\b',

    # ----------------------------------------------------------------
    # Emotional blackmail / guilt
    # ----------------------------------------------------------------
    r'\bafter\s+everything\s+I\'?(?:ve|have)\s+(?:done|given|shared)\s+for\s+(?:you|u)\b',
    r'\bI\s+(?:thought|expected)\s+(?:you|u)\s+(?:cared|loved\s+me|were\s+my\s+friend)\b',
    r'\byou\'?re\s+(?:breaking|hurting|destroying)\s+my\s+(?:heart|feelings?)\b',
    r'\bhow\s+could\s+you\s+(?:do\s+this|say\s+that|treat\s+me\s+like\s+this)\b',
    r'\bI\s+(?:gave|shared|did)\s+(?:so\s+much|everything)\s+for\s+(?:you|u)\s+and\s+(?:this|now)\b',
])

# ---------------------------------------------------------------------------
# Threats / Coercion Patterns
# Covers: explicit threats, blackmail, intimidation, and coercive language
# used to force compliance or silence.
# ---------------------------------------------------------------------------
THREATS_COERCION_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Blackmail — sharing content / information
    # ----------------------------------------------------------------
    r'\bI\'?(?:ll|will)\s+(?:share|send|post|upload|show|tell|expose|leak)\s+(?:those|your|the)\s+(?:photos?|pictures?|pics?|videos?|messages?|screenshots?|chats?)\b',
    r'\bI\'?(?:ll|will)\s+(?:tell|show|inform)\s+(?:everyone|your\s+(?:parents?|friends?|school|teacher))\s+(?:about|what)\b',
    r'\bI\s+(?:have|got|saved)\s+(?:your\s+)?(?:photos?|pictures?|pics?|videos?|screenshots?|messages?)\s+and\s+I\'?(?:ll|will)\b',
    r'\bif\s+you\s+(?:don\'?t|do\s+not|refuse|stop)\s+.{0,40}\s+I\'?(?:ll|will)\s+(?:share|post|tell|show|expose|leak)\b',

    # ----------------------------------------------------------------
    # Direct threats
    # ----------------------------------------------------------------
    r'\byou\'?(?:d|will)\s+(?:better|regret\s+(?:this|it)|be\s+sorry)\b',
    r'\bdon\'?t\s+(?:make\s+me|force\s+me|push\s+me)\b',
    r'\byou\'?ll\s+regret\s+(?:this|it|not\s+doing\s+this)\b',
    r'\bI\s+(?:know|found\s+out)\s+where\s+you\s+(?:live|go\s+to\s+school|hang\s+out)\b',
    r'\bI\s+can\s+(?:find|track|locate)\s+(?:you|u)\b',
    r'\bwatch\s+(?:yourself|your\s+back)\b',

    # ----------------------------------------------------------------
    # Reputation threats
    # ----------------------------------------------------------------
    r'\bI\'?(?:ll|will)\s+(?:ruin|destroy|damage)\s+(?:your|ur)\s+(?:reputation|life|friendships?|relationships?)\b',
    r'\bI\'?(?:ll|will)\s+(?:make\s+sure\s+)?(?:everyone|your\s+(?:friends?|school|parents?))\s+(?:knows?|finds?\s+out|hears?)\b',
    r'\bI\'?(?:ll|will)\s+(?:spread|tell)\s+(?:rumors?|lies?|stories?)\s+about\s+(?:you|u)\b',

    # ----------------------------------------------------------------
    # Compliance demands
    # ----------------------------------------------------------------
    r'\byou\s+(?:have\s+to|must|need\s+to|better)\s+(?:do\s+(?:this|it|what\s+I\s+say)|send|share|comply)\b',
    r'\bdo\s+(?:it|this|what\s+I\s+say)\s+or\s+(?:else|I\'?(?:ll|will))\b',
    r'\bno\s+(?:choice|option|way\s+out)\b',
    r'\byou\s+(?:can\'?t|cannot)\s+(?:say\s+no|refuse|stop\s+me|escape)\b',
])

# ---------------------------------------------------------------------------
# Gaming / Platform Luring Patterns
# Covers: using online games, gaming platforms, or social apps to initiate
# contact, build rapport, or move to private/unmonitored channels.
# ---------------------------------------------------------------------------
GAMING_LURING_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Gaming platform contact requests
    # ----------------------------------------------------------------
    r'\b(?:add|friend|follow)\s+me\s+(?:on|in)\s+(?:roblox|fortnite|minecraft|among\s+us|valorant|apex|cod|call\s+of\s+duty|gta|pubg|league\s+of\s+legends|lol|overwatch|fifa|nba\s+2k|warzone)\b',
    r'\bwhat\'?s\s+(?:your|ur)\s+(?:roblox|fortnite|minecraft|steam|epic\s+games?|psn|xbox|gamertag|gamer\s+tag|gaming)\s+(?:username|user\s*name|id|name|handle|tag)?\b',
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna)\s+(?:play|game|game\s+together)\s+(?:on|in)?\s*(?:roblox|fortnite|minecraft|among\s+us|valorant|apex|cod|gta|pubg|overwatch)\b',
    # "Let's play together on Roblox" — bare form (play + platform)
    r'\b(?:let\'?s|can\s+we|want\s+to|wanna)\s+play\s+(?:together\s+)?(?:on\s+)?(?:roblox|fortnite|minecraft|among\s+us|valorant|apex|cod|gta|pubg|overwatch|a\s+game)\b',
    r'\b(?:join|come\s+to)\s+(?:my|our)\s+(?:server|game|lobby|world|realm|party|squad|team)\b',
    r'\b(?:private|secret)\s+(?:server|game|lobby|world|realm|channel)\b',

    # ----------------------------------------------------------------
    # Moving to private / unmonitored channels
    # ----------------------------------------------------------------
    r'\b(?:let\'?s|can\s+we|switch\s+to|move\s+to|talk\s+on|chat\s+on)\s+(?:discord|telegram|signal|whatsapp|kik|snapchat|instagram\s+dms?|twitter\s+dms?)\b',
    r'\b(?:switch|move|go)\s+(?:to|over\s+to)\s+(?:dms?|direct\s+messages?|private\s+messages?|pms?)\b',
    r'\b(?:let\'?s|can\s+we)\s+(?:talk|chat|message)\s+(?:somewhere\s+(?:else|more\s+private)|privately|in\s+private|on\s+another\s+app)\b',
    r'\b(?:this\s+app|here)\s+(?:isn\'?t|is\s+not)\s+(?:safe|private|secure|good)\s+(?:to\s+talk|for\s+us)\b',
    r'\b(?:they|people)\s+(?:can|could|might)\s+(?:see|read|monitor|track)\s+(?:this|our\s+messages?|what\s+we\s+say)\b',

    # ----------------------------------------------------------------
    # Gaming as a pretext for meeting
    # ----------------------------------------------------------------
    r'\bwe\s+(?:could|should|can)\s+(?:play|game)\s+(?:together|in\s+person|at\s+my\s+place|at\s+your\s+place)\b',
    r'\bI\'?(?:ll|will)\s+(?:teach|show|help)\s+(?:you|u)\s+(?:how\s+to\s+play|get\s+better|level\s+up|win)\b',
    r'\bcome\s+(?:over|to\s+my\s+place)\s+(?:and\s+we\s+can\s+)?(?:play|game|hang\s+out)\b',
])

# ---------------------------------------------------------------------------
# Age Deception Patterns
# Covers: misrepresenting age, minimising age gaps, or using age-related
# language to appear non-threatening or peer-like.
# ---------------------------------------------------------------------------
AGE_DECEPTION_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Claiming to be the same age / young
    # ----------------------------------------------------------------
    r'\bI\'?m\s+(?:actually|also|only|just)\s+\d{1,2}\b',
    r'\bI\'?m\s+(?:the\s+same\s+age|your\s+age|close\s+to\s+your\s+age)\b',
    r'\bI\'?m\s+(?:only\s+)?(?:a\s+few\s+years?|not\s+much)\s+older\s+than\s+(?:you|u)\b',
    r'\bdon\'?t\s+worry\s+I\'?m\s+(?:young|not\s+that\s+old|close\s+to\s+your\s+age)\b',
    r'\bwe\'?re\s+(?:basically|almost|practically)\s+the\s+same\s+age\b',
    r'\bI\s+(?:look|seem|act)\s+(?:young|younger\s+than\s+I\s+am|your\s+age)\b',

    # ----------------------------------------------------------------
    # Minimising age gap / "age doesn't matter"
    # ----------------------------------------------------------------
    r'\bage\s+(?:is\s+just\s+a\s+number|doesn\'?t\s+matter|shouldn\'?t\s+matter|isn\'?t\s+important)\b',
    r'\b(?:age\s+gap|age\s+difference)\s+(?:doesn\'?t|don\'?t|shouldn\'?t)\s+(?:matter|bother|stop\s+us)\b',
    r'\bwhat\s+(?:does|do)\s+(?:age|numbers?)\s+(?:matter|have\s+to\s+do\s+with\s+(?:it|this|us))\b',
    r'\b(?:it\'?s\s+)?(?:just\s+a\s+number|only\s+a\s+number)\b',

    # ----------------------------------------------------------------
    # Flattering maturity to lower guard
    # ----------------------------------------------------------------
    r'\byou\'?re\s+(?:so\s+)?(?:mature|grown\s+up|wise|smart)\s+for\s+(?:your\s+age|someone\s+your\s+age)\b',
    r'\byou\s+(?:seem|act|sound|look)\s+(?:so\s+)?(?:mature|older|grown\s+up)\s+(?:for\s+your\s+age|than\s+you\s+are)\b',
    r'\byou\'?re\s+(?:not\s+like\s+other\s+kids?|more\s+mature\s+than\s+most)\b',
    r'\byou\s+(?:think|talk|act)\s+like\s+(?:an\s+adult|someone\s+much\s+older)\b',

    # ----------------------------------------------------------------
    # Asking about / probing age
    # ----------------------------------------------------------------
    r'\b(?:does\s+(?:age|it)\s+matter\s+to\s+you|do\s+you\s+care\s+about\s+(?:age|how\s+old\s+I\s+am))\b',
    r'\bwould\s+(?:you|u)\s+(?:still\s+)?(?:talk|chat|be\s+friends?|like\s+me)\s+if\s+I\s+(?:was|were|am)\s+older\b',
    r'\bdoes\s+(?:my\s+age|how\s+old\s+I\s+am)\s+(?:bother|matter|change\s+things?)\b',
])

# ---------------------------------------------------------------------------
# Personal Information (PII) Patterns
# Covers: phone numbers, email addresses, social media handles/usernames,
# real names, age/date-of-birth, and other personal identifiers.
# ---------------------------------------------------------------------------
PERSONAL_INFORMATION_PATTERNS = compile_patterns([
    # ----------------------------------------------------------------
    # Phone number — requests
    # ----------------------------------------------------------------
    r'\b(?:what\'?s|give\s+me|send\s+me|share|tell\s+me)\s+(?:your|ur)\s+(?:phone|cell|mobile|contact)\s+(?:number|num|no\.?|#)\b',
    r'\b(?:your|ur)\s+(?:phone|cell|mobile|contact)\s+(?:number|num|no\.?|#)\b',
    r'\bwhat\'?s\s+(?:your|ur)\s+(?:number|num|no\.?)\b',
    r'\b(?:can\s+I|could\s+I|may\s+I)\s+(?:have|get)\s+(?:your|ur)\s+(?:number|phone|cell|mobile)\b',
    r'\b(?:give|send|share|drop)\s+(?:me\s+)?(?:your|ur)\s+(?:number|digits|phone|cell|mobile)\b',
    r'\b(?:text|call|ring|WhatsApp|whatsapp|telegram|signal)\s+me\s+(?:on|at)?\s*(?:your|ur)?\s*(?:number|phone)?\b',
    r'\b(?:text|call|ring)\s+me\b',
    r'\bmy\s+(?:number|phone|cell|mobile)\s+is\b',

    # ----------------------------------------------------------------
    # Phone number — actual number patterns (spoken/typed)
    # ----------------------------------------------------------------
    # International format: +1 (555) 123-4567 / +44 7911 123456
    r'\+\d{1,3}[\s\-.]?\(?\d{1,4}\)?[\s\-.]?\d{3,5}[\s\-.]?\d{3,5}',
    # US/CA: (555) 123-4567 or 555-123-4567 or 555.123.4567
    r'\(?\d{3}\)?[\s\-.]?\d{3}[\s\-.]?\d{4}\b',
    # Compact 10-digit: 5551234567
    r'\b\d{10}\b',
    # Spoken-style: "my number is 9876543210"
    r'\b(?:number|phone|cell|mobile)\s+(?:is|:)\s*[\d\s\-\.\(\)]{7,15}\b',

    # ----------------------------------------------------------------
    # Email address — requests
    # ----------------------------------------------------------------
    r'\b(?:what\'?s|give\s+me|send\s+me|share|tell\s+me)\s+(?:your|ur)\s+(?:email|e-mail|mail|gmail|yahoo|hotmail|outlook)\b',
    r'\b(?:your|ur)\s+(?:email|e-mail|mail)\s+(?:address|id|account)?\b',
    r'\b(?:email|e-mail|mail)\s+me\b',
    r'\b(?:send|drop|share)\s+(?:me\s+)?(?:your|ur)\s+(?:email|e-mail|mail)\b',

    # ----------------------------------------------------------------
    # Email address — actual address pattern
    # ----------------------------------------------------------------
    r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b',

    # ----------------------------------------------------------------
    # Social media handles / usernames — requests
    # ----------------------------------------------------------------
    r'\b(?:what\'?s|give\s+me|send\s+me|share|tell\s+me)\s+(?:your|ur)\s+(?:instagram|insta|snapchat|snap|tiktok|twitter|facebook|fb|discord|telegram|whatsapp|kik|wechat|line|viber)\s*(?:handle|username|user\s*name|id|account|@|name)?\b',
    r'\b(?:your|ur)\s+(?:instagram|insta|snapchat|snap|tiktok|twitter|facebook|fb|discord|telegram|whatsapp|kik|wechat|line|viber)\s*(?:handle|username|user\s*name|id|account|@|name)?\b',
    r'\b(?:add|follow|dm|message|contact)\s+me\s+(?:on|at)\s+(?:instagram|insta|snapchat|snap|tiktok|twitter|facebook|fb|discord|telegram|whatsapp|kik|wechat|line|viber)\b',
    r'\b(?:find|search|look\s+up)\s+(?:me|you)\s+on\s+(?:instagram|insta|snapchat|snap|tiktok|twitter|facebook|fb|discord|telegram|whatsapp|kik|wechat|line|viber)\b',
    r'\b(?:my|your|ur)\s+(?:snap|insta|discord|kik|tiktok|twitter)\s+(?:is|:)\b',
    # "@username" handle pattern
    r'(?<!\w)@[A-Za-z0-9_\.]{2,30}\b',

    # ----------------------------------------------------------------
    # Real name — requests
    # ----------------------------------------------------------------
    r'\bwhat\'?s\s+(?:your|ur)\s+(?:real|full|actual|last|first|given|family|surname)\s+name\b',
    r'\b(?:tell\s+me|give\s+me|share)\s+(?:your|ur)\s+(?:real|full|actual|last|first|given|family|surname)\s+name\b',
    r'\bwhat\'?s\s+(?:your|ur)\s+(?:real\s+name|full\s+name|last\s+name|surname|family\s+name)\b',
    r'\b(?:real|full|actual)\s+name\b',

    # ----------------------------------------------------------------
    # Age / date of birth — requests
    # ----------------------------------------------------------------
    r'\bhow\s+old\s+are\s+you\b',
    r'\bwhat\'?s\s+(?:your|ur)\s+age\b',
    r'\b(?:your|ur)\s+(?:age|dob|date\s+of\s+birth|birthday|birth\s+date)\b',
    r'\bwhen\s+(?:is|was)\s+(?:your|ur)\s+(?:birthday|birth\s+date|dob)\b',
    r'\bwhat\s+(?:year|month|day)\s+(?:were|was)\s+you\s+born\b',
    r'\b(?:are\s+you|you\'?re)\s+(?:\d{1,2}|under\s+\d{1,2}|over\s+\d{1,2})\s*(?:years?\s+old)?\b',
    r'\b(?:tell\s+me|share)\s+(?:your|ur)\s+(?:age|birthday|dob)\b',

    # ----------------------------------------------------------------
    # Password / PIN — requests (high-risk PII)
    # ----------------------------------------------------------------
    r'\b(?:what\'?s|give\s+me|send\s+me|share|tell\s+me)\s+(?:your|ur)\s+(?:password|passcode|pin|pass|login|credentials)\b',
    r'\b(?:your|ur)\s+(?:password|passcode|pin|pass|login|credentials)\b',

    # ----------------------------------------------------------------
    # ID numbers — national ID, SSN, passport
    # ----------------------------------------------------------------
    r'\b(?:social\s+security|ssn|national\s+id|passport|id\s+number|aadhar|aadhaar|pan\s+card)\s*(?:number|no\.?|#)?\b',
    r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',  # SSN pattern: 123-45-6789

    # ----------------------------------------------------------------
    # Personal photo / selfie requests (PII-adjacent)
    # ----------------------------------------------------------------
    r'\b(?:send|share|post|upload)\s+(?:me\s+)?(?:a\s+)?(?:selfie|photo\s+of\s+yourself|picture\s+of\s+yourself|pic\s+of\s+yourself|photo\s+of\s+your\s+face|pic\s+of\s+your\s+face)\b',
    r'\bwhat\s+do\s+you\s+look\s+like\b',
    r'\b(?:show|send)\s+(?:me\s+)?(?:your|ur)\s+(?:face|photo|pic|picture|selfie)\b',
])


# Compile all patterns into main dictionary
PATTERNS: Dict[str, List[Pattern]] = {    "parent_monitoring":     PARENT_MONITORING_PATTERNS,
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
    "personal_information":  PERSONAL_INFORMATION_PATTERNS,
    "gift_bribery":          GIFT_BRIBERY_PATTERNS,
    "isolation":             ISOLATION_PATTERNS,
    "desensitization":       DESENSITIZATION_PATTERNS,
    "emotional_exploitation": EMOTIONAL_EXPLOITATION_PATTERNS,
    "threats_coercion":      THREATS_COERCION_PATTERNS,
    "gaming_luring":         GAMING_LURING_PATTERNS,
    "age_deception":         AGE_DECEPTION_PATTERNS,
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
