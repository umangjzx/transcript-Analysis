from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer
)

from reportlab.lib.styles import (
    getSampleStyleSheet
)

import os


def generate_pdf_report(

        report_id,

        filename,

        severity,

        risk_score,

        findings,

        summary

):

    os.makedirs(
        "reports",
        exist_ok=True
    )

    pdf_path = (
        f"reports/report_{report_id}.pdf"
    )

    doc = SimpleDocTemplate(
        pdf_path
    )

    styles = getSampleStyleSheet()

    content = []

    content.append(

        Paragraph(
            "Transcript Analysis Report",
            styles["Title"]
        )
    )

    content.append(
        Spacer(1, 12)
    )

    content.append(

        Paragraph(
            f"File: {filename}",
            styles["Normal"]
        )
    )

    content.append(

        Paragraph(
            f"Severity: {severity}",
            styles["Normal"]
        )
    )

    content.append(

        Paragraph(
            f"Risk Score: {risk_score}",
            styles["Normal"]
        )
    )

    content.append(
        Spacer(1, 12)
    )

    content.append(

        Paragraph(
            "Summary",
            styles["Heading2"]
        )
    )

    content.append(

        Paragraph(
            summary.replace(
                "\n",
                "<br/>"
            ),
            styles["Normal"]
        )
    )

    content.append(
        Spacer(1, 12)
    )

    content.append(

        Paragraph(
            "Evidence",
            styles["Heading2"]
        )
    )

    for item in findings:

        # Get display category from whichever key is present
        if "categories" in item:
            display_cat = ", ".join(item["categories"])
        elif "category" in item:
            display_cat = item["category"]
        elif "type" in item:
            display_cat = item["type"]
        else:
            display_cat = "unknown"

        content.append(

            Paragraph(

                f"[{item['timestamp']}s] "
                f"{display_cat} : "
                f"{item['evidence']}",

                styles["Normal"]
            )
        )

    doc.build(content)

    return pdf_path