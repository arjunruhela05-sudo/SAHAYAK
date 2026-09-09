from services.behavior_engine import calculate_behavior_indicator


CALM = {
    "available": True,
    "duration_sec": 40,
    "frames_analyzed": 1100,
    "fps": 27.5,
    "face_detected_ratio": 0.98,
    "hands_detected_ratio": 0.7,
    "blink_count": 9,
    "blink_rate_per_min": 13.5,
    "gaze_aversion_ratio": 0.12,
    "gaze_shift_rate_per_min": 6,
    "face_touch_count": 0,
    "face_touch_duration_sec": 0,
    "hand_movement_energy": 0.05,
    "hand_fidget_rate_per_min": 1,
    "hands_together_ratio": 0.05,
    "head_movement_energy": 0.04,
    "head_shake_rate_per_min": 0,
    "posture_shift_count": 0,
    "head_down_ratio": 0.05,
    "expression": {"brow_furrow": 0.05, "lip_press": 0.04, "mouth_frown": 0.03, "eye_squint": 0.05, "jaw_tension": 0.02, "smile": 0.2},
}

STRESSED = {
    "available": True,
    "duration_sec": 40,
    "frames_analyzed": 1100,
    "fps": 27.5,
    "face_detected_ratio": 0.95,
    "hands_detected_ratio": 0.8,
    "blink_count": 28,
    "blink_rate_per_min": 42,
    "gaze_aversion_ratio": 0.62,
    "gaze_shift_rate_per_min": 34,
    "face_touch_count": 5,
    "face_touch_duration_sec": 9,
    "hand_movement_energy": 0.42,
    "hand_fidget_rate_per_min": 16,
    "hands_together_ratio": 0.5,
    "head_movement_energy": 0.3,
    "head_shake_rate_per_min": 10,
    "posture_shift_count": 4,
    "head_down_ratio": 0.45,
    "expression": {"brow_furrow": 0.45, "lip_press": 0.35, "mouth_frown": 0.3, "eye_squint": 0.3, "jaw_tension": 0.3, "smile": 0.0},
}


def test_unavailable_payload():
    result = calculate_behavior_indicator({"available": False})
    assert result["available"] is False
    assert result["indicator"] == 0.0


def test_invalid_payload_is_graceful():
    result = calculate_behavior_indicator({"blink_rate_per_min": -4})
    assert result["available"] is False
    assert "error" in result


def test_calm_vs_stressed():
    calm = calculate_behavior_indicator(CALM)
    stressed = calculate_behavior_indicator(STRESSED)

    assert calm["available"] and stressed["available"]
    assert calm["indicator"] < 15
    assert stressed["indicator"] > 70
    assert stressed["reliability"] == 1.0
    assert any("blink" in cue.lower() for cue in stressed["cues"])
    assert any("eye contact" in cue.lower() for cue in stressed["cues"])
    assert any("face touching" in cue.lower() for cue in stressed["cues"])
    assert any("fidget" in cue.lower() for cue in stressed["cues"])


def test_low_quality_capture_is_downweighted():
    poor = dict(STRESSED, duration_sec=3, frames_analyzed=40, face_detected_ratio=0.3)
    result = calculate_behavior_indicator(poor)
    assert result["available"] is True
    assert result["reliability"] < 0.3
    assert result["indicator"] < result["raw_indicator"]
    assert result["quality_notes"]


def test_hands_not_tracked_redistributes_weight():
    no_hands = dict(STRESSED, hands_detected_ratio=0.0)
    result = calculate_behavior_indicator(no_hands)
    assert result["sub_scores"]["fidgeting"] == 0.0
    # still clearly elevated from the other cues
    assert result["indicator"] > 60
