def generate_stats(
        transcript,
        findings,
        severity,
        risk_score
):
    """
    Generate statistics from analysis results.
    
    Handles both old format (type) and new format (category/categories).
    """
    categories = {}

    for item in findings:
        # Handle both old and new format
        # New format: "category" or "categories" (list)
        # Old format: "type"
        item_categories = []
        
        if "categories" in item:
            # New grouped format with multiple categories
            item_categories = item["categories"]
        elif "category" in item:
            # New single category format
            item_categories = [item["category"]]
        elif "type" in item:
            # Old format (backward compatibility)
            item_categories = [item["type"]]
        
        # Count each category
        for cat in item_categories:
            if cat:
                categories[cat] = categories.get(cat, 0) + 1

    return {
        "word_count":
        len(transcript.split()),

        "character_count":
        len(transcript),

        "finding_count":
        len(findings),

        "unique_categories":
        len(categories),

        "categories":
        categories,

        # Alias for frontend compatibility
        "category_breakdown":
        categories,

        "severity":
        severity,

        "risk_score":
        risk_score
    }