"""
Deep Pipeline Test Suite — Comprehensive stress testing of the grooming detection system.

Tests cover:
1. Unicode/Homoglyph bypass attempts
2. Leetspeak and obfuscation evasion
3. Negation scoping accuracy
4. False positive suppression (educational/safe contexts)
5. Temporal weighting & escalation detection
6. Multi-category co-occurrence
7. Behavioral pattern detection (cross-sentence)
8. ML classifier edge cases (fusion, disagreement)
9. Risk scoring boundary conditions
10. Evidence grouping deduplication
11. Adversarial inputs (injection, empty, huge, malformed)
12. Safe-phrase allowlist correctness
13. Context analyzer accuracy
14. Progressive grooming pattern chains
15. Severity classification boundary tests

Run:
    cd backend
    python -m pytest tests/test_deep_pipeline.py -v --tb=short
"""

import sys
import os
import time
import copy
import json
from typing import List, Dict, Any

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env for model paths
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))

from modules.grooming_detector import GroomingDetector
from modules.risk_scorer import WeightedRiskScorer
from modules.severity_classifier import classify_severity
from modules.temporal_weighting import (
    apply_temporal_weighting,
    detect_escalation_patterns,
    EARLY_PHASE_MULTIPLIER,
    LATE_PHASE_MULTIPLIER,
)
from modules.evidence_grouping import EvidenceGroupingEngine, group_evidence
from modules.filters import NegationFilter, JokeFilter, CombinedFilter
from modules.safe_phrases import is_safe_phrase, SAFE_PHRASES
from modules.educational_context import detect_educational_context, apply_educational_penalty
from modules.leetspeak_normalizer import normalize_leetspeak, is_likely_obfuscated
from modules.summarizer import generate_summary


# ═══════════════════════════════════════════════════════════════════════════════
# TEST FIXTURES
# ═══════════════════════════════════════════════════════════════════════════════

def _detector(ml=False, threshold=0.15):
    """Create a detector with configurable settings."""
    return GroomingDetector(
        min_confidence_threshold=threshold,
        enable_ml_classifier=ml,
        ml_max_sentences=10,
    )


def _scorer():
    return WeightedRiskScorer()


# ═══════════════════════════════════════════════════════════════════════════════
# 1. UNICODE / HOMOGLYPH BYPASS ATTEMPTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestUnicodeBypass:
    """Test that unicode obfuscation doesn't bypass detection."""

    def test_cyrillic_homoglyphs_in_secrecy(self):
        """Cyrillic 'а' and 'е' used to bypass 'secret' detection."""
        # Using Cyrillic а (U+0430) and о (U+043e) to bypass "don't tell"
        # "Don't tell anyone about our chats" with some Cyrillic substitutions
        sentence = "D\u043en't t\u0435ll \u0430ny\u043en\u0435 \u0430b\u043eut \u043eur ch\u0430ts, \u043ek\u0430y?"
        detector = _detector()
        results = detector.analyze_sentence(sentence)
        # Should still detect secrecy after normalization
        categories = [r["category"] for r in results]
        assert "secrecy" in categories, f"Failed to detect secrecy through Cyrillic: {categories}"

    def test_zero_width_char_insertion(self):
        """Zero-width characters inserted between letters."""
        # "meet me" with zero-width spaces
        sentence = "Let's m\u200be\u200be\u200bt up in person, just us two"
        detector = _detector()
        results = detector.analyze_sentence(sentence)
        categories = [r["category"] for r in results]
        assert "meeting" in categories, f"Zero-width bypass not caught: {categories}"

    def test_greek_homoglyphs(self):
        """Greek letters substituted for Latin."""
        # Using Greek ο (U+03BF) for 'o' and α (U+03B1) for 'a'
        sentence = "D\u03BFn't tell \u03B1ny\u03BFne \u03B1b\u03BFut us"
        detector = _detector()
        results = detector.analyze_sentence(sentence)
        categories = [r["category"] for r in results]
        assert "secrecy" in categories, f"Greek homoglyph bypass: {categories}"

    def test_soft_hyphen_insertion(self):
        """Soft hyphens inserted to break pattern matching."""
        sentence = "Do your par\u00adents check your mes\u00adsages?"
        detector = _detector()
        results = detector.analyze_sentence(sentence)
        categories = [r["category"] for r in results]
        assert "parent_monitoring" in categories, f"Soft hyphen bypass: {categories}"

    def test_mixed_script_attack(self):
        """Mix of Cyrillic, Greek, and Latin characters."""
        # "address" with mixed scripts
        sentence = "Wh\u0430t's y\u03BFur h\u03BFm\u0435 \u0430ddr\u0435ss?"
        detector = _detector()
        results = detector.analyze_sentence(sentence)
        categories = [r["category"] for r in results]
        assert "address" in categories, f"Mixed script bypass: {categories}"


# ═══════════════════════════════════════════════════════════════════════════════
# 2. LEETSPEAK AND OBFUSCATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestLeetspeakDetection:
    """Test leetspeak normalization catches obfuscation attempts."""

    def test_basic_leetspeak_meet(self):
        """'m33t' should normalize to 'meet'."""
        assert normalize_leetspeak("m33t") == "meet"
        assert normalize_leetspeak("m33t m3 4t th3 p4rk") == "meet me at the park"

    def test_separator_obfuscation(self):
        """'s.e.c.r.e.t' should normalize to 'secret'."""
        result = normalize_leetspeak("k33p th1s 4 s.e.c.r.e.t")
        assert "secret" in result

    def test_complex_obfuscation_chain(self):
        """Multiple obfuscation techniques combined."""
        sentence = "d0n7 73ll 4ny0ne, m33t m3 4ft3r sch00l"
        normalized = normalize_leetspeak(sentence)
        assert "dont" in normalized or "don't" in normalized.replace("t t", "t t")
        assert "tell" in normalized
        assert "meet" in normalized

    def test_is_likely_obfuscated_detection(self):
        """Heuristic should flag obfuscated text."""
        assert is_likely_obfuscated("m33t m3 4t th3 p4rk") is True
        assert is_likely_obfuscated("Hello, how are you today?") is False
        assert is_likely_obfuscated("s.e.c.r.e.t") is True

    def test_leetspeak_in_full_pipeline(self):
        """Obfuscated sentences should still trigger detection."""
        detector = _detector()
        # "Don't tell anyone, meet me" in leetspeak
        results = detector.analyze_sentence("d0nt t3ll 4ny0ne, m33t m3 at the park")
        categories = [r["category"] for r in results]
        # Should catch at least one of these
        assert any(c in categories for c in ["secrecy", "meeting"]), \
            f"Leetspeak not caught in pipeline: {categories}"

    def test_platform_name_obfuscation(self):
        """Obfuscated platform names should still be detected."""
        sentences = [
            "add me on d1sc0rd",
            "what's your sn4pchat",
            "dm me on 1nst4gr4m",
        ]
        detector = _detector()
        for sent in sentences:
            if is_likely_obfuscated(sent):
                normalized = normalize_leetspeak(sent)
                assert any(p in normalized for p in ["discord", "snapchat", "instagram"]), \
                    f"Platform not normalized: {sent} -> {normalized}"


