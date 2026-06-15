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

# Create a non-root user for security
RUN adduser --disabled-password --gecos '' --uid 1001 appuser

# Copy application code
COPY . .

# Create required directories and set ownership
RUN mkdir -p uploads logs reports static && \
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

# Default command: run the FastAPI server (no --reload in production)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
