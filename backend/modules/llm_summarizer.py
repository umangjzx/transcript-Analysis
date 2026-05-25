"""
LLM Summarizer — Ollama Llama 3.1

Fixes applied:
- findings are now included in the prompt (were silently ignored before)
- long transcripts are truncated to ~3000 words to stay within context window
- graceful fallback if Ollama is not running
"""

import logging
from typing import List, Dict, Any

import ollama

logger = logging.getLogger(__name__)

# Maximum words of transcript to send to the LLM.
# Llama 3.1 8B has an 8k token context; ~3000 words ≈ 4000 tokens,
# leaving room for the prompt template and the response.
_MAX_TRANSCRIPT_WORDS = 3000


def _truncate_transcript(transcript: str, max_words: int = _MAX_TRANSCRIPT_WORDS) -> str:
    """Truncate transcript to max_words, appending a note if truncated."""
    words = transcript.split()
    if len(words) <= max_words:
        return transcript
    truncated = " ".join(words[:max_words])
    return truncated + f"\n\n[... transcript truncated at {max_words} words for LLM context limit ...]"


def _format_findings(findings: List[Dict[str, Any]], max_findings: int = 10) -> str:
    """Format top findings into a compact text block for the prompt."""
    if not findings:
        return "No findings detected."

    # Sort by confidence descending, take top N
    sorted_findings = sorted(
        findings,
        key=lambda f: f.get("confidence") or f.get("max_confidence") or 0,
        reverse=True,
    )[:max_findings]

    lines = []
    for i, f in enumerate(sorted_findings, 1):
        cats = f.get("categories") or ([f["category"]] if f.get("category") else ["unknown"])
        cat_str = ", ".join(cats)
        conf = f.get("confidence") or f.get("max_confidence") or 0
        sev = f.get("severity", "unknown")
        evidence = (f.get("evidence") or f.get("text") or "")[:120]
        lines.append(
            f"{i}. [{cat_str.upper()}] severity={sev}, confidence={conf:.0%}\n"
            f'   Evidence: "{evidence}"'
        )

    return "\n".join(lines)


def generate_llm_summary(
    transcript: str,
    findings: List[Dict[str, Any]],
    risk_score: float,
    severity: str,
) -> str:
    """
    Generate an AI executive summary using Ollama Llama 3.1.

    Args:
        transcript: Full conversation transcript.
        findings:   Grouped findings from the detection pipeline.
        risk_score: Numeric risk score (0–100).
        severity:   Severity label (Safe / Low / Moderate / High / Critical).

    Returns:
        Formatted summary string, or an error message if Ollama is unavailable.
    """
    truncated_transcript = _truncate_transcript(transcript)
    findings_text = _format_findings(findings)

    prompt = f"""You are a child safety analyst reviewing a flagged conversation transcript.

RISK SCORE: {risk_score:.0f}/100
SEVERITY: {severity}

TOP DETECTED FINDINGS ({len(findings)} total):
{findings_text}

TRANSCRIPT (may be truncated):
{truncated_transcript}

Provide a concise professional analysis with these four sections:

1. EXECUTIVE SUMMARY
   One paragraph summarising the overall risk level and nature of the conversation.

2. KEY CONCERNS
   Bullet list of the most significant risk indicators found.

3. HIGH-RISK BEHAVIOURS
   Specific behaviours or patterns that are most concerning, with brief quotes from the transcript.

4. RECOMMENDED ACTION
   Clear, actionable next steps for the reviewing analyst.

Be factual and concise. Do not invent information not present in the transcript or findings.
"""

    try:
        response = ollama.chat(
            model="llama3.1",
            messages=[{"role": "user", "content": prompt}],
        )
        return response["message"]["content"]

    except Exception as e:
        logger.warning(f"LLM summary failed (Ollama may not be running): {e}")
        return f"LLM Summary unavailable — Ollama error: {e}"