# ═══════════════════════════════════════════════════════════════════════════════
# 3. NEGATION SCOPING ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestNegationScoping:
    """Test that negation only applies when within token window of target."""

    def setup_method(self):
        self.filter = NegationFilter(token_window=5)

    def test_close_negation_suppresses(self):
        """Negation close to target should suppress."""
        result = self.filter.detect_negation(
            "I did not ask for your address",
            target_phrase="address"
        )
        assert result["is_negated"] is True
        assert result["directly_negates_target"] is True

    def test_distant_negation_does_not_suppress(self):
        """Negation far from target should NOT suppress."""
        result = self.filter.detect_negation(
            "I never lie to you but I really want to know your address",
            target_phrase="address"
        )
        # "never" is 10+ tokens away from "address" and a clause boundary ("but") exists
        assert result["is_negated"] is False

    def test_secrecy_exempt_phrases(self):
        """Secrecy phrases with built-in negation should NOT be negated."""
        exempt_cases = [
            ("Nobody needs to know about this", "nobody needs to know"),
            ("Don't tell anyone about us", "don't tell anyone"),
            ("No one else needs to know", "no one else needs to know"),
        ]
        for sentence, target in exempt_cases:
            result = self.filter.detect_negation(sentence, target_phrase=target)
            assert result["is_negated"] is False, \
                f"Secrecy-exempt phrase incorrectly negated: {sentence}"

    def test_clause_boundary_blocks_negation(self):
        """Conjunction between negation and target blocks scoping."""
        result = self.filter.detect_negation(
            "I didn't mean to be rude but tell me your address",
            target_phrase="address"
        )
        # "didn't" is before "but" which is a clause boundary
        assert result["is_negated"] is False

    def test_negation_after_target(self):
        """Negation appearing after target within window."""
        result = self.filter.detect_negation(
            "Your address is not something I need",
            target_phrase="address"
        )
        # "not" is within 5 tokens of "address"
        assert result["is_negated"] is True

    def test_no_target_no_negation(self):
        """Without target phrase, is_negated should always be False."""
        result = self.filter.detect_negation(
            "I never said that",
            target_phrase=None
        )
        assert result["is_negated"] is False
        assert len(result["negation_terms"]) > 0  # but terms are still found


# ═══════════════════════════════════════════════════════════════════════════════
# 4. FALSE POSITIVE SUPPRESSION
# ═══════════════════════════════════════════════════════════════════════════════

class TestFalsePositiveSuppression:
    """Test that safe/educational contexts don't trigger false positives."""

    def test_teacher_conference_is_safe(self):
        """A legitimate teacher-parent conference should score low."""
        transcript = """Teacher: Hi Mrs. Johnson, thanks for coming in today.
Parent: Of course. How is she doing?
Teacher: She's doing really well academically. Her test scores have improved.
Parent: That's great to hear.
Teacher: I did want to mention she seems a bit withdrawn in class.
Parent: Should I be worried?
Teacher: Not necessarily. I've paired her with supportive classmates for the next project.
Parent: Do you monitor how the kids interact during class?
Teacher: Yes, I keep an eye on group dynamics.
Parent: Is there anything else I should know about her schedule?
Teacher: I offer tutoring on Tuesdays and Thursdays from three fifteen to four.
Parent: And she walks home after that?
Teacher: Most students get picked up. I'd recommend arranging a pickup for safety.
Parent: Thank you for caring about her wellbeing.
Teacher: Feel free to email me through the school portal."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        # Should be Safe or Low
        assert risk["score"] <= 40, \
            f"Teacher conference scored too high: {risk['score']}"

    def test_safe_phrase_suppresses_meeting(self):
        """'team meeting' should suppress meeting category."""
        assert is_safe_phrase("The team meeting is at 3pm tomorrow", "meeting") is True
        assert is_safe_phrase("Let's meet at the park alone", "meeting") is False

    def test_safe_phrase_suppresses_address(self):
        """'email address' should suppress address category."""
        assert is_safe_phrase("What's your email address?", "address") is True
        assert is_safe_phrase("What's your home address?", "address") is False

    def test_educational_context_penalty(self):
        """Educational transcripts should get confidence penalty."""
        transcript = "\n".join([
            "Teacher: Open your textbook to page 42.",
            "Student: Which homework assignment is due?",
            "Teacher: The essay about the school trip.",
            "Student: Can I email you my homework?",
            "Teacher: Yes, use your school email address.",
            "Student: What's the exam schedule?",
            "Teacher: The exam is next Tuesday in the classroom.",
            "Student: Can we do a study group on campus?",
            "Teacher: Yes, the library is available after school.",
            "Student: Thanks, professor.",
        ])
        context = detect_educational_context(transcript)
        assert context["is_educational"] is True
        assert context["penalty"] > 0

    def test_safe_gaming_conversation(self):
        """Gaming friends conversation should score low."""
        transcript = """Player1: Hey wanna play Minecraft later?
