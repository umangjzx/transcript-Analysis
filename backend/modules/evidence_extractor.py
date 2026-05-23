"""
Evidence Extractor for Grooming Detection.

This module extracts and formats evidence from grooming detection findings
for use in reports and summaries.
"""

from typing import List, Dict, Any


SEVERITY_MAP = {
    "secrecy": "HIGH",
    "parent_monitoring": "HIGH",
    "address": "HIGH",
    "school": "HIGH",
    "meeting": "HIGH",
    "video_call": "MEDIUM",
    "routine": "MEDIUM",
    "relationship_building": "MEDIUM",
    "manipulation": "MEDIUM",
    "trust_building": "LOW"
}


def extract_evidence(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Extract evidence from grooming detection findings.
    
    Handles both old format (type) and new format (category/categories).
    
    Args:
        findings: List of detection findings
    
    Returns:
        List of evidence dictionaries
    """
    evidence = []
    
    for item in findings:
        # Handle both old and new format
        categories = []
        
        if "categories" in item:
            # New grouped format with multiple categories
            categories = item["categories"]
        elif "category" in item:
            # New single category format
            categories = [item["category"]]
        elif "type" in item:
            # Old format (backward compatibility)
            categories = [item["type"]]
        
        # Get the primary category (first one) for severity mapping
        primary_category = categories[0] if categories else "unknown"
        
        # Get confidence (handle both formats)
        confidence = item.get("max_confidence") or item.get("confidence", 0)

        # Pull nested scoring/filter fields to the top level for the frontend
        scoring  = item.get("scoring", {})
        filters  = item.get("filters", {})

        ev = {
            "timestamp":          item.get("timestamp"),
            "end":                item.get("end"),
            "category":           primary_category,
            "categories":         categories,
            "severity":           SEVERITY_MAP.get(primary_category, "LOW"),
            "confidence":         confidence,
            # The actual sentence text — stored as "evidence" in the detector
            "evidence":           item.get("evidence", item.get("text", "")),
            # Rich detail fields for the frontend Evidence Log
            "speaker":            item.get("speaker"),
            "context_type":       item.get("context_type"),
            "base_confidence":    scoring.get("base_confidence", item.get("base_confidence")),
            "context_multiplier": scoring.get("context_multiplier", item.get("context_multiplier")),
            "is_joke":            filters.get("is_joke", item.get("is_joke")),
            "is_negation":        filters.get("is_negated", item.get("is_negation")),
        }

        # Remove None values to keep the payload clean
        ev = {k: v for k, v in ev.items() if v is not None}

        evidence.append(ev)
    
    return evidence