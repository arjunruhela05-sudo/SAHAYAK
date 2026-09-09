import json
from io import BytesIO
from unittest.mock import patch

from fastapi.testclient import TestClient

from main import app
from services.fusion_engine import fuse_multimodal_signals


client = TestClient(app)


TRANSCRIPTION = {
    "available": True,
    "text": "Um, I... I don't know. He, uh, he said he will hurt me if I tell anyone and...",
    "language": "en",
    "segments": [
        {"start": 0.0, "end": 2.5, "text": "Um, I... I don't know."},
        {"start": 4.5, "end": 8.0, "text": "He, uh, he said he will hurt me if I tell anyone and..."},
    ],
}

ACOUSTIC = {
    "available": True,
    "duration": 8.0,
    "sample_rate": 16000,
    "rms": 0.08,
    "zero_crossing_rate": 0.08,
    "pitch_variability": 70.0,
}

PROSODY = {
    "available": True,
    "duration_sec": 8.0,
    "speech_ratio": 0.5,
    "pauses": {"pause_count": 3, "long_pause_count": 2, "mean_pause_sec": 1.4, "max_pause_sec": 2.0, "pause_ratio": 0.4, "pause_rate_per_min": 22, "speech_time_sec": 4.0, "leading_silence_sec": 0.3},
    "pitch": {"available": True, "f0_mean_hz": 230, "f0_std_hz": 40, "f0_cv": 0.3, "f0_semitone_range": 9, "jitter_local": 0.02, "pitch_drift_hz": 25, "voiced_ratio": 0.9},
    "voice_quality": {"shimmer_local": 0.1, "hnr_db": 12, "praat_used": True},
    "depth": {"available": True, "spectral_centroid_hz": 2000, "voice_depth_index": 0.7},
    "breathing": {"breath_count": 4, "breath_rate_per_min": 24, "breath_intensity": 0.3, "mean_breath_duration_sec": 0.3, "breath_interval_cv": 0.9},
    "tremor": {"tremor_index": 0.4, "tremor_segments": 3},
    "rate": {"syllable_count": 30, "syllable_rate": 6.5},
}

BEHAVIOR = {
    "available": True,
    "duration_sec": 30,
    "frames_analyzed": 850,
    "fps": 28,
    "face_detected_ratio": 0.97,
    "hands_detected_ratio": 0.8,
    "blink_count": 20,
    "blink_rate_per_min": 40,
    "gaze_aversion_ratio": 0.6,
    "gaze_shift_rate_per_min": 30,
    "face_touch_count": 4,
    "face_touch_duration_sec": 7,
    "hand_movement_energy": 0.4,
    "hand_fidget_rate_per_min": 15,
    "hands_together_ratio": 0.4,
    "head_movement_energy": 0.25,
    "head_shake_rate_per_min": 8,
    "posture_shift_count": 3,
    "head_down_ratio": 0.4,
    "expression": {"brow_furrow": 0.4, "lip_press": 0.3, "mouth_frown": 0.3, "eye_squint": 0.2, "jaw_tension": 0.2, "smile": 0.0},
}


def fake_audio():
    return {"file": ("recording.webm", BytesIO(b"fake-audio-data"), "audio/webm")}


