import ffmpeg
import os


def extract_audio(video_path):

    audio_path = video_path.replace(".mp4",".wav")

    (
        ffmpeg
        .input(video_path)
        .output(
            audio_path,
            acodec='pcm_s16le',
            ac=1,
            ar='16000'
        )
        .run(overwrite_output=True)
    )

    return audio_path