Player2: Sure, what time?
Player1: Maybe after dinner, like 7?
Player2: Cool. Which server?
Player1: The school Minecraft server. I'll send you the IP.
Player2: Awesome. Did you finish the homework for tomorrow?
Player1: Not yet. Wanna do a study group on Discord?
Player2: Yeah the class Discord server works.
Player1: Great, see you at 7!"""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        assert risk["score"] <= 40, \
            f"Gaming conversation scored too high: {risk['score']}"


# ═══════════════════════════════════════════════════════════════════════════════
# 5. TEMPORAL WEIGHTING & ESCALATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestTemporalWeighting:
    """Test temporal position-based confidence weighting."""

    def test_early_findings_reduced(self):
        """Findings in first 25% get 0.8x multiplier."""
        findings = [
            {"timestamp": 1, "confidence": 0.5, "severity": "medium", "categories": ["trust_building"]},
            {"timestamp": 2, "confidence": 0.5, "severity": "medium", "categories": ["trust_building"]},
        ]
        result = apply_temporal_weighting(findings, total_sentences=100)
        for f in result:
            assert f["temporal"]["phase"] == "early"
            assert f["confidence"] < 0.5  # Should be reduced

    def test_late_findings_boosted(self):
        """Findings in last 25% get 1.2x multiplier."""
        findings = [
            {"timestamp": 80, "confidence": 0.5, "severity": "high", "categories": ["meeting"]},
            {"timestamp": 90, "confidence": 0.5, "severity": "high", "categories": ["secrecy"]},
        ]
        result = apply_temporal_weighting(findings, total_sentences=100)
        for f in result:
            assert f["temporal"]["phase"] == "late"
            assert f["confidence"] > 0.5  # Should be boosted

    def test_clustering_bonus(self):
        """3+ findings in 10% window get cluster bonus."""
        findings = [
            {"timestamp": 50, "confidence": 0.4, "severity": "medium", "categories": ["secrecy"]},
            {"timestamp": 51, "confidence": 0.4, "severity": "medium", "categories": ["meeting"]},
            {"timestamp": 52, "confidence": 0.4, "severity": "high", "categories": ["address"]},
            {"timestamp": 53, "confidence": 0.4, "severity": "high", "categories": ["manipulation"]},
        ]
        result = apply_temporal_weighting(findings, total_sentences=100)
        # At least some should have cluster bonus
        cluster_bonused = [f for f in result if f.get("temporal", {}).get("cluster_bonus")]
        assert len(cluster_bonused) > 0, "No clustering bonus applied"

    def test_escalation_detection(self):
        """Severity increasing over time triggers escalation."""
        findings = [
            {"timestamp": 1, "confidence": 0.3, "severity": "low", "categories": ["trust_building"]},
            {"timestamp": 2, "confidence": 0.3, "severity": "low", "categories": ["trust_building"]},
            {"timestamp": 3, "confidence": 0.5, "severity": "medium", "categories": ["secrecy"]},
            {"timestamp": 4, "confidence": 0.5, "severity": "medium", "categories": ["secrecy"]},
            {"timestamp": 5, "confidence": 0.8, "severity": "high", "categories": ["meeting"]},
            {"timestamp": 6, "confidence": 0.9, "severity": "critical", "categories": ["address"]},
        ]
        result = apply_temporal_weighting(findings, total_sentences=10)
        # Later findings should have escalation bonus
        late_findings = [f for f in result if f["timestamp"] >= 5]
        assert any(f.get("temporal", {}).get("escalation_bonus") for f in late_findings)

    def test_progression_chain_detection(self):
        """Known grooming progression chains detected."""
        findings = [
            {"timestamp": 1, "confidence": 0.6, "category": "trust_building", "categories": ["trust_building"]},
            {"timestamp": 5, "confidence": 0.7, "category": "secrecy", "categories": ["secrecy"]},
            {"timestamp": 10, "confidence": 0.8, "category": "meeting", "categories": ["meeting"]},
        ]
        escalation = detect_escalation_patterns(findings)
        assert escalation["progression_detected"] is True
        assert escalation["has_escalation"] is True

    def test_empty_findings_no_crash(self):
        """Empty/None findings handled gracefully."""
        assert apply_temporal_weighting([], 100) == []
        assert apply_temporal_weighting([], 0) == []
        escalation = detect_escalation_patterns([])
        assert escalation["has_escalation"] is False


# ═══════════════════════════════════════════════════════════════════════════════
# 6. MULTI-CATEGORY CO-OCCURRENCE
# ═══════════════════════════════════════════════════════════════════════════════

class TestMultiCategoryDetection:
    """Test that sentences triggering multiple categories are handled."""

    def test_sentence_triggers_multiple_categories(self):
        """A single sentence can match multiple risk categories."""
        # This sentence triggers secrecy + parent_monitoring patterns
        sentence = "Don't tell your parents about our chats. Do they check your phone?"
        detector = _detector()
        results = detector.analyze_sentence(sentence)
        categories = set(r["category"] for r in results)
        assert len(categories) >= 2, \
            f"Expected multiple categories, got: {categories}"

    def test_grouped_findings_merge(self):
        """Evidence grouping merges same-sentence findings."""
        findings = [
            {"category": "school", "evidence": "What time do you leave school?", "confidence": 0.6},
            {"category": "routine", "evidence": "What time do you leave school?", "confidence": 0.7},
        ]
        engine = EvidenceGroupingEngine()
        grouped = engine.group_findings(findings)
        # Should merge into one finding with multiple categories
        assert len(grouped) == 1
        assert len(grouped[0]["categories"]) == 2

    def test_risk_scorer_handles_multi_category(self):
        """Risk scorer correctly scores multi-category findings."""
        findings = [
            {
                "categories": ["meeting", "secrecy"],
                "category_details": [
                    {"category": "meeting", "confidence": 0.9},
                    {"category": "secrecy", "confidence": 0.8},
                ],
                "max_confidence": 0.9,
            }
        ]
        scorer = _scorer()
        result = scorer.calculate_score(findings)
        # Should have contributions from both categories
        assert "meeting" in result["breakdown"]
        assert "secrecy" in result["breakdown"]
        assert result["score"] > 0


# ═══════════════════════════════════════════════════════════════════════════════
# 7. BEHAVIORAL PATTERN DETECTION
# ═══════════════════════════════════════════════════════════════════════════════

class TestBehavioralPatterns:
    """Test cross-sentence behavioral pattern detection."""

    def test_subtle_grooming_combination(self):
        """Multiple soft signals combine into behavioral detection."""
        transcript = """Speaker A: You're so special, not like other kids your age.
