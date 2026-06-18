"""
Upload Routes (unversioned)
===========================
Prefix: none (root-level)

Endpoints:
  POST /analyze           → upload audio file, start background analysis
  POST /analyze/video     → upload video file, extract audio, analyze
  POST /analyze/transcript → submit transcript text directly
"""

import os
import uuid
import logging
from typing import Dict, Any

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Request

from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS, ALLOWED_VIDEO_EXTENSIONS
from database.mongo import (
    save_meeting_metadata, next_meeting_id, audit_log,
)
from modules.virus_scanner import scan_file as virus_scan_file

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Upload & Analysis"])

MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_MB", "200")) * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = int(os.getenv("MAX_VIDEO_UPLOAD_MB", "500")) * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024  # 1 MB


# ── Background dispatchers ────────────────────────────────────────────────────

def _dispatch_audio(record_id: int, filepath: str, filename: str):
    from tasks.analysis_tasks import run_audio_analysis
    run_audio_analysis.delay(record_id, filepath, filename)


def _dispatch_video(record_id: int, audio_filepath: str, filename: str):
    from tasks.analysis_tasks import run_video_analysis
    run_video_analysis.delay(record_id, audio_filepath, filename)


def _dispatch_transcript(record_id: int, transcript: str, filename: str):
    from tasks.analysis_tasks import run_transcript_analysis
    run_transcript_analysis.delay(record_id, transcript, filename)


# ── POST /analyze ─────────────────────────────────────────────────────────────

