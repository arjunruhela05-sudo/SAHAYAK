"""
Uploaded video files: the audio track is analysed AND the footage is
analysed on the server for body language when the browser sent no cues.
"""

import json
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from tests.test_video import ACOUSTIC, BEHAVIOR, PROSODY, TRANSCRIPTION


client = TestClient(app)

FOOTAGE = dict(
    BEHAVIOR,
    extended=True,
    tracker="server-v6",
    source="uploaded_video",
    hand_rub_count=3, hand_rub_duration_sec=6.0, finger_clasp_ratio=0.3,
    swallow_count=5, swallow_rate_per_min=10, jaw_clench_ratio=0.4, freeze_ratio=0.35,
    events=[{"type": "hand_rub", "start": 2.0, "duration": 1.5}],
    timeline=[{"t": 0, "blink": 0, "gaze_away": 0.1, "self_touch": 0.0, "hand_motion": 0.05, "head_motion": 0.02, "tension": 0.4, "expression": 0.3}],
)


def fake_video():
    return {"file": ("statement.mp4", BytesIO(b"\x00\x00\x00\x18ftypmp42fake"), "video/mp4")}


@patch("api.video.analyze_video_file", return_value=FOOTAGE)
@patch("api.video.extract_audio_track", side_effect=lambda p: p)
@patch("api.video.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.video.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.video.extract_prosody_features", return_value=PROSODY)
def test_uploaded_video_footage_is_analysed_on_server(mock_prosody, mock_acoustic, mock_transcription, mock_extract, mock_footage):
    response = client.post(
        "/api/assess-video",
        files=fake_video(),
        data={"case_id": "SAH-FOOT-001", "consent": "true"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    mock_footage.assert_called_once()
    assert data["modalities"]["behavior"]["available"] is True
    assert "behavior" in data["modalities"]["modalities_used"]
    features = data["behavior_analysis"]["features"]
    assert features["tracker"] == "server-v6"
    assert features["events"][0]["type"] == "hand_rub"
    cues = " ".join(data["modalities"]["behavior"]["cues"]).lower()
    assert "rubbing the hands" in cues
    assert "swallow" in cues
    # audio pipeline still ran on the extracted track
    assert data["modalities"]["prosody"]["available"] is True
    assert data["transcript"] == TRANSCRIPTION["text"]


@patch("api.video.analyze_video_file", return_value=FOOTAGE)
@patch("api.video.extract_audio_track", side_effect=lambda p: p)
@patch("api.video.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.video.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.video.extract_prosody_features", return_value=PROSODY)
def test_browser_cues_take_precedence_in_auto_mode(mock_prosody, mock_acoustic, mock_transcription, mock_extract, mock_footage):
    response = client.post(
        "/api/assess-video",
        files=fake_video(),
        data={"case_id": "SAH-FOOT-002", "consent": "true", "behavior": json.dumps(BEHAVIOR)},
    )
    assert response.status_code == 200, response.text
    mock_footage.assert_not_called()
    assert response.json()["behavior_analysis"]["features"]["blink_rate_per_min"] == BEHAVIOR["blink_rate_per_min"]


@patch("api.video.analyze_video_file", return_value={"available": False, "error": "MediaPipe unavailable"})
@patch("api.video.extract_audio_track", side_effect=lambda p: p)
@patch("api.video.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.video.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.video.extract_prosody_features", return_value=PROSODY)
def test_footage_failure_degrades_to_audio_only(mock_prosody, mock_acoustic, mock_transcription, mock_extract, mock_footage):
    response = client.post(
        "/api/assess-video",
        files=fake_video(),
        data={"case_id": "SAH-FOOT-003", "consent": "true", "analyze_footage": "always"},
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["modalities"]["behavior"]["available"] is False
    assert "voice" in data["modalities"]["modalities_used"]


def test_invalid_footage_mode_is_rejected():
    response = client.post(
        "/api/assess-video",
        files=fake_video(),
        data={"case_id": "SAH-FOOT-004", "consent": "true", "analyze_footage": "maybe"},
    )
    assert response.status_code == 400
