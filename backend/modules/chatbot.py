import re

import chromadb
import ollama

from sentence_transformers import (
    SentenceTransformer
)

# --------------------------------------------------
# EMBEDDING MODEL
# --------------------------------------------------

embedding_model = SentenceTransformer(
    "all-MiniLM-L6-v2"
)

# --------------------------------------------------
# CHROMADB
# --------------------------------------------------

client = chromadb.PersistentClient(
    path="./vectors"
)

collection = client.get_or_create_collection(
    name="transcripts"
)

# --------------------------------------------------
# CHUNK TRANSCRIPT
# --------------------------------------------------

def chunk_text(
        text,
        chunk_size=5
):
    """
    Split transcript into sentence groups.
    Better than fixed character chunking.
    """

    if not text:
        return []

    sentences = re.split(
        r'(?<=[.!?])\s+',
        text
    )

    chunks = []

    for i in range(
            0,
            len(sentences),
            chunk_size
    ):

        chunk = " ".join(
            sentences[i:i + chunk_size]
        ).strip()

        if chunk:
            chunks.append(chunk)

    return chunks


# --------------------------------------------------
# STORE TRANSCRIPT
# --------------------------------------------------

def store_transcript(
        report_id,
        transcript
):

    try:

        if not transcript:
            return False

        transcript = transcript.strip()

        if not transcript:
            return False

        chunks = chunk_text(
            transcript
        )

        if not chunks:
            return False

        embeddings = (
            embedding_model
            .encode(chunks)
            .tolist()
        )

        ids = [

            f"{report_id}_{i}"

            for i in range(
                len(chunks)
            )
        ]

        # Remove previous chunks
        try:

            collection.delete(
                ids=ids
            )

        except Exception:
            pass

        collection.add(

            ids=ids,

            documents=chunks,

            embeddings=embeddings,

            metadatas=[

                {
                    "report_id": str(report_id),
                    "chunk_id": i
                }

                for i in range(
                    len(chunks)
                )
            ]
        )

        return True

    except Exception as e:

        print(
            f"Store Transcript Error: {e}"
        )

        return False


# --------------------------------------------------
# RETRIEVE CONTEXT
# --------------------------------------------------

def retrieve_context(
        report_id,
        question,
        top_k=5
):

    try:

        query_embedding = (
            embedding_model
            .encode(question)
            .tolist()
        )

        results = collection.query(

            query_embeddings=[
                query_embedding
            ],

            where={
                "report_id": str(report_id)
            },

            n_results=top_k
        )

        documents = results.get(
            "documents",
            []
        )

        if not documents:
            return ""

        docs = documents[0]

        if not docs:
            return ""

        return "\n\n".join(
            docs
        )

    except Exception as e:

        print(
            f"Context Retrieval Error: {e}"
        )

        return ""


# --------------------------------------------------
# QUESTION ANSWERING
# --------------------------------------------------

def answer_question(
        report_id,
        question
):

    context = retrieve_context(

        report_id,

        question
    )

    if not context:

        return {

            "question": question,

            "answer":
            "No relevant transcript content found for this report."
        }

    prompt = f"""
You are an investigation assistant.

Use ONLY the transcript context below.

Transcript Context:

{context}

Question:

{question}

Instructions:

- Answer ONLY using the transcript.
- Do not invent information.
- If information is unavailable,
  explicitly state that.
- Use bullet points if useful.
- Quote transcript content when appropriate.
- Be concise and factual.
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

        answer = (
            response["message"]
            ["content"]
        )

        return {

            "question": question,

            "answer": answer
        }

    except Exception as e:

        return {

            "question": question,

            "answer":
            f"Ollama Error: {str(e)}"
        }


# --------------------------------------------------
# DEBUG HELPER
# --------------------------------------------------

def transcript_exists(
        report_id
):

    try:

        results = collection.get(

            where={
                "report_id": str(report_id)
            }
        )

        return len(
            results.get(
                "ids",
                []
            )
        ) > 0

    except Exception:

        return False