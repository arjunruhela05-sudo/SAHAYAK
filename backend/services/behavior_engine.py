"""
Behaviour engine
================

Scores non-verbal stress cues extracted from video (in the browser, or
on the server from an uploaded file):

    * rapid / irregular blinking, eye closure
    * gaze aversion and restless gaze shifting
    * face touching
    * self-soothing gestures: rubbing hands, clasping / interlacing
      fingers, stroking the arms, self-hugging, touching the neck or
      hair, biting the lips
    * hand fidgeting, hand wringing
    * muscle tension: raised / uneven shoulders, jaw clenching,
      freezing (rigid stillness), slouching or leaning away
    * swallowing / throat movements (approximate, from the face mesh)
    * head movement, head shaking, looking down, posture shifts
    * tense facial expression (furrowed brow, pressed lips, frown, squint)

The producer sends aggregated numbers only (see models/behavior.py) plus,
for the responder view, a tracking-pattern event list.  The engine
validates capture quality, converts each cue into a 0-100 sub-score
using declared engineering ranges, and returns a transparent indicator
with cues.  Behaviour never determines risk on its own.
"""

from __future__ import annotations

from typing import Any, Dict, List

from models.behavior import BehaviorFeatures


# Engineering normalisation ranges (value -> 0..100)
RANGES = {
    "blink_rate_per_min": (18.0, 45.0),
    "blink_burst_per_min": (1.0, 6.0),
    "blink_interval_cv": (0.6, 1.4),
    "eye_closure_ratio": (0.08, 0.30),
    "gaze_aversion_ratio": (0.25, 0.70),
    "gaze_shift_rate_per_min": (10.0, 40.0),
    "face_touch_per_min": (0.5, 4.0),
    "face_touch_ratio": (0.03, 0.25),
    "hand_movement_energy": (0.10, 0.50),
    "hand_fidget_rate_per_min": (4.0, 20.0),
    "hands_together_ratio": (0.15, 0.60),
    "hand_rub_per_min": (0.5, 4.0),
    "hand_rub_ratio": (0.03, 0.25),
    "finger_clasp_ratio": (0.10, 0.50),
    "arm_stroke_per_min": (0.5, 3.0),
    "arm_stroke_ratio": (0.03, 0.20),
    "self_hug_ratio": (0.10, 0.45),
    "neck_touch_per_min": (0.3, 3.0),
    "hair_touch_per_min": (0.5, 4.0),
    "lip_bite_ratio": (0.05, 0.30),
    "swallow_rate_per_min": (3.0, 10.0),
    "shoulder_raise_ratio": (0.15, 0.55),
    "shoulder_asymmetry": (0.05, 0.20),
    "jaw_clench_ratio": (0.10, 0.45),
    "freeze_ratio": (0.20, 0.60),
    "slouch_ratio": (0.20, 0.60),
    "lean_away_ratio": (0.15, 0.50),
    "head_movement_energy": (0.08, 0.35),
    "head_shake_rate_per_min": (3.0, 15.0),
    "posture_shift_per_min": (1.0, 6.0),
    "head_down_ratio": (0.15, 0.50),
    "brow_furrow": (0.15, 0.50),
    "lip_press": (0.10, 0.40),
    "mouth_frown": (0.10, 0.40),
    "eye_squint": (0.15, 0.50),
    "jaw_tension": (0.10, 0.40),
}

SUB_WEIGHTS = {
    "blinking": 0.12,
    "gaze": 0.17,
    "face_touch": 0.11,
    "self_soothing": 0.15,
    "fidgeting": 0.12,
    "head_posture": 0.09,
    "tension": 0.11,
    "swallowing": 0.05,
    "expression": 0.08,
}

# Sub-scores that only exist with the extended (v6) tracker.
EXTENDED_GROUPS = ("self_soothing", "tension", "swallowing")
# Sub-scores that need the hands to be visible.
HAND_GROUPS = ("fidgeting", "self_soothing")

MIN_RELIABLE_DURATION_SEC = 8.0
MIN_FACE_RATIO = 0.40


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return round(max(0.0, min(100.0, (float(value) - low) / (high - low) * 100.0)), 1)


def parse_behavior_features(payload: Any) -> BehaviorFeatures:
    """Accept a dict / JSON-derived object and coerce it into the model."""
    if isinstance(payload, BehaviorFeatures):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("Behaviour features must be a JSON object.")
    return BehaviorFeatures(**payload)


