"""
RAG Chatbot — ChromaDB + Ollama Llama 3.1

Enhanced version:
  - Richer, more context-aware prompting
  - Rule-based fast-path: answers factual questions (score, severity, categories,
    speaker breakdown, top findings) instantly from MongoDB without hitting Ollama
  - Source chunk citations in every answer
  - Multi-turn conversation context (last 4 turns kept in memory per report)
  - Streaming-ready (answer returned as a single string for now; stream flag reserved)
  - Graceful degradation: if Ollama is down, rule-based answers still work
"""

import os
import re
import logging
from collections import deque
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Resolve vector store path relative to this file so it works regardless of CWD
_VECTORS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vectors")
_VECTORS_DIR = os.path.normpath(_VECTORS_DIR)

# Per-report conversation history: {report_id: deque([(q, a), ...])}
_CONVERSATION_HISTORY: Dict[int, deque] = {}
_MAX_HISTORY_TURNS = 4  # keep last 4 Q&A pairs per report

# Lazy singletons
_embedding_model = None
_chroma_client   = None
_collection      = None


# ── Lazy loaders ──────────────────────────────────────────────────────────────

def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading SentenceTransformer (all-MiniLM-L6-v2)...")
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("SentenceTransformer loaded.")
    return _embedding_model


def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        os.makedirs(_VECTORS_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=_VECTORS_DIR)
        _collection = _chroma_client.get_or_create_collection(name="transcripts")
        logger.info(f"ChromaDB collection ready at {_VECTORS_DIR}")
    return _collection


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 5) -> List[str]:
    """Split transcript into overlapping sentence groups."""
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks = []
    for i in range(0, len(sentences), max(1, chunk_size - 1)):  # 1-sentence overlap
        chunk = " ".join(sentences[i: i + chunk_size]).strip()
        if chunk:
            chunks.append(chunk)
    return chunks


# ── Store / delete transcript ─────────────────────────────────────────────────

def store_transcript(report_id: int, transcript: str) -> bool:
    """Embed and store transcript chunks in ChromaDB."""
    try:
        if not transcript or not transcript.strip():
            return False

        chunks = chunk_text(transcript)
        if not chunks:
            return False

        model      = _get_embedding_model()
        collection = _get_collection()
        embeddings = model.encode(chunks).tolist()
        ids        = [f"{report_id}_{i}" for i in range(len(chunks))]

        try:
            collection.delete(ids=ids)
        except Exception:
            pass

        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[
                {"report_id": str(report_id), "chunk_id": i, "chunk_total": len(chunks)}
                for i in range(len(chunks))
            ],
        )
        logger.info(f"Stored {len(chunks)} transcript chunks for report #{report_id}")
        return True

    except Exception as e:
        logger.warning(f"store_transcript failed for report #{report_id}: {e}")
        return False


def delete_transcript(report_id: int) -> bool:
    """Delete all transcript chunks from ChromaDB for a given report."""
    try:
        collection = _get_collection()
        collection.delete(where={"report_id": str(report_id)})
        logger.info(f"Deleted ChromaDB chunks for report #{report_id}")
        return True
    except Exception as e:
        logger.warning(f"delete_transcript failed for report #{report_id}: {e}")
        return False


# ── Context retrieval ─────────────────────────────────────────────────────────

def retrieve_context(
    report_id: int,
    question: str,
    top_k: int = 6,
) -> tuple[str, List[str]]:
    """
    Retrieve the most relevant transcript chunks for a question.

    Returns:
        (joined_context_string, list_of_source_chunks)
    """
    try:
        model      = _get_embedding_model()
        collection = _get_collection()

        query_embedding = model.encode(question).tolist()
        results = collection.query(
            query_embeddings=[query_embedding],
            where={"report_id": str(report_id)},
            n_results=top_k,
        )
        docs = results.get("documents", [[]])[0]
        if not docs:
            return "", []
        return "\n\n".join(docs), docs

    except Exception as e:
        logger.warning(f"retrieve_context failed for report #{report_id}: {e}")
        return "", []