@patch("api.video.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.video.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.video.extract_prosody_features", return_value=PROSODY)
def test_video_assessment_success(mock_prosody, mock_acoustic, mock_transcription):
    response = client.post(
        "/api/assess-video",
        files=fake_audio(),
        data={
            "case_id": "SAH-VIDEO-001",
            "consent": "true",
            "behavior": json.dumps(BEHAVIOR),
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()

    assert data["case_id"] == "SAH-VIDEO-001"
    assert 0 <= data["svi_score"] <= 100
    assert data["human_review_required"] is True
    assert data["transcript"] == TRANSCRIPTION["text"]

    modalities = data["modalities"]
    assert modalities["modalities_used"] == ["text", "voice", "behavior"]
    assert modalities["fusion_method"] == "text_primary+voice+behavior"
    assert modalities["prosody"]["available"] is True
    assert modalities["disfluency"]["available"] is True
    assert modalities["behavior"]["available"] is True
    assert modalities["behavior"]["indicator"] > 50
    assert modalities["voice_indicator"] > 30
    assert modalities["fused_svi"] >= modalities["text_svi"]
    assert modalities["fused_svi"] - modalities["text_svi"] <= 14.0

    explanation = " ".join(data["explanation"]).lower()
    assert "body language" in explanation
    assert "voice" in explanation

    assert data["voice_analysis"]["disfluency"]["fillers"]["count"] >= 2
    assert data["behavior_analysis"]["features"]["blink_rate_per_min"] == 40

    mock_transcription.assert_called_once()
    mock_acoustic.assert_called_once()
    mock_prosody.assert_called_once()


@patch("api.video.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.video.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.video.extract_prosody_features", return_value=PROSODY)
def test_video_case_is_persisted_with_modalities(mock_prosody, mock_acoustic, mock_transcription):
    client.post(
        "/api/assess-video",
        files=fake_audio(),
        data={"case_id": "SAH-VIDEO-002", "consent": "true", "behavior": json.dumps(BEHAVIOR)},
    )
    case = client.get("/api/cases/SAH-VIDEO-002").json()
    assert case["capture_mode"] == "video"
    assert case["modalities"]["behavior"]["available"] is True
    assert case["behavior_analysis"]["result"]["indicator"] > 50
    # raw media is never stored
    assert "audio" not in case and "video" not in case


@patch("api.video.transcribe_audio", return_value=TRANSCRIPTION)
@patch("api.video.extract_acoustic_features", return_value=ACOUSTIC)
@patch("api.video.extract_prosody_features", return_value=PROSODY)
def test_video_assessment_without_behavior_still_works(mock_prosody, mock_acoustic, mock_transcription):
    response = client.post(
        "/api/assess-video",
        files=fake_audio(),
        data={"case_id": "SAH-VIDEO-003", "consent": "true"},
    )
    assert response.status_code == 200, response.text
    modalities = response.json()["modalities"]
    # Empty behaviour payload -> behaviour unavailable, voice still used
    assert modalities["behavior"]["available"] is False
    assert "voice" in modalities["modalities_used"]


def test_video_assessment_requires_consent():
    response = client.post(
        "/api/assess-video",
        files=fake_audio(),
        data={"case_id": "SAH-VIDEO-004", "consent": "false", "behavior": "{}"},
    )
    assert response.status_code == 400
    assert "Consent is required" in response.json()["detail"]


def test_video_assessment_rejects_bad_behavior_json():
    response = client.post(
        "/api/assess-video",
        files=fake_audio(),
        data={"case_id": "SAH-VIDEO-005", "consent": "true", "behavior": "{not json"},
    )
    assert response.status_code == 400
    assert "JSON" in response.json()["detail"]


def test_video_assessment_rejects_out_of_range_behavior():
    response = client.post(
        "/api/assess-video",
        files=fake_audio(),
        data={"case_id": "SAH-VIDEO-006", "consent": "true", "behavior": json.dumps({"gaze_aversion_ratio": 4})},
    )
    assert response.status_code == 400
    assert "Invalid behaviour features" in response.json()["detail"]


def test_video_assessment_rejects_unsupported_media():
    response = client.post(
        "/api/assess-video",
        files={"file": ("x.txt", BytesIO(b"nope"), "text/plain")},
        data={"case_id": "SAH-VIDEO-007", "consent": "true", "behavior": "{}"},
    )
    assert response.status_code == 400


def test_behavior_score_endpoint():
    response = client.post("/api/behavior-score", json=BEHAVIOR)
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["indicator"] > 50
    assert data["cues"]


# ---------------------------------------------------------------------
# Fusion behaviour with all modalities
# ---------------------------------------------------------------------

def test_fusion_caps_total_adjustment():
    result = fuse_multimodal_signals(
        text_svi=30.0,
        acoustic_features={"available": True, "rms": 0.2, "zero_crossing_rate": 0.2, "pitch_variability": 150},
        prosody_result={"available": True, "indicator": 100.0, "sub_scores": {}, "cues": []},
        disfluency_result={"available": True, "indicator": 100.0, "sub_scores": {}, "cues": []},
        behavior_result={"available": True, "indicator": 100.0, "sub_scores": {}, "cues": [], "reliability": 1.0},
    )
    assert result["fused_svi"] <= 44.0
    assert result["voice_adjustment"] <= 10.0
    assert result["behavior_adjustment"] <= 6.0
    assert result["incongruence_flag"] is True
    assert result["fusion_method"] == "text_primary+voice+behavior"


def test_fusion_never_lowers_text_score():
    result = fuse_multimodal_signals(
        text_svi=80.0,
        acoustic_features={"available": False},
        prosody_result={"available": True, "indicator": 5.0, "sub_scores": {}, "cues": []},
        behavior_result={"available": True, "indicator": 0.0, "sub_scores": {}, "cues": []},
    )
    assert result["fused_svi"] == 80.0
    assert result["incongruence_flag"] is False


def test_fusion_behavior_scaled_by_reliability():
    reliable = fuse_multimodal_signals(
        text_svi=20.0,
        acoustic_features={"available": False},
        behavior_result={"available": True, "indicator": 90.0, "sub_scores": {}, "cues": [], "reliability": 1.0},
    )
    shaky = fuse_multimodal_signals(
        text_svi=20.0,
        acoustic_features={"available": False},
        behavior_result={"available": True, "indicator": 90.0, "sub_scores": {}, "cues": [], "reliability": 0.3},
    )
    assert reliable["behavior_adjustment"] > shaky["behavior_adjustment"]
    assert reliable["fusion_method"] == "text_primary+behavior"
