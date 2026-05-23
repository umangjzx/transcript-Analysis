"""
Evidence Grouping Engine for Grooming Detection.

This module groups and deduplicates evidence findings when a single sentence
triggers multiple pattern categories. Instead of creating duplicate findings,
it merges them into a single evidence entry with multiple categories.

Example:
    Input: [
        {"category": "school", "evidence": "What time do you leave school?"},
        {"category": "routine", "evidence": "What time do you leave school?"}
    ]
    
    Output: [
        {"evidence": "What time do you leave school?", "categories": ["school", "routine"]}
    ]
"""

from typing import List, Dict, Any, Optional, Set
from collections import defaultdict
import hashlib


class EvidenceGroupingEngine:
    """
    Group and deduplicate evidence findings across multiple categories.
    
    This engine handles cases where a single piece of evidence (sentence or phrase)
    matches multiple pattern categories, consolidating them into a single finding
    with multiple categories instead of creating duplicates.
    """
    
    def __init__(self, similarity_threshold: float = 0.95):
        """
        Initialize the evidence grouping engine.
        
        Args:
            similarity_threshold: Threshold for considering evidence as duplicate (0.0-1.0)
                                 Default 0.95 means 95% similarity required
        """
        self.similarity_threshold = similarity_threshold
    
    def group_findings(
        self,
        findings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Group findings by evidence text, merging categories for identical evidence.
        
        Args:
            findings: List of finding dictionaries, each containing at minimum:
                     - category: str
                     - evidence: str
                     Additional fields are preserved in the grouped output.
        
        Returns:
            List of grouped findings with merged categories
        """
        if not findings:
            return []
        
        # Group by normalized evidence text
        evidence_groups = defaultdict(list)
        
        for finding in findings:
            evidence = finding.get("evidence", "")
            if not evidence:
                continue
            
            # Normalize evidence for grouping
            normalized = self._normalize_text(evidence)
            evidence_groups[normalized].append(finding)
        
        # Merge categories for each evidence group
        grouped_results = []
        
        for normalized_evidence, group in evidence_groups.items():
            merged = self._merge_group(group)
            grouped_results.append(merged)
        
        return grouped_results
    
    def merge_categories(
        self,
        findings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Merge categories for findings with similar or identical evidence.
        
        This method is more sophisticated than group_findings as it also
        handles near-duplicate evidence using similarity matching.
        
        Args:
            findings: List of finding dictionaries
        
        Returns:
            List of merged findings with consolidated categories
        """
        if not findings:
            return []
        
        # First, do exact grouping
        exact_groups = self.group_findings(findings)
        
        # Then, check for near-duplicates and merge if needed
        merged_results = []
        processed_indices = set()
        
        for i, finding in enumerate(exact_groups):
            if i in processed_indices:
                continue
            
            # Find similar findings
            similar_indices = self._find_similar_findings(
                finding,
                exact_groups,
                start_index=i + 1
            )
            
            if similar_indices:
                # Merge similar findings
                to_merge = [finding] + [exact_groups[j] for j in similar_indices]
                merged = self._merge_group(to_merge)
                merged_results.append(merged)
                
                # Mark as processed
                processed_indices.add(i)
                processed_indices.update(similar_indices)
            else:
                # No similar findings, add as is
                merged_results.append(finding)
                processed_indices.add(i)
        
        return merged_results
    
    def deduplicate(
        self,
        findings: List[Dict[str, Any]],
        keep_highest_confidence: bool = True
    ) -> List[Dict[str, Any]]:
        """
        Remove duplicate findings, optionally keeping the one with highest confidence.
        
        Args:
            findings: List of finding dictionaries
            keep_highest_confidence: If True, keeps finding with highest confidence score
        
        Returns:
            Deduplicated list of findings
        """
        if not findings:
            return []
        
        # Group by evidence
        grouped = self.group_findings(findings)
        
        # If keep_highest_confidence, sort categories by confidence
        if keep_highest_confidence:
            for finding in grouped:
                if "category_details" in finding:
                    # Sort categories by confidence if available
                    finding["category_details"].sort(
                        key=lambda x: x.get("confidence", 0),
                        reverse=True
                    )
        
        return grouped
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for comparison.
        
        Args:
            text: Text to normalize
        
        Returns:
            Normalized text
        """
        # Convert to lowercase, strip whitespace, remove extra spaces
        normalized = text.lower().strip()
        normalized = " ".join(normalized.split())
        return normalized
    
    def _merge_group(self, group: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Merge a group of findings with the same evidence.
        
        Args:
            group: List of findings to merge
        
        Returns:
            Merged finding dictionary
        """
        if not group:
            return {}
        
        if len(group) == 1:
            # Single finding, just ensure categories is a list
            finding = group[0].copy()
            if "category" in finding and "categories" not in finding:
                finding["categories"] = [finding["category"]]
            return finding
        
        # Use the first finding as base
        merged = group[0].copy()
        
        # Collect all categories
        categories = []
        category_details = []
        
        for finding in group:
            category = finding.get("category")
            if category and category not in categories:
                categories.append(category)
                
                # Store category-specific details
                detail = {
                    "category": category,
                    "confidence": finding.get("confidence"),
                    "pattern_strength": finding.get("pattern_strength"),
                    "matched_text": finding.get("matched_text"),
                    "severity": finding.get("severity"),
                    "timestamp": finding.get("timestamp")
                }
                # Remove None values
                detail = {k: v for k, v in detail.items() if v is not None}
                category_details.append(detail)
        
        # Update merged finding
        merged["categories"] = categories
        merged["category_count"] = len(categories)
        
        # Store detailed information per category
        if category_details:
            merged["category_details"] = category_details
        
        # Calculate aggregate confidence (max of all categories)
        confidences = [
            f.get("confidence", 0) for f in group if f.get("confidence") is not None
        ]
        if confidences:
            merged["max_confidence"] = max(confidences)
            merged["avg_confidence"] = sum(confidences) / len(confidences)
        
        # Calculate aggregate severity (highest severity wins)
        severity_order = {"low": 1, "medium": 2, "high": 3, "critical": 4}
        severities = [
            f.get("severity") for f in group if f.get("severity") is not None
        ]
        if severities:
            merged["severity"] = max(
                severities,
                key=lambda s: severity_order.get(s, 0)
            )
        
        # Remove single category field if present
        if "category" in merged:
            del merged["category"]
        
        return merged
    
    def _find_similar_findings(
        self,
        target: Dict[str, Any],
        findings: List[Dict[str, Any]],
        start_index: int = 0
    ) -> List[int]:
        """
        Find findings with similar evidence to the target.
        
        Args:
            target: Target finding to compare against
            findings: List of all findings
            start_index: Index to start searching from
        
        Returns:
            List of indices of similar findings
        """
        similar_indices = []
        target_evidence = target.get("evidence", "")
        
        if not target_evidence:
            return similar_indices
        
        target_normalized = self._normalize_text(target_evidence)
        
        for i in range(start_index, len(findings)):
            finding = findings[i]
            evidence = finding.get("evidence", "")
            
            if not evidence:
                continue
            
            normalized = self._normalize_text(evidence)
            
            # Calculate similarity
            similarity = self._calculate_similarity(target_normalized, normalized)
            
            if similarity >= self.similarity_threshold:
                similar_indices.append(i)
        
        return similar_indices
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        Calculate similarity between two texts.
        
        Uses a simple character-based similarity metric.
        
        Args:
            text1: First text
            text2: Second text
        
        Returns:
            Similarity score (0.0-1.0)
        """
        if text1 == text2:
            return 1.0
        
        if not text1 or not text2:
            return 0.0
        
        # Simple character overlap similarity
        set1 = set(text1)
        set2 = set(text2)
        
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        
        if union == 0:
            return 0.0
        
        # Jaccard similarity
        jaccard = intersection / union
        
        # Also consider length similarity
        len_similarity = min(len(text1), len(text2)) / max(len(text1), len(text2))
        
        # Combined similarity (weighted average)
        similarity = (jaccard * 0.7) + (len_similarity * 0.3)
        
        return similarity
    
    def group_by_timestamp(
        self,
        findings: List[Dict[str, Any]],
        time_window_seconds: int = 5
    ) -> List[List[Dict[str, Any]]]:
        """
        Group findings by timestamp proximity.
        
        Useful for grouping findings that occurred close together in time.
        
        Args:
            findings: List of findings with timestamp field
            time_window_seconds: Time window in seconds for grouping
        
        Returns:
            List of finding groups
        """
        if not findings:
            return []
        
        # Sort by timestamp
        sorted_findings = sorted(
            findings,
            key=lambda x: x.get("timestamp", 0)
        )
        
        groups = []
        current_group = [sorted_findings[0]]
        
        for i in range(1, len(sorted_findings)):
            current = sorted_findings[i]
            previous = sorted_findings[i - 1]
            
            current_time = current.get("timestamp", 0)
            previous_time = previous.get("timestamp", 0)
            
            if current_time - previous_time <= time_window_seconds:
                current_group.append(current)
            else:
                groups.append(current_group)
                current_group = [current]
        
        # Add last group
        if current_group:
            groups.append(current_group)
        
        return groups
    
    def create_summary(
        self,
        grouped_findings: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create a summary of grouped findings.
        
        Args:
            grouped_findings: List of grouped findings
        
        Returns:
            Summary dictionary with statistics
        """
        if not grouped_findings:
            return {
                "total_findings": 0,
                "total_categories": 0,
                "category_distribution": {},
                "severity_distribution": {},
                "avg_categories_per_finding": 0.0
            }
        
        # Count categories
        category_counts = defaultdict(int)
        severity_counts = defaultdict(int)
        total_category_count = 0
        
        for finding in grouped_findings:
            categories = finding.get("categories", [])
            total_category_count += len(categories)
            
            for category in categories:
                category_counts[category] += 1
            
            severity = finding.get("severity")
            if severity:
                severity_counts[severity] += 1
        
        avg_categories = total_category_count / len(grouped_findings) if grouped_findings else 0.0
        
        return {
            "total_findings": len(grouped_findings),
            "total_categories": total_category_count,
            "unique_categories": len(category_counts),
            "category_distribution": dict(category_counts),
            "severity_distribution": dict(severity_counts),
            "avg_categories_per_finding": round(avg_categories, 2),
            "multi_category_findings": sum(
                1 for f in grouped_findings if len(f.get("categories", [])) > 1
            )
        }


# Convenience functions
def group_evidence(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Quick convenience function to group findings by evidence.
    
    Args:
        findings: List of finding dictionaries
    
    Returns:
        Grouped findings
    """
    engine = EvidenceGroupingEngine()
    return engine.group_findings(findings)


def deduplicate_evidence(findings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Quick convenience function to deduplicate findings.
    
    Args:
        findings: List of finding dictionaries
    
    Returns:
        Deduplicated findings
    """
    engine = EvidenceGroupingEngine()
    return engine.deduplicate(findings)


def merge_similar_evidence(
    findings: List[Dict[str, Any]],
    similarity_threshold: float = 0.95
) -> List[Dict[str, Any]]:
    """
    Quick convenience function to merge similar evidence.
    
    Args:
        findings: List of finding dictionaries
        similarity_threshold: Similarity threshold (0.0-1.0)
    
    Returns:
        Merged findings
    """
    engine = EvidenceGroupingEngine(similarity_threshold=similarity_threshold)
    return engine.merge_categories(findings)


# Export main components
__all__ = [
    'EvidenceGroupingEngine',
    'group_evidence',
    'deduplicate_evidence',
    'merge_similar_evidence'
]
