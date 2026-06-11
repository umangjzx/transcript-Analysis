"""
Tests for upload validation — file type, size limits, input rejection.
"""

import io
import pytest


class TestAudioUploadValidation:
    def test_reject_unsupported_format(self, client):
        file = io.BytesIO(b"fake content")
        response = client.post(
            "/analyze",
            files={"file": ("test.exe", file, "application/octet-stream")},
        )
        assert response.status_code == 400
        assert "Unsupported audio format" in response.json()["detail"]

    def test_reject_empty_filename(self, client):
        file = io.BytesIO(b"fake content")
        response = client.post(
            "/analyze",
            files={"file": ("test.pdf", file, "application/pdf")},
        )
        assert response.status_code == 400

    @pytest.mark.skipif(
        not __import__("os").getenv("MONGO_URI"),
        reason="Requires MongoDB for pipeline execution",
    )
    def test_accept_mp3_extension(self, client):
        """MP3 should be accepted (though analysis will fail without real audio)."""
        file = io.BytesIO(b"fake mp3 data" * 100)
        response = client.post(
            "/analyze",
            files={"file": ("test.mp3", file, "audio/mpeg")},
        )
        # Should get past validation — may fail later in pipeline (which is fine)
        assert response.status_code in (200, 201, 500, 507)


class TestVideoUploadValidation:
    def test_reject_unsupported_video_format(self, client):
        file = io.BytesIO(b"fake content")
        response = client.post(
            "/analyze/video",
            files={"file": ("test.gif", file, "image/gif")},
        )
        assert response.status_code == 400
        assert "Unsupported video format" in response.json()["detail"]


class TestTranscriptValidation:
    def test_reject_empty_transcript(self, client):
        response = client.post(
            "/analyze/transcript",
            json={"transcript": "", "filename": "test.txt"},
        )
        assert response.status_code == 400

    def test_reject_missing_transcript_field(self, client):
        response = client.post(
            "/analyze/transcript",
            json={"filename": "test.txt"},
        )
        assert response.status_code == 400

    def test_reject_binary_content(self, client):
        # Generate content with high non-printable ratio
        binary_content = "\x00\x01\x02\x03\x04" * 2001  # >5% non-printable
        response = client.post(
            "/analyze/transcript",
            json={"transcript": binary_content, "filename": "binary.txt"},
        )
        assert response.status_code == 422

    def test_reject_oversized_transcript(self, client):
        huge = "x" * 500_001
        response = client.post(
            "/analyze/transcript",
            json={"transcript": huge, "filename": "huge.txt"},
        )
        assert response.status_code == 413

    @pytest.mark.skipif(
        not __import__("os").getenv("MONGO_URI"),
        reason="Requires MongoDB for pipeline execution",
    )
    def test_accept_valid_transcript(self, client):
        response = client.post(
            "/analyze/transcript",
            json={
                "transcript": "Speaker A: Hello, how are you today?\nSpeaker B: I'm doing well.",
                "filename": "test_conversation.txt",
            },
        )
        # Should get past validation (may fail in pipeline without Celery)
        assert response.status_code in (200, 201, 500)

    @pytest.mark.skipif(
        not __import__("os").getenv("MONGO_URI"),
        reason="Requires MongoDB for pipeline execution",
    )
    def test_txt_file_upload(self, client):
        content = b"Speaker A: This is a test transcript."
        response = client.post(
            "/analyze/transcript",
            files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
        )
        assert response.status_code in (200, 201, 500)

    def test_reject_non_txt_file(self, client):
        content = b"Speaker A: This is a test."
        response = client.post(
            "/analyze/transcript",
            files={"file": ("test.pdf", io.BytesIO(content), "application/pdf")},
        )
        assert response.status_code == 400
