"""
End-to-End Test Submission Script.

Submits new test transcripts to the running Docker backend for full pipeline analysis.
Results will appear in the frontend at http://localhost:3000

Usage:
    python examples/submit_e2e_tests.py
"""

import os
import sys
import time
import json
import requests

API_URL = os.getenv("API_URL", "http://localhost:8000")

# Test files to submit (filename, expected severity range)
TEST_FILES = [
    ("test_safe_online_tutoring.txt", "Safe", "Low"),
    ("test_safe_therapy_session.txt", "Safe", "Low"),
    ("test_safe_sibling_conversation.txt", "Safe", "Safe"),
    ("test_edge_gaming_predator.txt", "High", "Critical"),
    ("test_edge_multi_platform.txt", "High", "Critical"),
    ("test_edge_roleplay_grooming.txt", "High", "Critical"),
    ("test_edge_gift_escalation.txt", "High", "Critical"),
    ("test_edge_authority_abuse.txt", "Moderate", "Critical"),
    ("test_edge_emotional_manipulation.txt", "High", "Critical"),
]


def submit_transcript(filepath: str, filename: str) -> dict:
    """Submit a transcript to the API and return the response."""
    with open(filepath, "r", encoding="utf-8") as f:
        transcript = f.read()

    response = requests.post(
        f"{API_URL}/analyze/transcript",
        json={"transcript": transcript, "filename": filename},
        headers={"Content-Type": "application/json"},
        timeout=30,
    )

    if response.status_code != 200:
        return {"error": response.status_code, "detail": response.text}

    return response.json()


def check_health() -> bool:
    """Check if the backend is healthy."""
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def main():
    print("\n" + "=" * 70)
    print("  END-TO-END PIPELINE TEST — Submitting to Docker Backend")
    print(f"  API: {API_URL}")
    print("=" * 70)

    # Health check
    if not check_health():
        print(f"\n  ERROR: Backend at {API_URL} is not responding!")
        print("  Make sure Docker containers are running: docker compose up -d")
        sys.exit(1)

    print(f"\n  ✓ Backend healthy\n")

    examples_dir = os.path.dirname(os.path.abspath(__file__))
    submitted = []
    errors = []

    print(f"  {'Filename':<45} {'ID':>5} {'Status':<12}")
    print(f"  {'-'*45} {'-'*5} {'-'*12}")

    for filename, expected_min, expected_max in TEST_FILES:
        filepath = os.path.join(examples_dir, filename)
        if not os.path.exists(filepath):
            print(f"  {filename:<45} {'?':>5} {'MISSING':<12}")
            continue

        result = submit_transcript(filepath, filename)

        if "error" in result:
            print(f"  {filename:<45} {'ERR':>5} {result['error']}")
            errors.append((filename, result))
        else:
            record_id = result.get("id", "?")
            status = result.get("status", "?")
            print(f"  {filename:<45} {record_id:>5} {status:<12}")
            submitted.append({
                "filename": filename,
                "id": record_id,
                "expected_min": expected_min,
                "expected_max": expected_max,
            })

        # Small delay to avoid overwhelming the queue
        time.sleep(0.5)

    print(f"\n  Submitted: {len(submitted)}/{len(TEST_FILES)}")
    if errors:
        print(f"  Errors: {len(errors)}")
        for fn, err in errors:
            print(f"    ✗ {fn}: {err}")

    # Wait for processing
    print(f"\n  Waiting for Celery workers to process...")
    print(f"  (This may take 30-120 seconds depending on ML model loading)")
    print(f"\n  Checking status every 10 seconds...\n")

    all_done = False
    max_wait = 300  # 5 minutes max
    waited = 0

    while not all_done and waited < max_wait:
        time.sleep(10)
        waited += 10

        all_done = True
        done_count = 0

        for item in submitted:
            try:
                resp = requests.get(
                    f"{API_URL}/api/v1/report/{item['id']}",
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    status = data.get("status", "PROCESSING")
                    if status in ("COMPLETED", "FAILED"):
                        done_count += 1
                        item["result"] = data
                    else:
                        all_done = False
                else:
                    all_done = False
            except Exception:
                all_done = False

        sys.stdout.write(f"\r  Progress: {done_count}/{len(submitted)} completed ({waited}s elapsed)")
        sys.stdout.flush()

    print("\n")

    # Print results
    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print(f"\n  {'Filename':<40} {'Score':>6} {'Severity':<10} {'Expected':<15} {'Status'}")
    print(f"  {'-'*40} {'-'*6} {'-'*10} {'-'*15} {'-'*6}")

    passed = 0
    failed = 0
    severity_order = {"Safe": 0, "Low": 1, "Moderate": 2, "High": 3, "Critical": 4}

    for item in submitted:
        result = item.get("result", {})
        if not result:
            print(f"  {item['filename']:<40} {'?':>6} {'TIMEOUT':<10} {'':<15} {'FAIL'}")
            failed += 1
            continue

        score = result.get("risk_score", 0)
        severity = result.get("severity", "?")
        expected_range = f"{item['expected_min']}-{item['expected_max']}"

        # Check if severity is within expected range
        sev_val = severity_order.get(severity, -1)
        min_val = severity_order.get(item["expected_min"], 0)
        max_val = severity_order.get(item["expected_max"], 4)

        is_pass = min_val <= sev_val <= max_val
        status_str = "PASS" if is_pass else "FAIL"

        if is_pass:
            passed += 1
        else:
            failed += 1

        print(f"  {item['filename']:<40} {score:>5.1f} {severity:<10} {expected_range:<15} {status_str}")

    print(f"\n  {'='*60}")
    print(f"  PASSED: {passed}/{len(submitted)}")
    print(f"  FAILED: {failed}/{len(submitted)}")
    print(f"  {'='*60}")

    if failed == 0:
        print(f"\n  ✓ ALL E2E TESTS PASSED — Check frontend at http://localhost:3000")
    else:
        print(f"\n  ✗ {failed} TEST(S) OUTSIDE EXPECTED RANGE")
        print(f"    Check frontend at http://localhost:3000 for full reports")

    print("\n  Frontend URLs:")
    for item in submitted:
        print(f"    http://localhost:3000/report/{item['id']}")

    print()


if __name__ == "__main__":
    main()
