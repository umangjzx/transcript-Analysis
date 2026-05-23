from faster_whisper import WhisperModel

model = WhisperModel(
    "base",
    device="cpu",
    compute_type="int8"
)


def transcribe_audio(audio_path):

    segments, info = model.transcribe(
        audio_path,
        beam_size=5
    )

    transcript = ""

    timeline = []

    for segment in segments:

        transcript += segment.text + " "

        timeline.append(
            {
                "start": round(segment.start, 2),
                "end": round(segment.end, 2),
                "text": segment.text.strip()
            }
        )

    return transcript.strip(), timeline