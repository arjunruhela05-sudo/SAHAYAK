import pytest
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient
from services.voice_engine import (
    save_uploaded_audio,
    validate_audio,
)
from main import app


client = TestClient(app)


def fake_audio_file():
    return {
        "file": (
            "test.wav",
            BytesIO(b"fake-audio-data"),
            "audio/wav",
        )
    }


@patch(
    "api.voice.transcribe_audio",
    return_value={
        "available": True,
        "text": "I am scared and I have nobody to help me.",
        "language": "en",
        "segments": [],
    },
)
@patch(
    "api.voice.extract_acoustic_features",
    return_value={
        "available": True,
        "duration": 5.2,
        "sample_rate": 16000,
        "rms": 0.08,
        "zero_crossing_rate": 0.08,
        "pitch_variability": 70.0,
    },
)
def test_audio_assessment_success(
    mock_acoustic,
    mock_transcription,
):
    response = client.post(
        "/api/assess-audio",
        files=fake_audio_file(),
        data={
            "case_id": "SAH-AUDIO-001",
            "consent": "true",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["case_id"] == "SAH-AUDIO-001"
    assert 0 <= data["svi_score"] <= 100
    assert data["risk_level"] in {
        "LOW",
        "MODERATE",
        "HIGH",
        "CRITICAL",
    }
    assert data["human_review_required"] is True

    mock_transcription.assert_called_once()
    mock_acoustic.assert_called_once()


def test_audio_assessment_requires_consent():
    response = client.post(
        "/api/assess-audio",
        files=fake_audio_file(),
        data={
            "case_id": "SAH-AUDIO-002",
            "consent": "false",
        },
    )

    assert response.status_code == 400
    assert "Consent is required" in response.json()["detail"]


def test_audio_assessment_rejects_empty_audio():
    response = client.post(
        "/api/assess-audio",
        files={
            "file": (
                "empty.wav",
                BytesIO(b""),
                "audio/wav",
            )
        },
        data={
            "case_id": "SAH-AUDIO-003",
            "consent": "true",
        },
    )

    assert response.status_code == 400
    assert "Audio file is empty" in response.json()["detail"]


def test_audio_assessment_rejects_unsupported_audio_type():
    response = client.post(
        "/api/assess-audio",
        files={
            "file": (
                "test.txt",
                BytesIO(b"not-audio"),
                "text/plain",
            )
        },
        data={
            "case_id": "SAH-AUDIO-004",
            "consent": "true",
        },
    )

    assert response.status_code == 400
    assert "Unsupported audio type" in response.json()["detail"]


@patch(
    "api.voice.transcribe_audio",
    return_value={
        "available": True,
        "text": "",
        "language": "en",
        "segments": [],
    },
)
def test_audio_assessment_rejects_empty_transcription(
    mock_transcription,
):
    response = client.post(
        "/api/assess-audio",
        files=fake_audio_file(),
        data={
            "case_id": "SAH-AUDIO-005",
            "consent": "true",
        },
    )

    assert response.status_code == 422
    assert "No speech could be transcribed" in (
        response.json()["detail"]
    )

    mock_transcription.assert_called_once()


@patch(
    "api.voice.transcribe_audio",
    return_value={
        "available": False,
        "text": "",
        "language": "unknown",
        "segments": [],
        "error": "Whisper unavailable",
    },
)
def test_audio_assessment_handles_whisper_failure(
    mock_transcription,
):
    response = client.post(
        "/api/assess-audio",
        files=fake_audio_file(),
        data={
            "case_id": "SAH-AUDIO-006",
            "consent": "true",
        },
    )

    assert response.status_code == 503
    assert "Whisper unavailable" in response.json()["detail"]

    mock_transcription.assert_called_once()


def test_audio_filename_path_traversal_is_rejected():
    with pytest.raises(ValueError):
        validate_audio(
            filename="../../malicious.wav",
            content_type="audio/wav",
            file_size=1024,
        )

def test_empty_audio_file_is_rejected():
    with pytest.raises(ValueError):
        validate_audio(
            filename="empty.wav",
            content_type="audio/wav",
            file_size=0,
        )        
