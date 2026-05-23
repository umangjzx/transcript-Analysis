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
S3_BUCKET             = os.getenv("S3_BUCKET", "")

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
