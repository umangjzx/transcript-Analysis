"""
Transcriber module with optional speaker diarization.

Performance notes
-----------------
Diarization is the dominant cost (~90 s for a 3-min file on CPU).
To keep analysis fast, diarization is now opt-in:

    ENABLE_DIARIZATION=true   in .env   (default: false)

When disabled, every timeline segment gets speaker='UNKNOWN' and
transcription still works normally.

When enabled, audio is resampled to 16 kHz mono before being passed
to pyannote — this alone cuts diarization time by ~60 % because
pyannote internally resamples anyway, and working at 44.1 kHz stereo
wastes significant compute.

Other fixes
-----------
- torchcodec wall-of-warnings suppressed at import time
- pyannote v4 API: result.speaker_diarization.itertracks()
- Audio loaded via soundfile (no FFmpeg/torchcodec needed on Windows)
- Whisper model lazy-loaded on first use
"""

import os
import logging
import warnings

# Suppress the torchcodec "not installed correctly" wall-of-text that
# appears every time pyannote.audio is imported on Windows CPU.
warnings.filterwarnings(
    "ignore",
    message="torchcodec is not installed correctly",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message="std\\(\\): degrees of freedom",
    category=UserWarning,
)

logger = logging.getLogger(__name__)

# ── Feature flags ─────────────────────────────────────────────────────────────

# Diarization is opt-in — it adds ~90 s on CPU for a 3-min file.
# Set ENABLE_DIARIZATION=true in .env to turn it on.
_ENABLE_DIARIZATION: bool = (
    os.getenv("ENABLE_DIARIZATION", "false").lower() == "true"
)

# Target sample rate for diarization — 16 kHz is what pyannote expects
# internally; resampling upfront avoids redundant work inside the pipeline.
_DIARIZATION_SAMPLE_RATE = 16_000

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


# ── Diarization pipeline (lazy singleton) ─────────────────────────────────────

_diarization_pipeline = None


def _get_diarization_pipeline():
    """
    Lazy-load the pyannote speaker-diarization pipeline.
    Returns None if diarization is disabled, HF_TOKEN is missing,
    or pyannote fails to load.
    """
    global _diarization_pipeline

    if not _ENABLE_DIARIZATION:
        return None

    if _diarization_pipeline is not None:
        return _diarization_pipeline

    hf_token = os.getenv("HF_TOKEN", "").strip()
    if not hf_token:
        logger.warning(
            "HF_TOKEN not set — speaker diarization disabled. "
            "Set HF_TOKEN and ENABLE_DIARIZATION=true in .env to enable."
        )
        return None

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            from pyannote.audio import Pipeline
        import torch

        logger.info("Loading pyannote speaker-diarization-3.1 pipeline…")
        _diarization_pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            token=hf_token,
        )
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _diarization_pipeline = _diarization_pipeline.to(torch.device(device))
        logger.info(f"Diarization pipeline loaded on {device}")

    except Exception as e:
        logger.warning(f"Could not load diarization pipeline: {e}")
        _diarization_pipeline = None

    return _diarization_pipeline


# ── Audio loading + resampling helper ────────────────────────────────────────

def _load_audio_for_diarization(audio_path: str):
    """
    Load audio and resample to 16 kHz mono for pyannote.

    Returns a dict  {'waveform': torch.Tensor (1, samples), 'sample_rate': 16000}
    that pyannote accepts directly — bypassing torchcodec entirely.

    Uses soundfile (libsndfile) which works on Windows without FFmpeg.
    """
    import torch
    import numpy as np

    try:
        import soundfile as sf
        waveform_np, sr = sf.read(audio_path, dtype="float32", always_2d=True)
        # soundfile → (samples, channels); transpose to (channels, samples)
        waveform = torch.from_numpy(waveform_np.T)  # (C, T)
    except Exception as sf_err:
        raise RuntimeError(
            f"soundfile could not read '{audio_path}': {sf_err}. "
            "Install soundfile: pip install soundfile"
        )

    # Convert to mono by averaging channels
    if waveform.shape[0] > 1:
        waveform = waveform.mean(dim=0, keepdim=True)  # (1, T)

    # Resample to 16 kHz if needed — avoids redundant work inside pyannote
    if sr != _DIARIZATION_SAMPLE_RATE:
        try:
            import torchaudio.functional as F
            waveform = F.resample(waveform, orig_freq=sr, new_freq=_DIARIZATION_SAMPLE_RATE)
            sr = _DIARIZATION_SAMPLE_RATE
            logger.debug(f"Resampled audio to {_DIARIZATION_SAMPLE_RATE} Hz")
        except Exception:
            # If torchaudio resampling fails, pass original — pyannote will handle it
            logger.debug("torchaudio resample unavailable; passing original sample rate")

    return {"waveform": waveform, "sample_rate": sr}


# ── Speaker assignment helpers ────────────────────────────────────────────────