# ── Rule-based fast-path ──────────────────────────────────────────────────────

_FACTUAL_PATTERNS = [
    (re.compile(r"\b(risk\s*score|score)\b", re.I),                "risk_score"),
    (re.compile(r"\b(severity|risk\s*level)\b", re.I),              "severity"),
    (re.compile(r"\b(categor|what\s+type|what\s+kind)\b", re.I),    "categories"),
    (re.compile(r"\b(finding|flag|detect)\b", re.I),                "findings"),
    (re.compile(r"\b(summary|summarize|overview|brief)\b", re.I),   "summary"),
    (re.compile(r"\b(speaker|who\s+said|person)\b", re.I),          "speakers"),
    (re.compile(r"\b(word\s*count|how\s+long|length)\b", re.I),     "word_count"),
    (re.compile(r"\b(recommendation|action|next\s+step)\b", re.I),  "recommendation"),
    (re.compile(r"\b(confidence)\b", re.I),                         "confidence"),
]


def _try_rule_based_answer(
    report_id: int,
    question: str,
) -> Optional[str]:
    """
    Attempt to answer factual questions directly from MongoDB without Ollama.
    Returns None if the question requires transcript understanding.
    """
    try:
        from database.mongo import get_analysis, get_findings, get_meeting
        from modules.summarizer import _cat_label
    except Exception:
        return None

    meta     = get_meeting(report_id)
    analysis = get_analysis(report_id) or {}
    findings = get_findings(report_id) or []

    if not meta and not analysis:
        return None

    score    = analysis.get("risk_score", 0)
    severity = analysis.get("severity", "Unknown")
    cats     = analysis.get("category_breakdown") or analysis.get("categories") or {}
    conf     = analysis.get("confidence_stats") or {}
    filename = meta.get("title", "") if meta else ""
    rule_sum = analysis.get("rule_summary", "")
    llm_sum  = analysis.get("llm_summary", "")

    # Determine which factual topic is being asked
    topic = None
    for pattern, t in _FACTUAL_PATTERNS:
        if pattern.search(question):
            topic = t
            break

    if topic == "risk_score":
        return (
            f"**Risk Score for Report #{report_id}**\n\n"
            f"The risk score is **{score:.1f} / 100**, classified as **{severity}**.\n\n"
            f"Score bands: Safe (0–20), Low (21–40), Moderate (41–60), "
            f"High (61–80), Critical (81–100)."
        )

    if topic == "severity":
        return (
            f"**Severity Assessment**\n\n"
            f"This session was classified as **{severity}** with a risk score "
            f"of {score:.1f}/100.\n\n"
            f"Session file: `{filename}`"
        )

    if topic == "categories":
        if not cats:
            return "No risk categories were detected in this session."
        lines = ["**Detected Risk Categories**\n"]
        for cat, count in sorted(cats.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {_cat_label(cat)}: {count} occurrence(s)")
        return "\n".join(lines)

    if topic == "findings":
        if not findings:
            return "No findings were recorded for this report."
        top = sorted(
            findings,
            key=lambda f: f.get("confidence") or f.get("max_confidence") or 0,
            reverse=True,
        )[:8]
        lines = [f"**Top Findings — Report #{report_id}**\n"]
        for i, f in enumerate(top, 1):
            cats_list = f.get("categories") or ([f["category"]] if f.get("category") else ["unknown"])
            cat_str   = ", ".join(_cat_label(c) for c in cats_list)
            c         = (f.get("confidence") or f.get("max_confidence") or 0) * 100
            ev        = (f.get("evidence") or f.get("text") or "")[:120]
            sev_tag   = (f.get("severity") or "").upper()
            lines.append(
                f"  {i}. [{sev_tag}] {cat_str} — {c:.0f}% confidence\n"
                f'     Evidence: "{ev}…"'
            )
        return "\n".join(lines)

    if topic == "summary":
        summary_text = llm_sum or rule_sum
        if not summary_text:
            return "No summary is available for this report yet."
        # Return just the first meaningful block
        return f"**Summary — Report #{report_id}**\n\n{summary_text[:1200]}"

    if topic == "speakers":
        spk_map: Dict[str, int] = {}
        for f in findings:
            spk = f.get("speaker")
            if spk:
                spk_map[spk] = spk_map.get(spk, 0) + 1
        if not spk_map:
            return "Speaker data is not available for this report (speaker diarization may not have run)."
        lines = ["**Speaker Breakdown**\n"]
        for spk, cnt in sorted(spk_map.items(), key=lambda x: x[1], reverse=True):
            lines.append(f"  • {spk}: {cnt} flagged segment(s)")
        return "\n".join(lines)

    if topic == "word_count":
        wc = analysis.get("word_count") or len(
            (analysis.get("transcript") or "").split()
        )
        return (
            f"The transcript for report #{report_id} contains approximately "
            f"**{wc:,} words**."
        )

    if topic == "recommendation":
        from modules.summarizer import _RECOMMENDATION
        sev_key = (severity or "safe").lower()
        rec = _RECOMMENDATION.get(sev_key, _RECOMMENDATION["safe"])
        return f"**Recommended Action**\n\n{rec}"

    if topic == "confidence":
        if not conf:
            return "Confidence statistics are not available for this report."
        return (
            f"**Confidence Statistics**\n\n"
            f"  • Average : {conf.get('average', 0)*100:.1f}%\n"
            f"  • Maximum : {conf.get('maximum', 0)*100:.1f}%\n"
            f"  • Minimum : {conf.get('minimum', 0)*100:.1f}%"
        )

    return None  # fall through to RAG + Ollama


# ── Conversation history ──────────────────────────────────────────────────────

def _get_history(report_id: int) -> List[tuple]:
    return list(_CONVERSATION_HISTORY.get(report_id, deque()))


def _append_history(report_id: int, question: str, answer: str) -> None:
    if report_id not in _CONVERSATION_HISTORY:
        _CONVERSATION_HISTORY[report_id] = deque(maxlen=_MAX_HISTORY_TURNS)
    _CONVERSATION_HISTORY[report_id].append((question, answer))


def clear_history(report_id: int) -> None:
    """Clear conversation history for a report (e.g. on report delete)."""
    _CONVERSATION_HISTORY.pop(report_id, None)


# ── Main answer function ──────────────────────────────────────────────────────

def answer_question(report_id: int, question: str) -> Dict[str, Any]:
    """
    Answer a question about a report using:
      1. Rule-based fast-path (instant, no LLM needed for factual Qs)
      2. RAG + Ollama (semantic search over transcript + LLM generation)

    Returns:
        {
            "question": str,
            "answer":   str,
            "sources":  List[str] | None,   # transcript chunks used
            "method":   "rule" | "rag" | "fallback",
        }
    """
    question = (question or "").strip()
    if not question:
        return {
            "question": question,
            "answer": "Please enter a question.",
            "sources": None,
            "method": "rule",
        }

    # ── 1. Rule-based fast-path ──────────────────────────────────────
    rule_answer = _try_rule_based_answer(report_id, question)
    if rule_answer:
        _append_history(report_id, question, rule_answer)
        return {
            "question": question,
            "answer":   rule_answer,
            "sources":  None,
            "method":   "rule",
        }

    # ── 2. RAG retrieval ─────────────────────────────────────────────
    context, source_chunks = retrieve_context(report_id, question, top_k=6)

    if not context:
        fallback = (
            "I couldn't find relevant transcript content for that question. "
            "Try asking about the risk score, detected categories, findings, "
            "or request a summary."
        )
        return {
            "question": question,
            "answer":   fallback,
            "sources":  None,
            "method":   "fallback",
        }

    # ── 3. Build multi-turn prompt ───────────────────────────────────
    history = _get_history(report_id)
    history_block = ""
    if history:
        history_lines = []
        for q, a in history:
            history_lines.append(f"User: {q}")
            # Truncate long previous answers in history
            a_preview = a[:300] + "…" if len(a) > 300 else a
            history_lines.append(f"Assistant: {a_preview}")
        history_block = "CONVERSATION HISTORY (most recent first):\n" + "\n".join(
            reversed(history_lines)
        ) + "\n\n"

    # Fetch report metadata for context enrichment
    try:
        from database.mongo import get_analysis, get_meeting
        meta     = get_meeting(report_id)     or {}
        analysis = get_analysis(report_id)    or {}
        severity = analysis.get("severity",   "Unknown")
        score    = analysis.get("risk_score",  0)
        filename = meta.get("title",           f"Report #{report_id}")
    except Exception:
        severity = "Unknown"
        score    = 0
        filename = f"Report #{report_id}"

    prompt = f"""You are a child safeguarding analyst assistant for the MelodyWings platform.
Your job is to help safety reviewers investigate flagged session reports.

REPORT CONTEXT:
  File     : {filename}
  Severity : {severity}
  Score    : {score:.1f}/100
  Report ID: #{report_id}

{history_block}RELEVANT TRANSCRIPT EXCERPTS (from semantic search):
---
{context}
---

QUESTION: {question}

INSTRUCTIONS:
- Answer using ONLY the transcript excerpts and report context above.
- Do NOT invent information not present in the excerpts.
- If the answer is not in the excerpts, say so clearly and suggest what information IS available.
- Quote the transcript directly when it supports your answer (use quotation marks).
- Be concise, professional, and factual — this is a safeguarding tool.
- If the question asks about patterns or behaviour, explain what the evidence shows.
- Use bullet points for multi-part answers.
- Do not hedge excessively — give direct, actionable answers.
"""

    # ── 4. Call Ollama ───────────────────────────────────────────────
    try:
        import ollama
        response = ollama.chat(
            model="llama3.1",
            messages=[{"role": "user", "content": prompt}],
            options={"temperature": 0.2, "num_predict": 512},
        )
        answer = response["message"]["content"].strip()

        # Validate quotes against transcript
        try:
            from modules.llm_output_validator import validate_llm_output
            full_transcript = "\n\n".join(source_chunks)
            validation = validate_llm_output(answer, full_transcript, strict=False)
            answer = validation["output"]
        except Exception:
            pass

        _append_history(report_id, question, answer)
        return {
            "question": question,
            "answer":   answer,
            "sources":  source_chunks[:3],  # return top 3 source chunks
            "method":   "rag",
        }

    except Exception as e:
        logger.warning(f"Ollama unavailable for report #{report_id}: {e}")

        # ── 5. Graceful fallback: return raw context ─────────────────
        fallback = (
            f"Ollama is currently unavailable. Here are the most relevant "
            f"transcript excerpts for your question:\n\n"
        )
        for i, chunk in enumerate(source_chunks[:3], 1):
            fallback += f"[Excerpt {i}]\n{chunk}\n\n"

        return {
            "question": question,
            "answer":   fallback.strip(),
            "sources":  source_chunks[:3],
            "method":   "fallback",
        }


# ── Debug helpers ─────────────────────────────────────────────────────────────

def transcript_exists(report_id: int) -> bool:
    """Return True if ChromaDB has chunks for this report."""
    try:
        collection = _get_collection()
        results = collection.get(where={"report_id": str(report_id)})
        return len(results.get("ids", [])) > 0
    except Exception:
        return False


def get_conversation_history(report_id: int) -> List[Dict[str, str]]:
    """Return conversation history as a list of {question, answer} dicts."""
    return [
        {"question": q, "answer": a}
        for q, a in _get_history(report_id)
    ]
