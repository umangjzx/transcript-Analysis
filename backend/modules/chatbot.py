"""
RAG Chatbot — ChromaDB + Ollama Llama 3.1

Fixes applied:
- SentenceTransformer and ChromaDB are lazy-loaded (not at import time)
- ChromaDB path is resolved relative to this file, not the CWD
- print() replaced with logger
"""

import os
import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Resolve vector store path relative to this file so it works regardless of CWD
_VECTORS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vectors")
_VECTORS_DIR = os.path.normpath(_VECTORS_DIR)

# Lazy singletons — loaded on first use, not at import time
_embedding_model = None
_chroma_client = None
_collection = None


def _get_embedding_model():
    global _embedding_model
    if _embedding_model is None:
        logger.info("Loading SentenceTransformer (all-MiniLM-L6-v2)...")
        from sentence_transformers import SentenceTransformer
        _embedding_model = SentenceTransformer("all-MiniLM-L6-v2")
        logger.info("SentenceTransformer loaded")
    return _embedding_model


def _get_collection():
    global _chroma_client, _collection
    if _collection is None:
        import chromadb
        os.makedirs(_VECTORS_DIR, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=_VECTORS_DIR)
        _collection = _chroma_client.get_or_create_collection(name="transcripts")
        logger.info(f"ChromaDB collection loaded from {_VECTORS_DIR}")
    return _collection


# ── Chunking ──────────────────────────────────────────────────────────────────

def chunk_text(text: str, chunk_size: int = 5):
    """Split transcript into sentence groups of chunk_size sentences."""
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    for i in range(0, len(sentences), chunk_size):
        chunk = " ".join(sentences[i : i + chunk_size]).strip()
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

        model = _get_embedding_model()
        collection = _get_collection()

        embeddings = model.encode(chunks).tolist()
        ids = [f"{report_id}_{i}" for i in range(len(chunks))]

        # Remove previous chunks for this report
        try:
            collection.delete(ids=ids)
        except Exception:
            pass

        collection.add(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=[{"report_id": str(report_id), "chunk_id": i} for i in range(len(chunks))],
        )
        logger.info(f"Stored {len(chunks)} transcript chunks for report #{report_id}")
        return True

    except Exception as e:
        logger.warning(f"store_transcript failed for report #{report_id}: {e}")
        return False


def delete_transcript(report_id: int) -> bool:
    """
    Delete all transcript chunks for a report from ChromaDB.
    Safe to call even if Chroma is not available.
    """
    try:
        collection = _get_collection()
        collection.delete(where={"report_id": str(report_id)})
        logger.info(f"Deleted transcript chunks from ChromaDB for report #{report_id}")
        return True
    except Exception as e:
        logger.warning(f"delete_transcript failed for report #{report_id}: {e}")
        return False


# ── Retrieve context ──────────────────────────────────────────────────────────

def retrieve_context(report_id: int, question: str, top_k: int = 5) -> str:
    """Retrieve the most relevant transcript chunks for a question."""
    try:
        model = _get_embedding_model()
        collection = _get_collection()

        query_embedding = model.encode(question).tolist()
        results = collection.query(
            query_embeddings=[query_embedding],
            where={"report_id": str(report_id)},
            n_results=top_k,
        )
        documents = results.get("documents", [])
        if not documents or not documents[0]:
            return ""
        return "\n\n".join(documents[0])

    except Exception as e:
        logger.warning(f"retrieve_context failed for report #{report_id}: {e}")
        return ""


# ── Answer question ───────────────────────────────────────────────────────────

def answer_question(report_id: int, question: str) -> dict:
    """Answer a question about a report using RAG + Ollama."""
    context = retrieve_context(report_id, question)

    if not context:
        return {
            "question": question,
            "answer": "No relevant transcript content found for this report.",
        }

    prompt = f"""You are an investigation assistant.

Use ONLY the transcript context below to answer the question.

Transcript Context:
{context}

Question:
{question}

Instructions:
- Answer ONLY using the transcript.
- Do not invent information.
- If the information is not in the transcript, say so explicitly.
- Use bullet points if useful.
- Quote transcript content when appropriate.
- Be concise and factual.
"""

    try:
        import ollama
        response = ollama.chat(
            model="llama3.1",
            messages=[{"role": "user", "content": prompt}],
        )
        return {
            "question": question,
            "answer": response["message"]["content"],
        }

    except Exception as e:
        logger.warning(f"Ollama chat failed for report #{report_id}: {e}")
        return {
            "question": question,
            "answer": f"Ollama is unavailable: {e}",
        }


# ── Debug helper ──────────────────────────────────────────────────────────────

def transcript_exists(report_id: int) -> bool:
    """Return True if transcript chunks exist in ChromaDB for this report."""
    try:
        collection = _get_collection()
        results = collection.get(where={"report_id": str(report_id)})
        return len(results.get("ids", [])) > 0
    except Exception:
        return False
