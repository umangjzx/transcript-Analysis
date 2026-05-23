from modules.grooming_detector import detect_grooming


def analyze_timeline(timeline):

    findings = []

    seen = set()

    for segment in timeline:

        text = segment["text"]

        segment_findings = detect_grooming(text)

        for finding in segment_findings:

            # Avoid duplicate category detections
            key = (
                segment["start"],
                finding["type"]
            )

            if key in seen:
                continue

            seen.add(key)

            findings.append({

                "timestamp": segment["start"],

                "end": segment["end"],

                "type": finding["type"],

                "phrase": finding["phrase"],

                "evidence": text
            })

    return findings