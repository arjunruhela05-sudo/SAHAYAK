"""
The assessed person must never receive a score, risk level, cue or
tracking data — only a receipt.
"""

import json
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from services.behavior_engine import calculate_behavior_indicator
from tests.test_video import ACOUSTIC, BEHAVIOR, PROSODY, TRANSCRIPTION


client = TestClient(app)

FORBIDDEN_KEYS = {"svi_score", "risk_level", "signals", "modalities", "voice_analysis", "behavior_analysis", "evidence", "explanation", "narrative_context", "vulnerability_profile"}


def _assert_receipt(data, case_id, capture_mode):
    assert data["case_id"] == case_id
    assert data["participant_view"] is True
    assert data["status"] == "RECEIVED"
    assert data["capture_mode"] == capture_mode
    assert data["human_review_required"] is True
    assert data["next_steps"]
    assert not (FORBIDDEN_KEYS & set(data.keys()))


def test_text_assessment_participant_receipt():
    response = client.post("/api/assess", json={
        "case_id": "SAH-PV-001", "narrative": "He said he will kill me tomorrow and I have nobody.",
        "language": "en", "consent": True, "participant_view": True,
    })
    assert response.status_code == 200, response.text
    _assert_receipt(response.json(), "SAH-PV-001", "text")

    # The case itself is fully scored for the responder.
    case = client.get("/api/cases/SAH-PV-001").json()
    assert case["svi_score"] > 0 and case["risk_level"] in {"HIGH", "CRITICAL"}
    assert case["narrative_context"] is not None


def test_text_assessment_default_is_full_response():
    response = client.post("/api/assess", json={
        "case_id": "SAH-PV-002", "narrative": "I am scared to go home.", "language": "en", "consent": True,
    })
    assert response.status_code == 200
    data = response.json()
    assert "svi_score" in data and "narrative_context" in data


@patch("api.voice.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.voice.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.voice.extract_prosody_features", return_value=PROSODY)
def test_audio_assessment_participant_receipt(mock_prosody, mock_acoustic, mock_transcription):
    response = client.post(
        "/api/assess-audio",
        files={"file": ("recording.webm", BytesIO(b"fake"), "audio/webm")},
        data={"case_id": "SAH-PV-003", "consent": "true", "participant_view": "true"},
    )
    assert response.status_code == 200, response.text
    _assert_receipt(response.json(), "SAH-PV-003", "voice")


@patch("api.video.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.video.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.video.extract_prosody_features", return_value=PROSODY)
def test_video_assessment_participant_receipt(mock_prosody, mock_acoustic, mock_transcription):
    response = client.post(
        "/api/assess-video",
        files={"file": ("recording.webm", BytesIO(b"fake"), "audio/webm")},
        data={"case_id": "SAH-PV-004", "consent": "true", "behavior": json.dumps(BEHAVIOR), "participant_view": "true"},
    )
    assert response.status_code == 200, response.text
    _assert_receipt(response.json(), "SAH-PV-004", "video")
    case = client.get("/api/cases/SAH-PV-004").json()
    assert case["modalities"]["behavior"]["available"] is True


def test_participant_case_views_are_redacted():
    client.post("/api/assess", json={"case_id": "SAH-PV-005", "narrative": "I am scared.", "language": "en", "consent": True})

    single = client.get("/api/cases/SAH-PV-005?view=participant").json()
    assert single["case_id"] == "SAH-PV-005"
    assert single["status"] == "NEW"
    assert "message" in single
    assert not (FORBIDDEN_KEYS & set(single.keys()))

    listing = client.get("/api/cases?view=participant").json()
    assert isinstance(listing, list) and listing
    assert all(not (FORBIDDEN_KEYS & set(item.keys())) for item in listing)

    # Responder views are unchanged
    full = client.get("/api/cases/SAH-PV-005").json()
    assert "svi_score" in full
    summaries = client.get("/api/cases").json()
    assert "svi_score" in summaries[0]


def test_extended_behavior_features_are_accepted_and_scored():
    extended = dict(
        BEHAVIOR,
        extended=True,
        tracker="browser-v6",
        pose_detected_ratio=0.9,
        hand_rub_count=4, hand_rub_duration_sec=9.0,
        finger_clasp_ratio=0.4, arm_stroke_count=3, arm_stroke_duration_sec=5.0,
        self_hug_ratio=0.3, neck_touch_count=3, hair_touch_count=2, lip_bite_ratio=0.2,
        swallow_count=6, swallow_rate_per_min=12,
        shoulder_raise_ratio=0.5, shoulder_asymmetry=0.15, jaw_clench_ratio=0.5, freeze_ratio=0.5, slouch_ratio=0.4, lean_away_ratio=0.3,
        blink_burst_count=5, blink_interval_cv=1.2,
        events=[{"type": "hand_rub", "start": 3.2, "duration": 2.1}, {"type": "swallow", "start": 5.0, "duration": 0.4, "note": "approximate"}],
        timeline=[{"t": 0, "blink": 1, "gaze_away": 0.2, "self_touch": 0.0, "hand_motion": 0.1, "head_motion": 0.05, "tension": 0.3, "expression": 0.2}],
    )
    result = calculate_behavior_indicator(extended)
    assert result["available"] is True
    assert result["sub_scores"]["self_soothing"] > 70
    assert result["sub_scores"]["tension"] > 70
    assert result["sub_scores"]["swallowing"] > 90
    assert result["event_count"] == 2
    joined = " ".join(result["cues"]).lower()
    assert "rubbing the hands" in joined
    assert "clasped" in joined
    assert "swallow" in joined
    assert "jaw clenched" in joined or "shoulders raised" in joined

    # The endpoint accepts the extended contract too
    response = client.post("/api/behavior-score", json=extended)
    assert response.status_code == 200
    assert response.json()["indicator"] > 70


def test_legacy_behavior_payload_ignores_extended_groups():
    result = calculate_behavior_indicator(BEHAVIOR)
    assert "self_soothing" not in result["tracked_groups"]
    assert "tension" not in result["tracked_groups"]
    assert result["indicator"] > 50


def test_video_capabilities_endpoint():
    response = client.get("/api/video-capabilities")
    assert response.status_code == 200
    data = response.json()
    assert "server_footage_analysis" in data and data["browser_tracking"] is True