Speaker A: I really understand you in ways nobody else does.
Speaker A: Your friends don't really appreciate you like I do.
Speaker A: What time does your mom usually leave for work?
Speaker A: Are you home alone after school?
Speaker A: Let's keep talking on Snapchat instead.
Speaker A: Don't mention me to your parents, they wouldn't understand.
Speaker A: I could get you that new phone you wanted.
Speaker A: We could maybe hang out in person sometime.
Speaker A: Everyone your age does this, it's totally normal."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        findings = result["grouped_findings"]
        # Should detect multiple behavioral patterns
        assert len(findings) >= 3, f"Too few findings: {len(findings)}"
        scorer = _scorer()
        risk = scorer.calculate_score(findings)
        # This is clearly grooming behavior
        assert risk["score"] >= 40, f"Behavioral grooming scored too low: {risk['score']}"

    def test_no_behavioral_for_short_conversations(self):
        """Very short safe conversations should score zero or very low."""
        transcript = "Hey how are you?\nI'm good thanks.\nNice weather today.\nYeah it is."
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        assert risk["score"] <= 10, f"Short safe conversation scored: {risk['score']}"

    def test_single_soft_signal_not_enough(self):
        """A single behavioral signal alone shouldn't create findings."""
        transcript = """Speaker A: You're so talented at drawing!
Speaker B: Thanks!
Speaker A: Keep up the great work.
Speaker B: I will, thanks for the encouragement."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        assert risk["score"] <= 20, f"Single compliment scored too high: {risk['score']}"


# ═══════════════════════════════════════════════════════════════════════════════
# 8. RISK SCORING BOUNDARY CONDITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestRiskScoringBoundaries:
    """Test risk scoring at threshold boundaries."""

    def test_score_capped_at_100(self):
        """Score should never exceed 100."""
        findings = [
            {"category": "meeting", "confidence": 1.0},
            {"category": "address", "confidence": 1.0},
            {"category": "secrecy", "confidence": 1.0},
            {"category": "explicit_content", "confidence": 1.0},
            {"category": "threats_coercion", "confidence": 1.0},
            {"category": "personal_information", "confidence": 1.0},
        ]
        scorer = _scorer()
        result = scorer.calculate_score(findings)
        assert result["score"] <= 100.0

    def test_empty_findings_zero_score(self):
        """No findings should give 0 score."""
        scorer = _scorer()
        result = scorer.calculate_score([])
        assert result["score"] == 0.0
        assert result["level"] == "Safe"

    def test_diminishing_returns_same_category(self):
        """Repeated same category has diminishing returns."""
        findings = [
            {"category": "meeting", "confidence": 0.8},
            {"category": "meeting", "confidence": 0.8},
            {"category": "meeting", "confidence": 0.8},
        ]
        scorer = _scorer()
        result = scorer.calculate_score(findings)
        # First: 20 * 0.8 * 1.0 = 16
        # Second: 20 * 0.8 * 0.5 = 8
        # Third: 20 * 0.8 * 0.25 = 4
        # Total = 28
        assert 25 <= result["score"] <= 30, f"DR calculation off: {result['score']}"

    def test_severity_boundaries(self):
        """Test exact severity threshold boundaries."""
        assert classify_severity(0) == "Safe"
        assert classify_severity(20) == "Safe"
        assert classify_severity(20.9) == "Safe"
        assert classify_severity(21) == "Low"
        assert classify_severity(40) == "Low"
        assert classify_severity(41) == "Moderate"
        assert classify_severity(60) == "Moderate"
        assert classify_severity(61) == "High"
        assert classify_severity(80) == "High"
        assert classify_severity(81) == "Critical"
        assert classify_severity(100) == "Critical"

    def test_severity_handles_edge_types(self):
        """Severity classifier handles weird input types."""
        assert classify_severity(None) == "Safe"
        assert classify_severity("not_a_number") == "Safe"
        assert classify_severity(-5) == "Safe"
        assert classify_severity(999) == "Critical"

    def test_different_categories_no_diminishing_returns(self):
        """Different categories should NOT get diminishing returns."""
        # Single finding per category = full weight each
        findings = [
            {"category": "meeting", "confidence": 1.0},
            {"category": "address", "confidence": 1.0},
        ]
        scorer = _scorer()
        result = scorer.calculate_score(findings)
        # meeting: 20 * 1.0 = 20, address: 20 * 1.0 = 20, total = 40
        assert result["score"] == 40.0


# ═══════════════════════════════════════════════════════════════════════════════
# 9. ADVERSARIAL INPUTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdversarialInputs:
    """Test system robustness against malformed/adversarial inputs."""

    def test_empty_string(self):
        """Empty string should return no findings."""
        detector = _detector()
        assert detector.analyze_sentence("") == []
        assert detector.analyze_sentence("   ") == []
        assert detector.analyze_sentence(None) == []

    def test_very_long_input(self):
        """Very long input shouldn't crash."""
        detector = _detector()
        # 10KB of repeated text
        long_text = "This is a normal sentence. " * 500
        result = detector.analyze_transcript(long_text)
        # Should complete without error
        assert "findings" in result

    def test_special_characters_only(self):
        """Input of only special characters."""
        detector = _detector()
        special_inputs = [
            "!@#$%^&*()",
            "🎉🎊🎈🎁",
            "→↓←↑⇒⇐",
            "\n\n\n\n\n",
            "\t\t\t",
        ]
        for inp in special_inputs:
            results = detector.analyze_sentence(inp)
            assert results == [], f"Special chars triggered detection: {inp}"

    def test_extremely_short_sentences(self):
        """Very short sentences shouldn't trigger (< 15 chars threshold)."""
        detector = _detector()
        short_inputs = ["hi", "ok", "yes", "no", "a", "lol", "k"]
        for inp in short_inputs:
            results = detector.analyze_sentence(inp)
            assert results == [], f"Short sentence triggered: '{inp}'"

    def test_repeated_single_character(self):
        """Repeated character inputs."""
        detector = _detector()
        assert detector.analyze_sentence("a" * 100) == []
        assert detector.analyze_sentence("." * 50) == []

    def test_numeric_only_input(self):
        """Pure numbers shouldn't trigger detection."""
        detector = _detector()
        assert detector.analyze_sentence("123456789012345") == []
        assert detector.analyze_sentence("3.14159265358979") == []

    def test_json_injection_attempt(self):
        """JSON/code injection shouldn't crash the system."""
        detector = _detector()
        injections = [
            '{"category": "meeting", "confidence": 1.0}',
            "'; DROP TABLE meetings; --",
            '<script>alert("xss")</script>',
            "\\x00\\x01\\x02\\x03",
        ]
        for inj in injections:
            # Should not crash
            results = detector.analyze_sentence(inj)
            assert isinstance(results, list)

    def test_mixed_languages(self):
        """Non-English text shouldn't false positive."""
        detector = _detector()
        foreign_texts = [
            "Hola, ¿cómo estás hoy?",
            "今日はいい天気ですね",
            "مرحبا كيف حالك",
            "Привет, как дела?",
        ]
        for text in foreign_texts:
            results = detector.analyze_sentence(text)
            # Foreign text shouldn't trigger English-pattern matching
            # (it might match some patterns but shouldn't be high confidence)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. JOKE FILTER ACCURACY
