"""
Transcriber module (no diarization).

This project intentionally does not perform speaker diarization.
We only return Whisper transcription text plus a basic timeline of
segment timestamps from faster-whisper.
"""

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
    Returns:
        transcript (str)  — plain-text transcript
        timeline   (list) — [{ start, end, text }, ...]
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
        })
    transcript = transcript.strip()
    return transcript, timeline
