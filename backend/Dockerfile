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

# Copy application code
COPY . .

# Create required directories
RUN mkdir -p uploads logs reports static

# Fix model path for Linux (backslash in .env won't work)
ENV FINETUNED_MODEL_PATH=models/grooming-nli-finetuned

# Expose the API port
EXPOSE 8000

# Default command: run the FastAPI server (no --reload in production)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
