"""
Synthetic-frame tests for the server-side body-language aggregator.

The aggregator is a port of the browser tracker; these streams mirror
the ones used to test the JavaScript core so both stay in step.
"""

import math

from services.behavior_engine import calculate_behavior_indicator
from services.video_behavior_engine import BehaviorAggregator, P, TRACKER_VERSION


FPS = 20
DT = 1000.0 / FPS


def face(cx=0.5, cy=0.45, w=0.28, h=0.38, chin_dip=0.0):
    lm = []
    for i in range(478):
        a = i / 478 * math.pi * 2
        lm.append(P(cx + w / 2 * math.cos(a), cy + h / 2 * math.sin(a)))
    lm[1] = P(cx, cy)
    lm[152] = P(cx, cy + h / 2 - chin_dip)
    return lm


def shapes(**o):
    base = {
        "browDownLeft": 0.1, "browDownRight": 0.1, "mouthPressLeft": 0.05, "mouthPressRight": 0.05, "jawOpen": 0.02,
    }
    base.update(o)
    return base


def matrix(yaw_deg=0.0, pitch_deg=0.0):
    y, p = math.radians(yaw_deg), math.radians(pitch_deg)
    m = [[0.0] * 4 for _ in range(4)]
    # third column = forward axis
    m[0][2] = math.sin(y) * math.cos(p)
    m[1][2] = math.sin(p)
    m[2][2] = math.cos(y) * math.cos(p)
    m[3][3] = 1.0
    return m


def hand(cx, cy, spread=0.04):
    h = []
    for i in range(21):
        h.append(P(cx + ((i % 5) - 2) * spread * 0.5, cy + (i // 5) * spread * 0.6))
    h[0] = P(cx, cy + 0.08)
    h[9] = P(cx, cy)
    return h


def run(frames):
    agg = BehaviorAggregator()
    ts = 1000.0
    for f in frames:
        agg.process_frame(ts, **f)
        ts += DT
    return agg.summary()


def calm_stream(seconds=30):
    frames = []
    for i in range(seconds * FPS):
        blink = 0.9 if i % (4 * FPS) < 3 else 0.0
        frames.append({
            "face_landmarks": face(),
            "blendshapes": shapes(eyeBlinkLeft=blink, eyeBlinkRight=blink),
            "matrix": matrix(),
            "hands": [hand(0.25, 0.85), hand(0.75, 0.85)],
        })
    return frames


def stressed_stream(seconds=30):
    frames = []
    for i in range(seconds * FPS):
        t = i / FPS
        burst = int(t) % 5 == 0
        blink = 0.9 if (burst and i % 8 < 3) or (i % (2 * FPS) < 2) else 0.0
        away = 8 < t < 20
        dip = 0.02 if 3.0 < (t % 6) < 3.5 else 0.0
        rub_x = 0.5 + 0.05 * (1 if math.sin(t * math.pi * 4) >= 0 else -1)
        hands = [hand(0.47, 0.75), hand(rub_x + 0.03, 0.75)] if t > 4 else [hand(0.25, 0.85), hand(0.75, 0.85)]
        frames.append({
            "face_landmarks": face(chin_dip=dip),
            "blendshapes": shapes(
                eyeBlinkLeft=blink, eyeBlinkRight=blink,
                eyeLookOutLeft=0.9 if away else 0.0, eyeLookInRight=0.9 if away else 0.0,
                mouthPressLeft=0.5, mouthPressRight=0.5, browDownLeft=0.4, browDownRight=0.4,
            ),
            "matrix": matrix(0, -20 if t > 22 else 0),
            "hands": hands,
        })
    return frames


def test_tracker_version_and_contract():
    summary = run(calm_stream(10))
    assert summary["tracker"] == TRACKER_VERSION
    assert summary["extended"] is True
    assert summary["frames_analyzed"] == 200
    assert isinstance(summary["events"], list) and isinstance(summary["timeline"], list)
    # The contract must validate in the behaviour engine
    result = calculate_behavior_indicator(summary)
    assert result["available"] is True
    assert "self_soothing" in result["sub_scores"] and "tension" in result["sub_scores"]


def test_calm_vs_stressed_streams():
    calm = run(calm_stream())
    stressed = run(stressed_stream())

    assert calm["blink_rate_per_min"] < 20 < stressed["blink_rate_per_min"]
    assert stressed["blink_burst_count"] >= 3
    assert calm["gaze_aversion_ratio"] < 0.05 and stressed["gaze_aversion_ratio"] > 0.3
    assert stressed["hand_rub_count"] >= 1
    assert calm["jaw_clench_ratio"] < 0.1 and stressed["jaw_clench_ratio"] > 0.8
    assert stressed["swallow_count"] >= 3
    assert stressed["head_down_ratio"] > 0.2
    # A perfectly still synthetic subject is "frozen"; the fidgeting one is not
    assert calm["freeze_ratio"] > 0.5 and stressed["freeze_ratio"] < 0.3

    types = {e["type"] for e in stressed["events"]}
    assert {"blink_burst", "gaze_away", "jaw_clench", "swallow", "hand_rub", "head_down"} <= types
    assert len(stressed["timeline"]) >= 29

    calm_score = calculate_behavior_indicator(calm)["indicator"]
    stressed_score = calculate_behavior_indicator(stressed)["indicator"]
    assert stressed_score > calm_score + 25


def test_finger_clasp_and_face_touch():
    clasp = []
    for _ in range(15 * FPS):
        clasp.append({"face_landmarks": face(), "blendshapes": shapes(), "matrix": matrix(), "hands": [hand(0.5, 0.75), hand(0.5, 0.75)]})
    summary = run(clasp)
    assert summary["finger_clasp_ratio"] > 0.8
    assert any(e["type"] == "finger_clasp" for e in summary["events"])

    touch = []
    for i in range(20 * FPS):
        t = i / FPS
        touching = (t % 6) < 2
        touch.append({"face_landmarks": face(), "blendshapes": shapes(), "matrix": matrix(), "hands": [hand(0.5 if touching else 0.2, 0.45 if touching else 0.9)]})
    summary = run(touch)
    assert 3 <= summary["face_touch_count"] <= 4
    assert summary["face_touch_duration_sec"] > 5


def test_no_face_frames_are_graceful():
    frames = [{"face_landmarks": None, "blendshapes": None, "matrix": None, "hands": []} for _ in range(50)]
    summary = run(frames)
    assert summary["available"] is True
    assert summary["face_detected_ratio"] == 0.0
    result = calculate_behavior_indicator(summary)
    assert result["reliability"] < 0.5