def _get_annotation(diarization_result):
    """
    Extract the pyannote Annotation from a diarization result.
    pyannote v3 → Annotation directly.
    pyannote v4 → DiarizeOutput with .speaker_diarization attribute.
    """
    if hasattr(diarization_result, "speaker_diarization"):
        return diarization_result.speaker_diarization
    return diarization_result


def _assign_speaker(segment_start: float, segment_end: float, annotation) -> str:
    """Return the speaker label with the most overlap with a Whisper segment."""
    best_speaker = "UNKNOWN"
    best_overlap = 0.0
    for turn, _, speaker in annotation.itertracks(yield_label=True):
        overlap = max(0.0, min(segment_end, turn.end) - max(segment_start, turn.start))
        if overlap > best_overlap:
            best_overlap = overlap
            best_speaker = speaker
    return best_speaker


# ── Video → Audio extraction ──────────────────────────────────────────────────

def extract_audio_from_video(video_path: str, output_path: str) -> str:
    """
    Extract the first audio stream from a video file and write it as a WAV.

    Uses PyAV (the ``av`` package already in requirements.txt) — no FFmpeg
    binary required on Windows.

    Args:
        video_path:  Path to the source video file.
        output_path: Destination path for the extracted WAV file.

    Returns:
        output_path on success.

    Raises:
        RuntimeError if no audio stream is found or extraction fails.
    """
    import av as _av
    import struct

    logger.info(f"Extracting audio from video: {video_path} → {output_path}")

    try:
        in_container = _av.open(video_path)
    except Exception as e:
        raise RuntimeError(f"Could not open video file '{video_path}': {e}")

    # Find the first audio stream
    audio_stream = next(
        (s for s in in_container.streams if s.type == "audio"), None
    )
    if audio_stream is None:
        in_container.close()
        raise RuntimeError(
            f"No audio stream found in '{video_path}'. "
            "The video may be silent or the format is unsupported."
        )

    try:
        out_container = _av.open(output_path, mode="w", format="wav")
        out_stream = out_container.add_stream("pcm_s16le", rate=16000, layout="mono")

        resampler = _av.AudioResampler(
            format="s16",
            layout="mono",
            rate=16000,
        )

        for packet in in_container.demux(audio_stream):
            for frame in packet.decode():
                resampled_frames = resampler.resample(frame)
                for rf in resampled_frames:
                    rf.pts = None
                    for out_packet in out_stream.encode(rf):
                        out_container.mux(out_packet)

        # Flush encoder
        for out_packet in out_stream.encode(None):
            out_container.mux(out_packet)

        out_container.close()
        in_container.close()

    except Exception as e:
        try:
            in_container.close()
        except Exception:
            pass
        raise RuntimeError(f"Audio extraction failed: {e}")

    logger.info(f"Audio extracted successfully: {output_path}")
    return output_path


# ── Public API ────────────────────────────────────────────────────────────────

def transcribe_audio(audio_path: str):
    """
    Transcribe an audio file and optionally label each segment with a speaker.

    Diarization is only run when ENABLE_DIARIZATION=true in .env.
    Without diarization a 3-min file completes in ~5 s on CPU.
    With diarization it takes ~90 s on CPU (no GPU).

    Returns:
        transcript (str)  — plain-text or speaker-labelled transcript
        timeline   (list) — [{ start, end, text, speaker }, ...]
                            speaker = 'UNKNOWN' when diarization is off
    """

    # ── Step 1: Whisper transcription ─────────────────────────────────────────
    model = _get_whisper_model()
    segments, _info = model.transcribe(
        audio_path,
        beam_size=5,
        word_timestamps=False,
    )
    segments = list(segments)

    transcript = ""
    timeline   = []
    for seg in segments:
        transcript += seg.text + " "
        timeline.append({
            "start":   round(seg.start, 2),
            "end":     round(seg.end,   2),
            "text":    seg.text.strip(),
            "speaker": "UNKNOWN",
        })
    transcript = transcript.strip()

    # ── Step 2: Speaker diarization (opt-in) ──────────────────────────────────
    pipeline = _get_diarization_pipeline()

    if pipeline is None:
        if _ENABLE_DIARIZATION:
            logger.debug("Diarization enabled but pipeline unavailable — skipping")
        return transcript, timeline

    if not timeline:
        return transcript, timeline

    try:
        t_start = __import__("time").monotonic()
        logger.info(f"Running speaker diarization on: {audio_path}")

        audio_input = _load_audio_for_diarization(audio_path)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            diarization_result = pipeline(audio_input)

        annotation = _get_annotation(diarization_result)

        for entry in timeline:
            entry["speaker"] = _assign_speaker(
                entry["start"], entry["end"], annotation
            )

        transcript = "\n".join(
            f"[{e['speaker']}] {e['text']}" for e in timeline
        )

        unique_speakers = {e["speaker"] for e in timeline} - {"UNKNOWN"}
        elapsed = __import__("time").monotonic() - t_start
        logger.info(
            f"Diarization completed in {elapsed:.1f}s — "
            f"{len(unique_speakers)} speaker(s) detected"
        )

    except Exception as e:
        logger.warning(f"Diarization failed, continuing without it: {e}")

    return transcript, timeline
