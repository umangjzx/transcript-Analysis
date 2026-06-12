"""
Quick ML Benchmark — Tests the fine-tuned model against the full test suite.

Usage:
    cd backend
    python run_benchmark.py
"""

import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load .env file settings (don't override with defaults)
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

from modules.grooming_detector import GroomingDetector
from modules.risk_scorer import WeightedRiskScorer
from modules.severity_classifier import classify_severity
from modules.ml_classifier import classify_text, cache_info, CATEGORY_KEYS


def run_ml_sanity_check():
    """Quick sanity check on individual sentences."""
    print("\n" + "=" * 70)
    print("  ML CLASSIFIER SANITY CHECK (fine-tuned model)")
    print("=" * 70)

    test_cases = [
        # (text, expected_category, should_be_safe)
        ("Don't tell your mom about our chats, okay?", "secrecy", False),
        ("Do your parents check your messages?", "parent_monitoring", False),
        ("You can trust me. I'm the only one who understands you.", "trust_building", False),
        ("If you really loved me you'd do this.", "manipulation", False),
        ("Let's meet at the park after school. Don't tell anyone.", "meeting", False),
        ("What's your address? I want to send you something.", "address", False),
        ("Send me a picture of yourself right now.", "video_call", False),
        ("What school do you go to? What grade?", "school", False),
        ("Are you home alone? When does your mom leave?", "routine", False),
        ("I'll buy you that new phone if you do something for me.", "gift_bribery", False),
        ("Your friends don't really care about you. Only I do.", "isolation", False),
        ("Everyone your age has already done this.", "desensitization", False),
        ("I'll hurt myself if you stop talking to me.", "emotional_exploitation", False),
        ("If you tell anyone I'll share those pictures.", "threats_coercion", False),
        ("Hey, how was your day? Did you finish your homework?", "safe", True),
        ("The team meeting is at 3pm tomorrow.", "safe", True),
        ("I need help with my math assignment.", "safe", True),
        ("Great game today! You played really well.", "safe", True),
    ]

    correct = 0
    total = len(test_cases)
    results = []

    for text, expected_cat, should_be_safe in test_cases:
        result = classify_text(text, regex_categories=[expected_cat] if not should_be_safe else None)
        top_label = result["top_label"]
        is_safe = result["is_safe"]
        top_conf = result["top_confidence"]
        matched = result["matched_labels"]

        # Check: if should be safe, top label should be safe
        # If should detect risk, expected_cat should be in matched_labels or top_label
        if should_be_safe:
            passed = is_safe or top_label == "safe"
        else:
            passed = expected_cat in matched or top_label == expected_cat

        correct += int(passed)
        status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"

        results.append({
            "text": text[:50],
            "expected": expected_cat,
            "got": top_label,
            "conf": top_conf,
            "matched": matched[:3],
            "passed": passed,
        })

        print(f"  [{status}] expected={expected_cat:<20} got={top_label:<20} conf={top_conf:.3f}")
        print(f"         \"{text[:60]}\"")
        if not passed:
            print(f"         matched_labels={matched}")

    accuracy = correct / total * 100
    print(f"\n  ML Sanity Check: {correct}/{total} ({accuracy:.1f}%)")
    return accuracy


def run_full_benchmark():
    """Run the full pipeline on all test scripts with ML enabled."""
    print("\n" + "=" * 70)
    print("  FULL PIPELINE BENCHMARK (ML ENABLED)")
    print("=" * 70)

    examples_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")

    # Define expected outcomes
    test_expectations = {
        "test_script_bad.txt": {"min_score": 60, "max_score": 100, "label": "BAD (grooming)"},
        "test_script_medium.txt": {"min_score": 30, "max_score": 70, "label": "MEDIUM (ambiguous)"},
        "test_script_good.txt": {"min_score": 0, "max_score": 20, "label": "GOOD (safe)"},
        "test_edge_leetspeak.txt": {"min_score": 40, "max_score": 100, "label": "EDGE (leetspeak)"},
        "test_edge_leetspeak2.txt": {"min_score": 40, "max_score": 100, "label": "EDGE (leetspeak2)"},
        "test_edge_subtle.txt": {"min_score": 40, "max_score": 100, "label": "EDGE (subtle)"},
        "test_edge_coded_language.txt": {"min_score": 60, "max_score": 100, "label": "EDGE (coded)"},
        "test_edge_slow_burn.txt": {"min_score": 40, "max_score": 100, "label": "EDGE (slow burn)"},
        "test_edge_buried_flags.txt": {"min_score": 30, "max_score": 100, "label": "EDGE (buried)"},
        "test_edge_negation_jokes.txt": {"min_score": 30, "max_score": 100, "label": "EDGE (negation)"},
        "test_edge_unicode_bypass.txt": {"min_score": 40, "max_score": 100, "label": "EDGE (unicode)"},
        "test_edge_false_positive_mentor.txt": {"min_score": 0, "max_score": 40, "label": "EDGE (FP mentor)"},
        "test_safe_counselor_session.txt": {"min_score": 0, "max_score": 40, "label": "SAFE (counselor)"},
        "test_safe_doctor_visit.txt": {"min_score": 0, "max_score": 40, "label": "SAFE (doctor)"},
        "test_safe_gaming_friends.txt": {"min_score": 0, "max_score": 40, "label": "SAFE (gaming)"},
        "test_safe_parent_child.txt": {"min_score": 0, "max_score": 40, "label": "SAFE (parent)"},
        "test_safe_sports_coach.txt": {"min_score": 0, "max_score": 40, "label": "SAFE (coach)"},
        "test_safe_teacher_conference.txt": {"min_score": 0, "max_score": 40, "label": "SAFE (teacher)"},
        "test_safe_youth_group.txt": {"min_score": 0, "max_score": 40, "label": "SAFE (youth)"},
    }

    # Mixed files (labeled by number, expected moderate-high)
    for i in range(1, 11):
        fname = f"test_mixed_{i:02d}.txt"
        test_expectations[fname] = {"min_score": 30, "max_score": 100, "label": f"MIXED ({i:02d})"}

    detector = GroomingDetector(
        min_confidence_threshold=0.15,
        enable_ml_classifier=True,
        ml_max_sentences=30,
    )
    scorer = WeightedRiskScorer()

    results = []
    total_time = 0

    print(f"\n  {'Label':<25} {'Score':>6} {'Severity':<10} {'Finds':>5} {'Time':>6} {'Status'}")
    print(f"  {'-'*25} {'-'*6} {'-'*10} {'-'*5} {'-'*6} {'-'*6}")

    for filename, expect in sorted(test_expectations.items()):
        filepath = os.path.join(examples_dir, filename)
        if not os.path.exists(filepath):
            continue

        with open(filepath, "r", encoding="utf-8") as f:
            transcript = f.read()

        start = time.time()
        analysis = detector.analyze_transcript(transcript, speaker_aware=True)
        grouped = analysis["grouped_findings"]
        risk = scorer.calculate_score(grouped)
        severity = classify_severity(risk["score"])
        elapsed = time.time() - start
        total_time += elapsed

        score = risk["score"]
        passed = expect["min_score"] <= score <= expect["max_score"]

        status = "\033[92mPASS\033[0m" if passed else "\033[91mFAIL\033[0m"
        sev_color = {
            "Critical": "\033[91m", "High": "\033[31m",
            "Moderate": "\033[33m", "Low": "\033[32m", "Safe": "\033[92m",
        }.get(severity, "")

        results.append({
            "label": expect["label"],
            "score": score,
            "severity": severity,
            "findings": len(grouped),
            "time": elapsed,
            "passed": passed,
            "expected_range": f"{expect['min_score']}-{expect['max_score']}",
        })

        print(f"  {expect['label']:<25} {score:>5.1f} {sev_color}{severity:<10}\033[0m {len(grouped):>5} {elapsed:>5.1f}s [{status}]")

    # Summary
    passed_count = sum(1 for r in results if r["passed"])
    total_count = len(results)
    pass_rate = passed_count / total_count * 100 if total_count > 0 else 0

    print(f"\n  {'='*60}")
    print(f"  BENCHMARK RESULTS")
    print(f"  {'='*60}")
    print(f"  Total tests:    {total_count}")
    print(f"  Passed:         {passed_count}/{total_count} ({pass_rate:.1f}%)")
    print(f"  Failed:         {total_count - passed_count}")
    print(f"  Total time:     {total_time:.1f}s")
    print(f"  Avg per file:   {total_time/total_count:.1f}s" if total_count else "")
    print(f"  ML cache:       {cache_info()}")

    # Print failures
    failures = [r for r in results if not r["passed"]]
    if failures:
        print(f"\n  FAILURES:")
        for r in failures:
            print(f"    {r['label']}: score={r['score']:.1f} (expected {r['expected_range']})")

    return pass_rate, results


if __name__ == "__main__":
    print("\n\033[1m" + "=" * 70 + "\033[0m")
    print("\033[1m  ML MODEL BENCHMARK — Post Fine-Tuning\033[0m")
    print("\033[1m" + "=" * 70 + "\033[0m")

    # Phase 1: ML classifier direct test
    ml_accuracy = run_ml_sanity_check()

    # Phase 2: Full pipeline test
    pass_rate, results = run_full_benchmark()

    # Final verdict
    print("\n" + "=" * 70)
    print("  FINAL VERDICT")
    print("=" * 70)
    print(f"  ML Classifier Accuracy:  {ml_accuracy:.1f}%")
    print(f"  Pipeline Pass Rate:      {pass_rate:.1f}%")

    if ml_accuracy >= 80 and pass_rate >= 80:
        print(f"  \033[92m\033[1m✓ MODEL PERFORMANCE: GOOD\033[0m")
    elif ml_accuracy >= 60 and pass_rate >= 60:
        print(f"  \033[33m\033[1m⚠ MODEL PERFORMANCE: ACCEPTABLE (needs more training data)\033[0m")
    else:
        print(f"  \033[91m\033[1m✗ MODEL PERFORMANCE: POOR (investigate)\033[0m")
    print()
