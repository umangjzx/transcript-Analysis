import ollama


def generate_llm_summary(

        transcript,

        findings,

        risk_score,

        severity
):

    prompt = f"""

Analyze this transcript.

Risk Score:
{risk_score}

Severity:
{severity}

Transcript:

{transcript}

Return:

1 Executive Summary

2 Key Concerns

3 High Risk Behaviors

4 Recommended Action

"""

    try:

        response = ollama.chat(

            model="llama3.1",

            messages=[

                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        return response["message"]["content"]

    except Exception as e:

        return f"LLM Summary Failed: {str(e)}"