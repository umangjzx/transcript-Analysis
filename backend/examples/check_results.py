"""Fetch and display results for the batch benchmark run (IDs 550-578)."""
import sys, os
sys.path.insert(0, "/app")
from database.mongo import get_mongo_db

db = get_mongo_db()
header = f"{'#':<5} {'Filename':<45} {'Severity':<10} {'Score':<7}"
print(header)
print("-" * len(header))

results = list(db["analysis_results"].find(
    {"meeting_id": {"$gte": 550, "$lte": 578}}
).sort("meeting_id", 1))

if not results:
    # Try meetings collection
    results = list(db["meetings"].find(
        {"meeting_id": {"$gte": 550, "$lte": 578}}
    ).sort("meeting_id", 1))

for doc in results:
    mid = doc.get("meeting_id", "?")
    fn = doc.get("filename", "?")
    sev = doc.get("severity", "?")
    score = doc.get("risk_score", 0)
    print(f"{mid:<5} {fn:<45} {sev:<10} {score:<7.1f}")

print(f"\nTotal: {len(results)} reports")