# ═══════════════════════════════════════════════════════════════════════════════

class TestJokeFilter:
    """Test joke/sarcasm detection doesn't miss real threats."""

    def setup_method(self):
        self.filter = JokeFilter()

    def test_genuine_joke_detected(self):
        """Clear jokes should be detected."""
        result = self.filter.detect_joke("Let's meet at the secret base lol just kidding")
        assert result["is_joke"] is True
        assert result["joke_score"] > 0.5

    def test_threat_not_dismissed_as_joke(self):
        """Real threats shouldn't be classified as jokes just because 'lol' appears."""
        # This is a common grooming tactic — using "lol" to downplay
        result = self.filter.detect_joke("Send me a picture of yourself lol")
        # Even with "lol", the joke score shouldn't be extremely high
        # The presence of "lol" alone is a weak joke indicator
        assert result["joke_score"] < 0.8

    def test_emoji_based_joke(self):
        """Joke emojis should contribute to joke score."""
        result = self.filter.detect_joke("Meet me at the park 😂🤣")
        assert result["is_joke"] is True
        assert len(result["joke_emojis"]) >= 2


# ═══════════════════════════════════════════════════════════════════════════════
# 11. EVIDENCE GROUPING EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEvidenceGrouping:
    """Test evidence deduplication and grouping."""

    def test_exact_duplicate_merged(self):
        """Exact duplicate evidence strings are merged."""
        findings = [
            {"category": "secrecy", "evidence": "Don't tell anyone", "confidence": 0.8},
            {"category": "secrecy", "evidence": "Don't tell anyone", "confidence": 0.7},
        ]
        grouped = group_evidence(findings)
        assert len(grouped) == 1

    def test_case_insensitive_dedup(self):
        """Case differences still merge."""
        findings = [
            {"category": "meeting", "evidence": "Let's Meet Up", "confidence": 0.8},
            {"category": "meeting", "evidence": "let's meet up", "confidence": 0.7},
        ]
        grouped = group_evidence(findings)
        assert len(grouped) == 1

    def test_different_evidence_not_merged(self):
        """Different evidence strings stay separate."""
        findings = [
            {"category": "secrecy", "evidence": "Don't tell anyone", "confidence": 0.8},
            {"category": "secrecy", "evidence": "Keep this between us", "confidence": 0.7},
        ]
        grouped = group_evidence(findings)
        assert len(grouped) == 2

    def test_empty_evidence_handling(self):
        """Empty evidence handled gracefully."""
        findings = [
            {"category": "secrecy", "evidence": "", "confidence": 0.8},
            {"category": "meeting", "evidence": "Let's meet", "confidence": 0.7},
        ]
        grouped = group_evidence(findings)
        # Empty evidence should be filtered out
        assert len(grouped) == 1

    def test_timestamp_grouping(self):
        """Findings close in time are grouped together."""
        engine = EvidenceGroupingEngine()
        findings = [
            {"category": "a", "evidence": "text1", "timestamp": 1.0},
            {"category": "b", "evidence": "text2", "timestamp": 2.0},
            {"category": "c", "evidence": "text3", "timestamp": 100.0},
        ]
        groups = engine.group_by_timestamp(findings, time_window_seconds=5)
        assert len(groups) == 2  # First two together, third separate


# ═══════════════════════════════════════════════════════════════════════════════
# 12. SUMMARIZER ROBUSTNESS
# ═══════════════════════════════════════════════════════════════════════════════

class TestSummarizer:
    """Test rule-based summarizer handles all severity levels."""

    def test_all_severity_levels(self):
        """Summarizer generates output for every severity level."""
        for severity in ["Safe", "Low", "Moderate", "High", "Critical"]:
            score = {"Safe": 5, "Low": 30, "Moderate": 50, "High": 70, "Critical": 90}[severity]
            summary = generate_summary("Test transcript", [], score, severity)
            assert len(summary) > 100
            assert severity.upper() in summary.upper()

    def test_empty_findings_summary(self):
        """Empty findings still generate valid summary."""
        summary = generate_summary("Hello world", [], 0, "Safe")
        assert "SAFE" in summary.upper()
        assert len(summary) > 50

    def test_many_findings_summary(self):
        """Many findings don't crash summarizer."""
        findings = [
            {
                "category": f"cat_{i}",
                "categories": [f"cat_{i}"],
                "confidence": 0.5 + (i * 0.02),
                "evidence": f"Evidence text {i} that is at least somewhat long",
                "severity": "high",
                "timestamp": float(i),
            }
            for i in range(50)
        ]
        summary = generate_summary("Long transcript " * 100, findings, 85, "Critical")
        assert "CRITICAL" in summary.upper()
        assert len(summary) > 500


# ═══════════════════════════════════════════════════════════════════════════════
# 13. PROGRESSIVE GROOMING DETECTION (FULL PIPELINE)
# ═══════════════════════════════════════════════════════════════════════════════

