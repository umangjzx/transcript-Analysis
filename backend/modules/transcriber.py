"""
Transcriber module with optional speaker diarization.

If HF_TOKEN is set in the environment, pyannote.audio is used to label
each transcript segment with a speaker ID (SPEAKER_00, SPEAKER_01, …).
If the token is missing or pyannote fails, the pipeline falls back to
plain Whisper transcription without speaker labels.

Fixes applied:
- Whisper model is lazy-loaded on first use (not at import time)
"""

import os
import logging

logger = logging.getLogger(__name__)

# ── Whisper model (lazy singleton) ────────────────────────────────────────────

_whisper_model = None


def _get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        from faster_whisper import WhisperModel
        logger.info("Loading Whisper model (base, CPU, int8)...")
        _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
        logger.info("Whisper model loaded")
    return _whisper_model

# ── Diarization pipeline (lazy-loaded) ────────────────────────────────────────

_diarization_pipeline = None


def _get_diarization_pipeline():
    """
    Lazy-load the pyannote speaker-diarization pipeline.
    Returns None if HF_TOKEN is not set or pyannote is not installed.
    """
    global _diarization_pipeline

    if _diarization_pipeline is not None:
        return _diarization_pipeline

    hf_token = os.getenv("HF_TOKEN", "").strip()
    if not hf_token:
        logger.warning(
            "HF_TOKEN not set — speaker diarization disabled. "
            "Add HF_TOKEN to your .env to enable it."
        )
        return None

    try:
        from pyannote.audio import Pipeline
        import torch

        logger.info("Loading pyannote speaker-diarization pipeline…")
        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=hf_token
        )

        # Use GPU if available, otherwise CPU
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _diarization_pipeline = _diarization_pipeline.to(
            torch.device(device)
        )
        logger.info(f"Diarization pipeline loaded on {device}")

    except Exception as e:
        logger.warning(f"Could not load diarization pipeline: {e}")
        _diarization_pipeline = None

    return _diarization_pipeline


# ── Speaker assignment helper ─────────────────────────────────────────────────

def _assign_speaker(segment_start: float, segment_end: float, diarization) -> str:
    """
    Find the speaker label that has the most overlap with a Whisper segment.
    Falls back to 'UNKNOWN' if no overlap is found.
    """
    best_speaker = "UNKNOWN"
    best_overlap = 0.0

    for turn, _, speaker in diarization.itertracks(yield_label=True):
        # Overlap between [segment_start, segment_end] and [turn.start, turn.end]
        overlap_start = max(segment_start, turn.start)
        overlap_end   = min(segment_end,   turn.end)
        overlap       = max(0.0, overlap_end - overlap_start)

        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker

    return best_speaker


# ── Public API ────────────────────────────────────────────────────────────────

def transcribe_audio(audio_path: str):
    """
    Transcribe an audio file and optionally label each segment with a speaker.

    Returns:
        transcript (str)  — full plain-text transcript
        timeline   (list) — list of dicts with keys:
                            start, end, text, speaker (always present;
                            value is 'UNKNOWN' when diarization is off)
    """

    # ── Step 1: Whisper transcription ─────────────────────────────────────────
    model = _get_whisper_model()
    segments, _info = model.transcribe(
        audio_path,
        beam_size=5,
        word_timestamps=False,
    )

    # Materialise the generator so we can iterate twice if needed
    segments = list(segments)

    transcript = ""
    timeline   = []

    for seg in segments:
        transcript += seg.text + " "
        timeline.append({
            "start":   round(seg.start, 2),
            "end":     round(seg.end,   2),
            "text":    seg.text.strip(),
            "speaker": "UNKNOWN",          # default; overwritten below
        })

    transcript = transcript.strip()

    # ── Step 2: Speaker diarization (optional) ────────────────────────────────
    pipeline = _get_diarization_pipeline()

    if pipeline is not None and timeline:
        try:
            logger.info(f"Running speaker diarization on: {audio_path}")
            diarization = pipeline(audio_path)

            for entry in timeline:
                entry["speaker"] = _assign_speaker(
                    entry["start"],
                    entry["end"],
                    diarization
                )

            # Build a speaker-labelled transcript as well
            labelled_lines = [
                f"[{e['speaker']}] {e['text']}"
                for e in timeline
            ]
            transcript = "\n".join(labelled_lines)

            logger.info("Speaker diarization completed successfully")

        except Exception as e:
            logger.warning(f"Diarization failed, continuing without it: {e}")
            # timeline already has speaker='UNKNOWN' — nothing more to do

    return transcript, timeline