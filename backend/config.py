import os

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

os.makedirs(UPLOAD_FOLDER, exist_ok=True)