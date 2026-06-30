# ── Backend Dockerfile ─────────────────────────────────────────────────────────
# Multi-stage build: dependencies first (cached), then app code.

FROM python:3.11-slim AS base

# System deps for audio processing (ffmpeg), PDF generation, and general build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    libsndfile1 \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Dependencies stage ────────────────────────────────────────────────────────
FROM base AS deps

COPY requirements.txt .

# Install PyTorch CPU-only first (saves ~1.5 GB vs full CUDA build)
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir torch==2.6.0 --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir -r requirements.txt

# ── Application stage ─────────────────────────────────────────────────────────
FROM deps AS app

# Cache HuggingFace / SentenceTransformer models inside the image so containers
# don't download them on every cold start (~5 min) and don't hit the
# "1_Pooling/config.json not found" partial-download error at runtime.
ENV HF_HOME=/app/.cache/huggingface \
    SENTENCE_TRANSFORMERS_HOME=/app/.cache/sentence-transformers \
    TRANSFORMERS_OFFLINE=0

# Pre-download the models used by the detection pipeline + chatbot RAG.
# The fine-tuned grooming model is downloaded from GCS (too large for source upload).
# SentenceTransformer is fetched from HuggingFace.
RUN pip install --no-cache-dir gcloud-aio-storage 2>/dev/null || true && \
    python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"

# Download fine-tuned grooming NLI model from GCS bucket
RUN mkdir -p models/grooming-nli-finetuned && \
    for f in model.safetensors config.json tokenizer.json tokenizer_config.json special_tokens_map.json vocab.txt; do \
      curl -sL "https://storage.googleapis.com/melodywings-ml-models/grooming-nli-finetuned/$f" \
        -o "models/grooming-nli-finetuned/$f"; \
    done && \
    ls -la models/grooming-nli-finetuned/model.safetensors && \
    echo "Fine-tuned model downloaded from GCS"

# Create a non-root user for security
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy application code
COPY . .

# Fix Windows line endings in shell scripts (CRLF -> LF)
RUN sed -i 's/\r$//' start.sh && \
    mkdir -p uploads logs reports static .cache && \
    chmod +x start.sh && \
    chown -R appuser:appuser /app

# Fix model path for Linux (backslash in .env won't work)
ENV FINETUNED_MODEL_PATH=models/grooming-nli-finetuned

# Switch to non-root user
USER appuser

# Expose the API port
EXPOSE 8000

# Healthcheck — confirms the FastAPI server is responsive
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Default command: run FastAPI + Celery worker via start script
CMD ["bash", "start.sh"]