@router.post("/analyze")
async def analyze_audio(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload an audio file and start background analysis via Celery."""
    from modules.disk_space_checker import check_disk_space

    disk_check = check_disk_space()
    if not disk_check["ok"]:
        raise HTTPException(
            status_code=507,
            detail=f"Insufficient disk space: {disk_check['free_mb']:.0f} MB available, "
                   f"need {disk_check['required_mb']} MB.",
        )

    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported audio format '{extension}'. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
        )

    safe_disk_name = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    filepath = os.path.join(UPLOAD_FOLDER, safe_disk_name)
    file_size = 0

    try:
        with open(filepath, "wb") as buffer:
            while True:
                chunk = await file.read(size=_CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_UPLOAD_BYTES:
                    buffer.close()
                    try:
                        os.remove(filepath)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size is {MAX_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        try:
            os.remove(filepath)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save uploaded file: {str(e)}")

    # Virus scan
    scan_result = virus_scan_file(filepath)
    if not scan_result["safe"]:
        os.remove(filepath)
        raise HTTPException(
            status_code=422,
            detail=f"File rejected: virus detected ({scan_result['threat']})",
        )

    original_filename = file.filename or safe_disk_name
    record_id = next_meeting_id()
    save_meeting_metadata(
        meeting_id=record_id,
        filename=original_filename,
        file_size_bytes=file_size,
        status="PROCESSING",
    )

    background_tasks.add_task(_dispatch_audio, record_id, filepath, original_filename)
    audit_log("file_uploaded", meeting_id=record_id, user_action="upload",
              details={"filename": original_filename, "size_bytes": file_size})
    logger.info(f"[#{record_id}] Upload accepted: {original_filename} ({file_size//1024} KB)")

    return {"id": record_id, "filename": original_filename,
            "status": "PROCESSING", "message": "Analysis started in background"}


# ── POST /analyze/video ───────────────────────────────────────────────────────

@router.post("/analyze/video")
async def analyze_video(background_tasks: BackgroundTasks, file: UploadFile = File(...)):
    """Upload a video file, extract audio, then analyze."""
    from modules.disk_space_checker import check_disk_space

    disk_check = check_disk_space()
    if not disk_check["ok"]:
        raise HTTPException(
            status_code=507,
            detail=f"Insufficient disk space: {disk_check['free_mb']:.0f} MB available, "
                   f"need {disk_check['required_mb']} MB.",
        )

    extension = os.path.splitext(file.filename or "")[1].lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported video format '{extension}'. Allowed: {', '.join(ALLOWED_VIDEO_EXTENSIONS)}",
        )

    safe_disk_name = f"{uuid.uuid4().hex}{extension}"
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    video_filepath = os.path.join(UPLOAD_FOLDER, safe_disk_name)
    original_filename = file.filename or safe_disk_name
    file_size = 0

    try:
        with open(video_filepath, "wb") as buffer:
            while True:
                chunk = await file.read(size=_CHUNK_SIZE)
                if not chunk:
                    break
                file_size += len(chunk)
                if file_size > MAX_VIDEO_UPLOAD_BYTES:
                    buffer.close()
                    try:
                        os.remove(video_filepath)
                    except Exception:
                        pass
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Maximum allowed size for video is {MAX_VIDEO_UPLOAD_BYTES // (1024*1024)} MB.",
                    )
                buffer.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        try:
            os.remove(video_filepath)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f"Failed to save video file: {str(e)}")

    # Virus scan
    scan_result = virus_scan_file(video_filepath)
    if not scan_result["safe"]:
        try:
            os.remove(video_filepath)
        except Exception:
            pass
        raise HTTPException(
            status_code=422,
            detail=f"File rejected: virus detected ({scan_result['threat']})",
        )

    # Extract audio
    audio_disk_name = f"{uuid.uuid4().hex}.wav"
    audio_filepath = os.path.join(UPLOAD_FOLDER, audio_disk_name)

    try:
        from modules.transcriber import extract_audio_from_video
        extract_audio_from_video(video_filepath, audio_filepath)
    except Exception as e:
        try:
            os.remove(video_filepath)
        except Exception:
            pass
        raise HTTPException(status_code=422, detail=f"Could not extract audio from video: {str(e)}")

    # Delete video immediately
    try:
        os.remove(video_filepath)
        logger.info(f"Video file deleted after extraction: {video_filepath}")
    except Exception as _e:
        logger.warning(f"Could not delete video file: {_e}")

    record_id = next_meeting_id()
    save_meeting_metadata(
        meeting_id=record_id,
        filename=original_filename,
        file_size_bytes=file_size,
        status="PROCESSING",
    )

    background_tasks.add_task(_dispatch_video, record_id, audio_filepath, original_filename)
    audit_log("video_uploaded", meeting_id=record_id, user_action="upload",
              details={"filename": original_filename, "size_bytes": file_size})
    logger.info(f"[#{record_id}] Video upload accepted: {original_filename} ({file_size // 1024} KB)")

    return {"id": record_id, "filename": original_filename,
            "status": "PROCESSING", "message": "Video audio extracted, analysis started in background"}


# ── POST /analyze/transcript ──────────────────────────────────────────────────

@router.post("/analyze/transcript")
async def analyze_transcript_text(background_tasks: BackgroundTasks, request: Request):
    """Submit a plain-text transcript (JSON body or .txt file upload)."""
    content_type = request.headers.get("content-type", "")

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file is None:
            raise HTTPException(status_code=400, detail="No file field found in form data.")

        original_filename = uploaded_file.filename or "transcript_input.txt"
        ext = os.path.splitext(original_filename)[1].lower()
        if ext not in (".txt",):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{ext}'. Only .txt files are accepted.",
            )

        raw_bytes = await uploaded_file.read()
        if len(raw_bytes) > 10 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Text file too large. Maximum 10 MB.")

        try:
            transcript_text = raw_bytes.decode("utf-8").strip()
        except UnicodeDecodeError:
            try:
                transcript_text = raw_bytes.decode("latin-1").strip()
            except Exception:
                raise HTTPException(status_code=422, detail="Could not decode file as text.")

        if not transcript_text:
            raise HTTPException(status_code=400, detail="The uploaded file is empty.")
    else:
        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Request body must be valid JSON.")

        transcript_text = body.get("transcript", "")
        # Handle case where transcript is not a string (e.g. nested JSON parsing)
        if not isinstance(transcript_text, str):
            if isinstance(transcript_text, (list, dict)):
                import json as _json
                transcript_text = _json.dumps(transcript_text)
            else:
                transcript_text = str(transcript_text) if transcript_text else ""
        transcript_text = transcript_text.strip()
        if not transcript_text:
            raise HTTPException(status_code=400, detail="'transcript' field is required and must not be empty.")
        original_filename = body.get("filename", "transcript_input.txt")
        if not isinstance(original_filename, str):
            original_filename = "transcript_input.txt"
        original_filename = original_filename.strip() or "transcript_input.txt"

    if len(transcript_text) > 500_000:
        raise HTTPException(status_code=413, detail="Transcript too large. Maximum 500,000 characters.")

    # Reject binary content
    _non_printable = sum(
        1 for ch in transcript_text[:10000]
        if ord(ch) < 32 and ch not in ('\n', '\r', '\t')
    )
    if _non_printable > len(transcript_text[:10000]) * 0.05:
        raise HTTPException(status_code=422, detail="Input appears to be binary data, not text.")

    # Reject overly long lines
    for i, line in enumerate(transcript_text.split('\n')[:100], 1):
        if len(line) > 10_000:
            raise HTTPException(
                status_code=422,
                detail=f"Line {i} exceeds maximum length of 10,000 characters.",
            )

    record_id = next_meeting_id()
    save_meeting_metadata(
        meeting_id=record_id,
        filename=original_filename,
        file_size_bytes=len(transcript_text.encode("utf-8")),
        status="PROCESSING",
    )

    background_tasks.add_task(_dispatch_transcript, record_id, transcript_text, original_filename)
    audit_log("transcript_submitted", meeting_id=record_id, user_action="upload",
              details={"filename": original_filename, "char_count": len(transcript_text)})
    logger.info(f"[#{record_id}] Transcript submitted: {original_filename} ({len(transcript_text)} chars)")

    return {"id": record_id, "filename": original_filename,
            "status": "PROCESSING", "message": "Transcript received, analysis started in background"}
