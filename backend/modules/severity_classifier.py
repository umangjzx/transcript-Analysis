def classify_severity(score):

    if score >= 80:
        return "CRITICAL"

    elif score >= 40:
        return "MEDIUM"

    return "LOW"