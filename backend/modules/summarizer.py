def generate_summary(
        transcript,
        findings,
        score,
        severity
):

    total_words = len(
        transcript.split()
    )

    # Collect all categories, handling both old format (type) and new format (category/categories)
    all_cats = []
    for item in findings:
        if "categories" in item:
            all_cats.extend(item["categories"])
        elif "category" in item:
            all_cats.append(item["category"])
        elif "type" in item:
            all_cats.append(item["type"])

    categories = sorted(list(set(all_cats)))

    summary = f"""
====================================
TRANSCRIPT ANALYSIS REPORT
====================================

Overall Severity : {severity}

Risk Score       : {score}/100

Total Words      : {total_words}

Total Findings   : {len(findings)}

Detected Categories:
"""

    if categories:

        for category in categories:

            # Count findings that include this category
            count = len([
                item
                for item in findings
                if category in (
                    item.get("categories") or
                    ([item["category"]] if "category" in item else []) or
                    ([item["type"]] if "type" in item else [])
                )
            ])

            summary += f"\n • {category} ({count})"

    else:

        summary += "\n • No suspicious indicators detected"

    summary += "\n\nKey Evidence:\n"

    if findings:

        shown = findings[:10]

        for item in shown:

            # Get display category from whichever key is present
            if "categories" in item:
                display_cat = ", ".join(item["categories"]).upper()
            elif "category" in item:
                display_cat = item["category"].upper()
            elif "type" in item:
                display_cat = item["type"].upper()
            else:
                display_cat = "UNKNOWN"

            summary += (
                f"\n[{item['timestamp']}s] "
                f"{display_cat} -> "
                f"{item['evidence']}"
            )

        if len(findings) > 10:

            summary += (
                f"\n\n...and "
                f"{len(findings) - 10} "
                f"more findings."
            )

    summary += "\n\nRisk Assessment:\n"

    sev_lower = (severity or "").lower()

    if sev_lower == "critical":
        summary += (
            "Multiple high-risk indicators were detected, "
            "including attempts to gather personal information, "
            "secrecy-related language, private communication "
            "requests, or meeting arrangements. Urgent intervention required."
        )
    elif sev_lower == "high":
        summary += (
            "Significant grooming patterns detected. "
            "Immediate review by a qualified analyst is recommended."
        )
    elif sev_lower == "moderate":
        summary += (
            "Several potentially concerning indicators were "
            "identified. Manual review is recommended."
        )
    elif sev_lower == "low":
        summary += (
            "Minor concerns detected. The conversation may warrant monitoring "
            "but no immediate action is required."
        )
    else:
        summary += (
            "No significant risk indicators were detected "
            "based on current rules."
        )

    return summary