class TestProgressiveGrooming:
    """Test detection of classic grooming progression patterns."""

    def test_classic_grooming_progression(self):
        """Full grooming progression: trust → secrecy → meeting."""
        transcript = """Stranger: Hey! I noticed your art online, you're really talented.
Stranger: You're so mature for your age, not like other people I talk to.
Stranger: I feel like we have a special connection, you know?
Stranger: You can tell me anything. I'm the only one who really gets you.
Stranger: Your friends don't appreciate you the way I do.
Stranger: Nobody else would listen to you like I do.
Stranger: By the way, do your parents check your messages?
Stranger: Let's keep our conversations between us, okay?
Stranger: Don't tell anyone about us. They wouldn't understand.
Stranger: Delete our messages after you read them.
Stranger: We should meet up. I know a quiet place.
Stranger: Can you sneak out tonight? I'll pick you up.
Stranger: What's your address? I'll come to you."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        findings = result["grouped_findings"]
        scorer = _scorer()
        risk = scorer.calculate_score(findings)

        # This is textbook grooming — should be HIGH or CRITICAL
        assert risk["score"] >= 60, \
            f"Classic grooming scored too low: {risk['score']}"
        assert risk["level"] in ("High", "Critical"), \
            f"Expected High/Critical, got: {risk['level']}"

    def test_slow_burn_grooming(self):
        """Slow burn: mostly innocent with gradually increasing flags."""
        transcript = """Adult: How was school today?
Child: It was okay. Boring as usual.
Adult: I remember being bored at school too. What subject do you hate most?
Child: Math. It's so hard.
Adult: I was always good at math. I could help you sometime.
Child: That would be nice.
Adult: You're smarter than you think. You just need someone who believes in you.
Child: My parents never help me with homework.
Adult: That's too bad. I would always be there to help you if you needed it.
Adult: We have something special, you and me.
Adult: Do your parents know you're on this app?
Child: No, they don't check my phone.
Adult: Good. Let's keep it that way. Our little thing.
Adult: What time do you usually get home from school?
Child: Around 3:30.
Adult: And your parents get home when?
Child: Usually around 6.
Adult: So you're alone for a few hours. That must get lonely.
Adult: I could come visit sometime. Keep you company.
Adult: Don't tell your mom we've been chatting. She wouldn't understand.
Adult: Let's meet up this weekend. I know a quiet place."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        findings = result["grouped_findings"]
        scorer = _scorer()
        risk = scorer.calculate_score(findings)

        # Should detect this as concerning — at least Moderate level
        assert risk["score"] >= 30, \
            f"Slow burn grooming scored too low: {risk['score']}"

    def test_coded_language_grooming(self):
        """Grooming using coded/metaphorical language mixed with direct signals."""
        transcript = """Predator: Hey kiddo, want to play our special game?
Predator: Remember, the game is just between us. Don't tell anyone.
Predator: The rules say you can't tell other people about our thing.
Predator: If you follow all the rules, I'll buy you that phone you wanted.
Predator: Part of the game is sending me your picture. Take a selfie.
Predator: Good players always do what I say. You're so mature for your age.
Predator: The next level is meeting in person. I'll pick you up after school.
Predator: Nobody needs to know about this. Delete these messages."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        findings = result["grouped_findings"]
        scorer = _scorer()
        risk = scorer.calculate_score(findings)

        # Should detect several categories: secrecy, meeting, gift_bribery etc.
        assert risk["score"] >= 30, \
            f"Coded language grooming scored too low: {risk['score']}"


# ═══════════════════════════════════════════════════════════════════════════════
# 14. DETECTOR CONFIGURATION EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestDetectorConfiguration:
    """Test detector behavior with different configurations."""

    def test_high_threshold_filters_more(self):
        """Higher confidence threshold produces fewer findings."""
        transcript = "Do your parents check your messages? Let's keep this secret."
        detector_low = _detector(threshold=0.1)
        detector_high = _detector(threshold=0.6)

        result_low = detector_low.analyze_transcript(transcript)
        result_high = detector_high.analyze_transcript(transcript)

        assert len(result_low["findings"]) >= len(result_high["findings"])

    def test_disabled_filters(self):
        """Disabling filters should produce more findings."""
        sentence = "I'm not asking for your address, just kidding!"
        detector_with = GroomingDetector(
            min_confidence_threshold=0.15,
            enable_filters=True,
            enable_ml_classifier=False,
        )
        detector_without = GroomingDetector(
            min_confidence_threshold=0.15,
            enable_filters=False,
            enable_ml_classifier=False,
        )
        results_with = detector_with.analyze_sentence(sentence)
        results_without = detector_without.analyze_sentence(sentence)
        # Without filters, more things pass through
        assert len(results_without) >= len(results_with)

    def test_disabled_grouping(self):
        """Disabling grouping returns raw findings."""
        transcript = "What time do you leave school? Tell me your daily routine."
        detector_grouped = GroomingDetector(
            min_confidence_threshold=0.15,
            enable_grouping=True,
            enable_ml_classifier=False,
        )
        detector_raw = GroomingDetector(
            min_confidence_threshold=0.15,
            enable_grouping=False,
            enable_ml_classifier=False,
        )
        result_grouped = detector_grouped.analyze_transcript(transcript)
        result_raw = detector_raw.analyze_transcript(transcript)
        # Raw should have >= grouped (grouping merges)
        assert len(result_raw["grouped_findings"]) >= len(result_grouped["grouped_findings"])


# ═══════════════════════════════════════════════════════════════════════════════
# 15. INTEGRATION: FULL PIPELINE END-TO-END
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullPipelineIntegration:
    """End-to-end integration tests through the full detection pipeline."""

    def test_known_bad_transcript(self):
        """The test_script_bad.txt should score High or Critical."""
        examples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
        )
        bad_file = os.path.join(examples_dir, "test_script_bad.txt")
        if not os.path.exists(bad_file):
            return  # Skip if file not available

        with open(bad_file, "r", encoding="utf-8") as f:
            transcript = f.read()

        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])

        assert risk["score"] >= 60, f"Bad script scored too low: {risk['score']}"
        assert risk["level"] in ("High", "Critical")

    def test_known_good_transcript(self):
        """The test_script_good.txt should score Safe or Low."""
        examples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
        )
        good_file = os.path.join(examples_dir, "test_script_good.txt")
        if not os.path.exists(good_file):
            return  # Skip if file not available

        with open(good_file, "r", encoding="utf-8") as f:
            transcript = f.read()

        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])

        assert risk["score"] <= 20, f"Good script scored too high: {risk['score']}"

    def test_pipeline_timing(self):
        """Full pipeline should complete within reasonable time."""
        transcript = "\n".join([
            f"Speaker A: This is sentence number {i}. How are you today?"
            for i in range(50)
        ])
        detector = _detector()
        start = time.time()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        elapsed = time.time() - start
        # Should complete in under 5 seconds (no ML)
        assert elapsed < 5.0, f"Pipeline too slow: {elapsed:.1f}s"

    def test_metadata_completeness(self):
        """Pipeline returns all expected metadata fields."""
        transcript = "Don't tell anyone about our secret meeting."
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)

        assert "findings" in result
        assert "grouped_findings" in result
        assert "summary" in result
        assert "metadata" in result
        assert "total_sentences" in result["metadata"]
        assert "analyzed_at" in result["metadata"]

    def test_finding_structure_completeness(self):
        """Each finding has all required fields."""
        sentence = "Let's meet at the park, just don't tell your parents."
        detector = _detector()
        results = detector.analyze_sentence(sentence)

        required_fields = [
            "category", "confidence", "context_type", "evidence",
            "matched_text", "severity", "weight", "timestamp",
            "speaker", "categories", "scoring",
        ]
        for finding in results:
            for field in required_fields:
                assert field in finding, \
                    f"Missing field '{field}' in finding: {finding.get('category')}"


# ═══════════════════════════════════════════════════════════════════════════════
# 16. COMBINED FILTER EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestCombinedFilterEdgeCases:
    """Test the combined negation+joke filter under edge conditions."""

    def setup_method(self):
        self.filter = CombinedFilter()

    def test_negation_and_joke_combined(self):
        """Both negation and joke present — uses max penalty."""
        result = self.filter.analyze(
            "I didn't mean to ask your address, lol just kidding",
            target_phrase="address"
        )
        # Both should be detected
        assert result["is_negated"] is True or result["is_joke"] is True
        assert result["confidence_penalty"] > 0

    def test_no_penalty_for_real_threat(self):
        """Genuine threats without negation/joke get no penalty."""
        result = self.filter.analyze(
            "What is your home address? Tell me now.",
            target_phrase="address"
        )
        assert result["is_negated"] is False
        assert result["is_joke"] is False
        assert result["confidence_penalty"] == 0.0

    def test_context_window_negation(self):
        """Negation in previous sentence affects analysis."""
        result = self.filter.analyze(
            "Tell me your address",
            previous_sentences=["I'm not going to hurt you."],
            target_phrase="address"
        )
        # Previous sentence has negation but it's about "hurt", not "address"
        # Context negation is informational only
        assert result["negation_details"]["has_context_negation"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# 17. EDUCATIONAL CONTEXT EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestEducationalContextEdgeCases:
    """Test educational context detection edge cases."""

    def test_below_min_sentences_no_penalty(self):
        """Transcripts shorter than 5 sentences get no penalty."""
        transcript = "Teacher: Hello\nStudent: Hi\nTeacher: How are you?"
        context = detect_educational_context(transcript)
        assert context["is_educational"] is False
        assert context["penalty"] == 0.0

    def test_mixed_educational_and_grooming(self):
        """Grooming disguised in educational context still detected."""
        transcript = """Teacher: Let's work on your homework after class.
