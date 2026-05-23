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
    severity_dist = {}
    context_type_dist = {}
    speaker_dist = {}
    confidences = []
    findings_timeline = []  # [{timestamp, confidence, category}]

    for item in findings:
        # ── Categories ──────────────────────────────────────────────
        item_categories = []
        if "categories" in item:
            item_categories = item["categories"]
        elif "category" in item:
            item_categories = [item["category"]]
        elif "type" in item:
            item_categories = [item["type"]]

        for cat in item_categories:
            if cat:
                categories[cat] = categories.get(cat, 0) + 1

        # ── Severity distribution ────────────────────────────────────
        sev = item.get("severity")
        if sev:
            severity_dist[sev] = severity_dist.get(sev, 0) + 1

        # ── Context type distribution ────────────────────────────────
        ctx = item.get("context_type") or (
            item.get("context", {}).get("primary")
            if isinstance(item.get("context"), dict) else None
        )
        if ctx:
            context_type_dist[ctx] = context_type_dist.get(ctx, 0) + 1

        # ── Speaker distribution ─────────────────────────────────────
        speaker = item.get("speaker")
        if speaker:
            speaker_dist[speaker] = speaker_dist.get(speaker, 0) + 1

        # ── Confidence collection ────────────────────────────────────
        conf = item.get("confidence") or item.get("max_confidence")
        if conf is not None:
            confidences.append(float(conf))

        # ── Timeline entry ───────────────────────────────────────────
        ts = item.get("timestamp")
        primary_cat = item_categories[0] if item_categories else "unknown"
        if ts is not None and conf is not None:
            findings_timeline.append({
                "timestamp": round(float(ts), 2),
                "confidence": round(float(conf), 4),
                "category": primary_cat,
                "severity": sev or "unknown",
            })

    # ── Confidence stats ─────────────────────────────────────────────
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
        max_conf = max(confidences)
        min_conf = min(confidences)
        # Histogram buckets: 0-25, 25-50, 50-75, 75-100
        conf_histogram = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}
        for c in confidences:
            pct = c * 100
            if pct <= 25:
                conf_histogram["0-25"] += 1
            elif pct <= 50:
                conf_histogram["25-50"] += 1
            elif pct <= 75:
                conf_histogram["50-75"] += 1
            else:
                conf_histogram["75-100"] += 1
    else:
        avg_conf = max_conf = min_conf = 0.0
        conf_histogram = {"0-25": 0, "25-50": 0, "50-75": 0, "75-100": 0}

    # ── ML agreement stats ───────────────────────────────────────────
    ml_total = 0
    ml_agreed = 0
    ml_disagreed = 0
    for item in findings:
        ml = item.get("ml") or {}
        if ml and not ml.get("error"):
            ml_total += 1
            if ml.get("agreement") is True:
                ml_agreed += 1
            elif ml.get("agreement") is False:
                ml_disagreed += 1

    ml_agreement_rate = round(ml_agreed / ml_total, 4) if ml_total > 0 else None

    # Sort timeline by timestamp
    findings_timeline.sort(key=lambda x: x["timestamp"])

    return {
        "word_count": len(transcript.split()),
        "character_count": len(transcript),
        "finding_count": len(findings),
        "unique_categories": len(categories),

        # Category counts
        "categories": categories,
        "category_breakdown": categories,  # alias for frontend compat

        # Severity / context / speaker distributions
        "severity_distribution": severity_dist,
        "context_type_distribution": context_type_dist,
        "speaker_distribution": speaker_dist,

        # Confidence analytics
        "confidence_stats": {
            "average": round(avg_conf, 4),
            "maximum": round(max_conf, 4),
            "minimum": round(min_conf, 4),
        },
        "confidence_histogram": conf_histogram,

        # ML agreement
        "ml_stats": {
            "total_with_ml": ml_total,
            "agreed": ml_agreed,
            "disagreed": ml_disagreed,
            "agreement_rate": ml_agreement_rate,
        },

        # Findings timeline (for scatter/line chart)
        "findings_timeline": findings_timeline,

        # High-confidence count
        "high_confidence_count": sum(1 for c in confidences if c >= 0.7),

        "severity": severity,
        "risk_score": risk_score,
    }