def capture_quality(features: BehaviorFeatures) -> Dict[str, Any]:
    """How much can we trust this capture?  Returns a 0-1 reliability."""
    reasons: List[str] = []
    reliability = 1.0

    if features.duration_sec < MIN_RELIABLE_DURATION_SEC:
        reliability *= max(0.2, features.duration_sec / MIN_RELIABLE_DURATION_SEC)
        reasons.append("Short capture; behavioural rates are approximate.")

    if features.face_detected_ratio < MIN_FACE_RATIO:
        reliability *= 0.3
        reasons.append("Face was not visible for most of the recording.")
    elif features.face_detected_ratio < 0.75:
        reliability *= 0.7
        reasons.append("Face was intermittently out of frame.")

    if features.frames_analyzed < 60:
        reliability *= 0.5
        reasons.append("Very few frames were analysed.")

    return {
        "reliability": round(max(0.0, min(1.0, reliability)), 2),
        "hands_tracked": features.hands_detected_ratio >= 0.2,
        "pose_tracked": features.pose_detected_ratio >= 0.3,
        "notes": reasons,
    }


def calculate_behavior_indicator(features: BehaviorFeatures | Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert behavioural features into a 0-100 supplementary indicator
    with sub-scores, cues and a reliability estimate.
    """
    try:
        f = parse_behavior_features(features)
    except Exception as exc:  # pydantic validation error, wrong type ...
        return {
            "available": False,
            "indicator": 0.0,
            "reliability": 0.0,
            "sub_scores": {},
            "cues": [],
            "error": str(exc),
        }

    if not f.available or f.frames_analyzed == 0:
        return {
            "available": False,
            "indicator": 0.0,
            "reliability": 0.0,
            "sub_scores": {},
            "cues": [],
        }

    quality = capture_quality(f)
    minutes = max(f.duration_sec / 60.0, 1e-6)
    seconds = max(f.duration_sec, 1e-6)
    cues: List[str] = []

    # --- blinking -----------------------------------------------------
    blink_score = max(
        _scale(f.blink_rate_per_min, *RANGES["blink_rate_per_min"]),
        0.8 * _scale(f.eye_closure_ratio, *RANGES["eye_closure_ratio"]),
        0.7 * _scale(f.blink_burst_count / minutes, *RANGES["blink_burst_per_min"]),
        0.6 * _scale(f.blink_interval_cv, *RANGES["blink_interval_cv"]),
    )
    if f.blink_rate_per_min >= RANGES["blink_rate_per_min"][0] * 1.3:
        cues.append(f"Rapid blinking ({f.blink_rate_per_min:.0f} blinks/min; typical resting rate is 10-20).")
    elif f.eye_closure_ratio >= RANGES["eye_closure_ratio"][1] * 0.8:
        cues.append("Eyes were closed or half-closed for long stretches.")
    if f.blink_burst_count / minutes >= RANGES["blink_burst_per_min"][1] * 0.6:
        cues.append("Blinking came in rapid flurries rather than a steady rhythm.")

    # --- gaze ---------------------------------------------------------
    gaze_score = max(
        _scale(f.gaze_aversion_ratio, *RANGES["gaze_aversion_ratio"]),
        0.8 * _scale(f.gaze_shift_rate_per_min, *RANGES["gaze_shift_rate_per_min"]),
    )
    if f.gaze_aversion_ratio >= 0.45:
        cues.append(f"Avoided eye contact for {f.gaze_aversion_ratio * 100:.0f}% of the recording.")
    if f.gaze_shift_rate_per_min >= RANGES["gaze_shift_rate_per_min"][1] * 0.7:
        cues.append("Restless, darting gaze.")

    # --- face touching --------------------------------------------------
    touch_per_min = f.face_touch_count / minutes
    touch_ratio = f.face_touch_duration_sec / seconds
    face_touch_score = max(
        _scale(touch_per_min, *RANGES["face_touch_per_min"]),
        _scale(touch_ratio, *RANGES["face_touch_ratio"]),
    )
    if f.face_touch_count >= 2 and face_touch_score >= 35:
        cues.append(
            f"Repeated face touching ({f.face_touch_count} times, "
            f"{f.face_touch_duration_sec:.0f}s total) — a common self-soothing gesture."
        )

    # --- self-soothing gestures (extended, hands) -------------------------
    self_soothing_score = 0.0
    if f.extended and quality["hands_tracked"]:
        rub_per_min = f.hand_rub_count / minutes
        rub_ratio = f.hand_rub_duration_sec / seconds
        stroke_per_min = f.arm_stroke_count / minutes
        stroke_ratio = f.arm_stroke_duration_sec / seconds
        neck_per_min = f.neck_touch_count / minutes
        hair_per_min = f.hair_touch_count / minutes

        parts = [
            _scale(rub_per_min, *RANGES["hand_rub_per_min"]),
            _scale(rub_ratio, *RANGES["hand_rub_ratio"]),
            _scale(f.finger_clasp_ratio, *RANGES["finger_clasp_ratio"]),
            _scale(stroke_per_min, *RANGES["arm_stroke_per_min"]),
            _scale(stroke_ratio, *RANGES["arm_stroke_ratio"]),
            _scale(f.self_hug_ratio, *RANGES["self_hug_ratio"]),
            0.9 * _scale(neck_per_min, *RANGES["neck_touch_per_min"]),
            0.8 * _scale(hair_per_min, *RANGES["hair_touch_per_min"]),
            0.8 * _scale(f.lip_bite_ratio, *RANGES["lip_bite_ratio"]),
        ]
        parts.sort(reverse=True)
        # Strongest gesture dominates; a second distinct gesture adds a little.
        self_soothing_score = min(100.0, parts[0] + 0.25 * parts[1])

        if f.hand_rub_count >= 2 and rub_per_min >= RANGES["hand_rub_per_min"][0]:
            cues.append(f"Rubbing the hands together ({f.hand_rub_count} episodes, {f.hand_rub_duration_sec:.0f}s).")
        if f.finger_clasp_ratio >= RANGES["finger_clasp_ratio"][0] * 1.5:
            cues.append(f"Fingers clasped / interlaced for {f.finger_clasp_ratio * 100:.0f}% of the recording.")
        if f.arm_stroke_count >= 2 and stroke_per_min >= RANGES["arm_stroke_per_min"][0]:
            cues.append(f"Stroking or rubbing the arms ({f.arm_stroke_count} episodes).")
        if f.self_hug_ratio >= RANGES["self_hug_ratio"][0] * 1.5:
            cues.append("Arms wrapped around the body (self-hugging / closed posture).")
        if f.neck_touch_count >= 2 and neck_per_min >= RANGES["neck_touch_per_min"][0]:
            cues.append(f"Touching the neck or throat ({f.neck_touch_count} times).")
        if f.hair_touch_count >= 2 and hair_per_min >= RANGES["hair_touch_per_min"][0]:
            cues.append(f"Touching or pulling the hair ({f.hair_touch_count} times).")
        if f.lip_bite_ratio >= RANGES["lip_bite_ratio"][0] * 1.5:
            cues.append("Biting or rolling the lips.")

    # --- fidgeting -----------------------------------------------------
    if quality["hands_tracked"]:
        fidget_score = max(
            _scale(f.hand_movement_energy, *RANGES["hand_movement_energy"]),
            _scale(f.hand_fidget_rate_per_min, *RANGES["hand_fidget_rate_per_min"]),
            0.9 * _scale(f.hands_together_ratio, *RANGES["hands_together_ratio"]),
        )
        if f.hand_fidget_rate_per_min >= RANGES["hand_fidget_rate_per_min"][1] * 0.6:
            cues.append(f"Frequent hand fidgeting ({f.hand_fidget_rate_per_min:.0f} bursts/min).")
        if f.hands_together_ratio >= RANGES["hands_together_ratio"][1] * 0.7 and not (
            f.extended and f.finger_clasp_ratio >= RANGES["finger_clasp_ratio"][0] * 1.5
        ):
            cues.append("Hands clasped or wringing together for much of the recording.")
    else:
        fidget_score = 0.0

    # --- muscle tension / posture (extended) ------------------------------
    tension_score = 0.0
    if f.extended:
        parts = [
            _scale(f.jaw_clench_ratio, *RANGES["jaw_clench_ratio"]),
            _scale(f.freeze_ratio, *RANGES["freeze_ratio"]),
        ]
        if quality["pose_tracked"]:
            parts.extend([
                _scale(f.shoulder_raise_ratio, *RANGES["shoulder_raise_ratio"]),
                0.8 * _scale(f.shoulder_asymmetry, *RANGES["shoulder_asymmetry"]),
                0.8 * _scale(f.slouch_ratio, *RANGES["slouch_ratio"]),
                0.7 * _scale(f.lean_away_ratio, *RANGES["lean_away_ratio"]),
            ])
        parts.sort(reverse=True)
        tension_score = min(100.0, parts[0] + 0.25 * parts[1]) if len(parts) > 1 else parts[0]

        if f.jaw_clench_ratio >= RANGES["jaw_clench_ratio"][0] * 1.5:
            cues.append(f"Jaw clenched for {f.jaw_clench_ratio * 100:.0f}% of the recording (muscle tension).")
        if f.freeze_ratio >= RANGES["freeze_ratio"][0] * 1.5:
            cues.append(f"Rigid, frozen stillness for {f.freeze_ratio * 100:.0f}% of the recording.")
        if quality["pose_tracked"]:
            if f.shoulder_raise_ratio >= RANGES["shoulder_raise_ratio"][0] * 1.5:
                cues.append("Shoulders raised / hunched towards the ears (tension).")
            if f.shoulder_asymmetry >= RANGES["shoulder_asymmetry"][1] * 0.7:
                cues.append("Uneven, guarded shoulder posture.")
            if f.slouch_ratio >= RANGES["slouch_ratio"][0] * 1.5:
                cues.append("Slumped / collapsed posture for much of the recording.")
            if f.lean_away_ratio >= RANGES["lean_away_ratio"][0] * 1.5:
                cues.append("Leaning away from the camera / interviewer.")

    # --- swallowing (extended) -------------------------------------------
    swallow_score = 0.0
    if f.extended:
        swallow_score = _scale(f.swallow_rate_per_min, *RANGES["swallow_rate_per_min"])
        if f.swallow_count >= 3 and f.swallow_rate_per_min >= RANGES["swallow_rate_per_min"][0] * 1.3:
            cues.append(
                f"Frequent swallowing / throat movements ({f.swallow_rate_per_min:.0f} per min, approximate)."
            )

    # --- head & posture ---------------------------------------------------
    head_score = max(
        _scale(f.head_movement_energy, *RANGES["head_movement_energy"]),
        _scale(f.head_shake_rate_per_min, *RANGES["head_shake_rate_per_min"]),
        _scale(f.posture_shift_count / minutes, *RANGES["posture_shift_per_min"]),
        0.9 * _scale(f.head_down_ratio, *RANGES["head_down_ratio"]),
    )
    if f.head_down_ratio >= 0.35:
        cues.append("Head lowered / looking down for extended periods.")
    if f.head_shake_rate_per_min >= RANGES["head_shake_rate_per_min"][1] * 0.6:
        cues.append("Frequent head shaking.")
    if f.posture_shift_count / minutes >= RANGES["posture_shift_per_min"][1] * 0.7:
        cues.append("Restless posture shifts.")

    # --- expression -------------------------------------------------------
    e = f.expression
    expression_score = (
        0.30 * _scale(e.brow_furrow, *RANGES["brow_furrow"])
        + 0.25 * _scale(e.lip_press, *RANGES["lip_press"])
        + 0.20 * _scale(e.mouth_frown, *RANGES["mouth_frown"])
        + 0.15 * _scale(e.eye_squint, *RANGES["eye_squint"])
        + 0.10 * _scale(e.jaw_tension, *RANGES["jaw_tension"])
    )
    # A sustained genuine smile lowers the tension estimate slightly.
    expression_score = max(0.0, expression_score - 20.0 * e.smile)
    if e.brow_furrow >= 0.30:
        cues.append("Furrowed brow / tense forehead.")
    if e.lip_press >= 0.25:
        cues.append("Lips pressed tightly together.")
    if e.mouth_frown >= 0.25:
        cues.append("Downturned mouth / distressed expression.")

    sub_scores = {
        "blinking": round(blink_score, 1),
        "gaze": round(gaze_score, 1),
        "face_touch": round(face_touch_score, 1),
        "self_soothing": round(self_soothing_score, 1),
        "fidgeting": round(fidget_score, 1),
        "head_posture": round(head_score, 1),
        "tension": round(tension_score, 1),
        "swallowing": round(swallow_score, 1),
        "expression": round(expression_score, 1),
    }

    # Only weight what was actually tracked; never score "no gesture"
    # for cues the producer could not observe.
    weights = dict(SUB_WEIGHTS)
    if not f.extended:
        for key in EXTENDED_GROUPS:
            weights.pop(key, None)
    if not quality["hands_tracked"]:
        for key in HAND_GROUPS:
            weights.pop(key, None)
    total = sum(weights.values())
    weights = {k: v / total for k, v in weights.items()}

    raw = sum(sub_scores[k] * w for k, w in weights.items())
    indicator = raw * quality["reliability"]

    return {
        "available": True,
        "indicator": round(max(0.0, min(100.0, indicator)), 1),
        "raw_indicator": round(raw, 1),
        "reliability": quality["reliability"],
        "quality_notes": quality["notes"],
        "sub_scores": sub_scores,
        "cues": cues,
        "tracked_groups": sorted(weights.keys()),
        "event_count": len(f.events or []),
    }


__all__ = [
    "calculate_behavior_indicator",
    "parse_behavior_features",
    "BehaviorFeatures",
]