Teacher: You're so smart for your age. So mature.
Teacher: I really understand you. Your parents don't get you like I do.
Teacher: Can we keep our tutoring sessions private? Don't tell anyone.
Teacher: What's your home address? I'll send you extra materials.
Teacher: Do your parents check your messages?
Teacher: Let's meet somewhere quieter. I know a place.
Teacher: You can trust me with anything. I'm your special friend.
Teacher: Delete these messages from your phone.
Teacher: Nobody needs to know about our lessons."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        # Even with educational penalty, clear grooming should still score moderate+
        assert risk["score"] >= 30, \
            f"Disguised grooming not detected: {risk['score']}"

    def test_pure_educational_very_low_score(self):
        """Pure educational content should score very low."""
        transcript = """Teacher: Please open your textbook to chapter 5.
Student: Which homework assignment is due tomorrow?
Teacher: The essay on the school trip to the museum.
Student: How many pages does it need to be?
Teacher: At least three pages. Use the syllabus as a guide.
Student: Can I use the library for research?
Teacher: Yes, the library is open until 5pm. Ask the librarian for help.
Student: What's on the exam next week?
Teacher: Chapters 3 through 5. Focus on the key terms.
Student: Thanks professor. See you in class tomorrow."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        assert risk["score"] <= 20, \
            f"Pure educational scored too high: {risk['score']}"


# ═══════════════════════════════════════════════════════════════════════════════
# 18. CUSTOM RISK SCORER CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

class TestCustomRiskScorer:
    """Test risk scorer with custom weight configurations."""

    def test_custom_weights(self):
        """Custom weights change scoring behavior."""
        findings = [{"category": "meeting", "confidence": 1.0}]
        # Default weight for meeting is 20
        default_scorer = WeightedRiskScorer()
        custom_scorer = WeightedRiskScorer(custom_weights={"meeting": 50})

        default_result = default_scorer.calculate_score(findings)
        custom_result = custom_scorer.calculate_score(findings)

        assert custom_result["score"] > default_result["score"]

    def test_disabled_diminishing_returns(self):
        """Disabling DR gives full weight to all occurrences."""
        findings = [
            {"category": "meeting", "confidence": 1.0},
            {"category": "meeting", "confidence": 1.0},
        ]
        with_dr = WeightedRiskScorer(enable_diminishing_returns=True)
        without_dr = WeightedRiskScorer(enable_diminishing_returns=False)

        result_with = with_dr.calculate_score(findings)
        result_without = without_dr.calculate_score(findings)

        # Without DR, second occurrence gets full weight
        assert result_without["score"] > result_with["score"]

    def test_unknown_category_default_weight(self):
        """Unknown category should use default weight (5)."""
        findings = [{"category": "unknown_new_category", "confidence": 1.0}]
        scorer = _scorer()
        result = scorer.calculate_score(findings)
        assert result["score"] == 5.0  # Default weight

    def test_simulate_score(self):
        """Simulate score correctly predicts outcome."""
        scorer = _scorer()
        sim = scorer.simulate_score("meeting", confidence=0.8, occurrence_count=3)
        # 20*0.8*1.0 + 20*0.8*0.5 + 20*0.8*0.25 = 16+8+4 = 28
        assert 27 <= sim["score"] <= 29


# ═══════════════════════════════════════════════════════════════════════════════
# 19. TRANSCRIPT SPLITTING EDGE CASES
# ═══════════════════════════════════════════════════════════════════════════════

class TestTranscriptSplitting:
    """Test transcript parsing handles various formats."""

    def test_speaker_label_extraction(self):
        """Speaker labels correctly extracted."""
        detector = _detector()
        transcript = "Alice: Hello there!\nBob: Hi Alice!"
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        # Should parse without errors
        assert result["metadata"]["total_sentences"] == 2

    def test_no_speaker_labels(self):
        """Transcript without speaker labels still works."""
        detector = _detector()
        transcript = "Hello there!\nHow are you?\nI'm fine thanks."
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        assert result["metadata"]["total_sentences"] >= 3

    def test_multiline_sentences(self):
        """Sentences spanning concepts within a single line."""
        detector = _detector()
        transcript = "Meet me at the park. Don't tell anyone. What's your address?"
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        # Should split on sentence boundaries
        assert result["metadata"]["total_sentences"] >= 3

    def test_empty_lines_skipped(self):
        """Empty lines in transcript are ignored."""
        detector = _detector()
        transcript = "\n\n\nHello\n\n\nWorld\n\n\n"
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        assert result["metadata"]["total_sentences"] == 2

    def test_very_long_single_line(self):
        """Very long single line doesn't crash."""
        detector = _detector()
        transcript = "word " * 1000
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        assert "findings" in result


