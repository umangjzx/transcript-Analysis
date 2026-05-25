import os
from dotenv import load_dotenv

load_dotenv(override=True)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")

DATABASE_URL = "sqlite:///analysis.db"

ALLOWED_EXTENSIONS = [
    ".mp3",
    ".wav",
    ".m4a",
    ".aac",
    ".ogg"
]

# ── Email / SMTP ──────────────────────────────────────────────────────────────
SMTP_HOST        = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT        = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER        = os.getenv("SMTP_USER", "")
SMTP_PASSWORD    = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_NAME   = os.getenv("SMTP_FROM_NAME", "AuraSafety")
ALERT_RECIPIENTS = os.getenv("ALERT_RECIPIENTS", "")
APP_URL          = os.getenv("APP_URL", "http://localhost:5173")

# ── MongoDB ───────────────────────────────────────────────────────────────────
MONGO_URI     = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "audio_safety_db")

# ── AWS S3 ────────────────────────────────────────────────────────────────────
AWS_ACCESS_KEY_ID     = os.getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION            = os.getenv("AWS_REGION", "us-east-1")
S3_BUCKET             = os.getenv("S3_BUCKET_NAME", "")

# ── Speaker Diarization ───────────────────────────────────────────────────────
# HuggingFace token for pyannote/speaker-diarization-3.1
# Leave blank to run without diarization.
HF_TOKEN = os.getenv("HF_TOKEN", "")

# ── ML Classifier ─────────────────────────────────────────────────────────────
# Set to "true" once the ~400 MB distilbert-mnli model has been downloaded.
ENABLE_ML_CLASSIFIER = os.getenv("ENABLE_ML_CLASSIFIER", "false").lower() == "true"

# ── Speaker Diarization ───────────────────────────────────────────────────────
# Set to "true" to enable pyannote speaker diarization.
# Adds ~90 s per 3-min file on CPU — keep false for fast analysis.
ENABLE_DIARIZATION = os.getenv("ENABLE_DIARIZATION", "false").lower() == "true"

# ── Upload limits ─────────────────────────────────────────────────────────────
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "200"))

# ── CORS ──────────────────────────────────────────────────────────────────────
# Comma-separated list of allowed frontend origins.
# Default allows the Vite dev server. Change for production.
ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173"
)

# ── Authentication ─────────────────────────────────────────────────────────────
# Set a strong random string to enable API key auth.
# Leave blank to disable (local dev only).
API_KEY = os.getenv("API_KEY", "")

# ── Upload cleanup ─────────────────────────────────────────────────────────────
# Uploaded audio files older than this many hours are auto-deleted. 0 = disabled.
UPLOAD_TTL_HOURS = int(os.getenv("UPLOAD_TTL_HOURS", "24"))

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
