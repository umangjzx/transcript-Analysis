"""
Batch benchmark: Queue all 29 test transcripts through the Celery pipeline
simultaneously and measure total wall-clock time + per-task results.

Usage (run from backend container):
    python examples/batch_benchmark.py
"""

import os
import sys
import time
import glob
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.mongo import get_mongo_db, next_meeting_id, save_meeting_metadata
from tasks.analysis_tasks import run_drive_import_analysis


def main():
    examples_dir = os.path.dirname(os.path.abspath(__file__))
    txt_files = sorted(glob.glob(os.path.join(examples_dir, "*.txt")))

    print(f"\n{'='*70}")
    print(f"  BATCH BENCHMARK — {len(txt_files)} files")
    print(f"  Started at: {datetime.now(timezone.utc).isoformat()}")
    print(f"{'='*70}\n")

    tasks = []
    start_time = time.time()

    for filepath in txt_files:
        filename = os.path.basename(filepath)
        with open(filepath, "r", encoding="utf-8") as f:
            transcript = f.read()

        record_id = next_meeting_id()
        save_meeting_metadata(
            meeting_id=record_id,
            filename=filename,
            file_size_bytes=len(transcript.encode("utf-8")),
            status="PROCESSING",
        )

        # Queue task via Celery
        result = run_drive_import_analysis.delay(record_id, transcript, filename)
        tasks.append({
            "record_id": record_id,
            "filename": filename,
            "task_id": result.id,
            "chars": len(transcript),
            "result": result,
        })
        print(f"  Queued #{record_id:>4} | {filename:<45} | {len(transcript):>6} chars | task={result.id[:8]}")

    queue_time = time.time() - start_time
    print(f"\n  All {len(tasks)} tasks queued in {queue_time:.1f}s")
    print(f"  Waiting for all tasks to complete...\n")

    # Wait for all tasks to finish
    for task_info in tasks:
        task_info["result"].get(timeout=600)  # 10 min max per task

    total_time = time.time() - start_time

    # Fetch results from MongoDB
    print(f"\n{'='*70}")
    print(f"  RESULTS")
    print(f"{'='*70}")
    print(f"  {'#':<5} {'Filename':<45} {'Severity':<10} {'Score':<7} {'Chars':<7}")
    print(f"  {'-'*5} {'-'*45} {'-'*10} {'-'*7} {'-'*7}")

    db = get_mongo_db()
    for task_info in tasks:
        record_id = task_info["record_id"]
        doc = db["meetings"].find_one({"meeting_id": record_id})
        severity = doc.get("severity", "?") if doc else "?"
        score = doc.get("risk_score", 0) if doc else 0
        print(f"  {record_id:<5} {task_info['filename']:<45} {severity:<10} {score:<7.1f} {task_info['chars']:<7}")

    print(f"\n{'='*70}")
    print(f"  TOTAL WALL-CLOCK TIME: {total_time:.1f}s ({total_time/60:.1f} min)")
    print(f"  AVG PER FILE: {total_time/len(tasks):.1f}s")
    print(f"  THROUGHPUT: {len(tasks)/total_time*60:.1f} files/min")
    print(f"  CONCURRENCY: 2 workers (prefork)")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    main()