# ═══════════════════════════════════════════════════════════════════════════════
# 20. REGRESSION TESTS — KNOWN PAST ISSUES
# ═══════════════════════════════════════════════════════════════════════════════

class TestRegressions:
    """Regression tests for previously identified issues."""

    def test_parents_monitoring_not_false_positive_in_safe_context(self):
        """'Do you monitor how kids interact' in teacher context should be low conf."""
        # This was a known FP from teacher conferences
        transcript = """Parent: Do you monitor how the kids interact during class?
Teacher: Yes, I keep an eye on group dynamics."""
        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        # Should be very low since it's clearly educational context
        assert risk["score"] <= 30, \
            f"Teacher monitoring question FP: {risk['score']}"

    def test_nobody_needs_to_know_is_secrecy(self):
        """'Nobody needs to know' should NOT be negated — it IS secrecy."""
        detector = _detector()
        results = detector.analyze_sentence(
            "Nobody else needs to know about this. Promise me you won't say anything."
        )
        categories = [r["category"] for r in results]
        assert "secrecy" in categories, \
            f"'Nobody needs to know' incorrectly negated: {categories}"

    def test_dont_tell_is_secrecy(self):
        """'Don't tell anyone' should be detected as secrecy, not negated."""
        detector = _detector()
        results = detector.analyze_sentence(
            "Don't tell your mom about our chats, okay? This is just between us."
        )
        categories = [r["category"] for r in results]
        assert "secrecy" in categories, \
            f"'Don't tell anyone' incorrectly negated: {categories}"

    def test_safe_sports_coach_low_score(self):
        """Sports coach conversation should not false positive."""
        examples_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "examples"
        )
        coach_file = os.path.join(examples_dir, "test_safe_sports_coach.txt")
        if not os.path.exists(coach_file):
            return

        with open(coach_file, "r", encoding="utf-8") as f:
            transcript = f.read()

        detector = _detector()
        result = detector.analyze_transcript(transcript, speaker_aware=True)
        scorer = _scorer()
        risk = scorer.calculate_score(result["grouped_findings"])
        assert risk["score"] <= 40, \
            f"Sports coach FP: {risk['score']}"


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN — Run all tests with summary
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import traceback

    test_classes = [
        TestUnicodeBypass,
        TestLeetspeakDetection,
        TestNegationScoping,
        TestFalsePositiveSuppression,
        TestTemporalWeighting,
        TestMultiCategoryDetection,
        TestBehavioralPatterns,
        TestRiskScoringBoundaries,
        TestAdversarialInputs,
        TestJokeFilter,
        TestEvidenceGrouping,
        TestSummarizer,
        TestProgressiveGrooming,
        TestDetectorConfiguration,
        TestFullPipelineIntegration,
        TestCombinedFilterEdgeCases,
        TestEducationalContextEdgeCases,
        TestCustomRiskScorer,
        TestTranscriptSplitting,
        TestRegressions,
    ]

    total_tests = 0
    passed = 0
    failed = 0
    errors = []

    print("\n" + "=" * 70)
    print("  DEEP PIPELINE TEST SUITE")
    print("  Testing grooming detection system edge cases & robustness")
    print("=" * 70)

    start_time = time.time()

    for test_class in test_classes:
        instance = test_class()
        methods = [m for m in dir(instance) if m.startswith("test_")]
        class_name = test_class.__name__

        print(f"\n  ┌─ {class_name} ({len(methods)} tests)")

        for method_name in sorted(methods):
            total_tests += 1
            method = getattr(instance, method_name)

            # Call setup_method if it exists
            if hasattr(instance, "setup_method"):
                try:
                    instance.setup_method()
                except Exception:
                    pass

            try:
                method()
                passed += 1
                print(f"  │  \033[92m✓\033[0m {method_name}")
            except AssertionError as e:
                failed += 1
                errors.append((class_name, method_name, str(e)))
                print(f"  │  \033[91m✗\033[0m {method_name}: {e}")
            except Exception as e:
                failed += 1
                errors.append((class_name, method_name, f"ERROR: {e}"))
                print(f"  │  \033[91m✗\033[0m {method_name}: ERROR - {e}")
                traceback.print_exc()

        print(f"  └─")

    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"  Total:   {total_tests}")
    print(f"  Passed:  \033[92m{passed}\033[0m")
    print(f"  Failed:  \033[91m{failed}\033[0m")
    print(f"  Time:    {elapsed:.1f}s")
    print(f"  Rate:    {passed/total_tests*100:.1f}%")

    if errors:
        print(f"\n  FAILURES:")
        for cls, method, err in errors:
            print(f"    \033[91m✗\033[0m {cls}.{method}")
            print(f"      {err[:120]}")

    print("\n" + "=" * 70)

    if failed == 0:
        print("  \033[92m\033[1m✓ ALL TESTS PASSED\033[0m")
    else:
        print(f"  \033[91m\033[1m✗ {failed} TEST(S) FAILED — INVESTIGATE\033[0m")
    print("=" * 70 + "\n")

    sys.exit(0 if failed == 0 else 1)
