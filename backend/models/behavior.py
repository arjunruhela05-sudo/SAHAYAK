"""
Behavioural (video) feature contract.

The features are produced either

    * in the browser (MediaPipe Face / Hand / Pose Landmarkers on the live
      camera feed — the video never leaves the device), or
    * on the server from an uploaded video file
      (``services/video_behavior_engine.py``).

Both producers emit exactly this aggregated contract — never frames.
Every field is optional so a partial capture (e.g. hands never in frame)
still produces a valid assessment.

``extended`` marks captures produced by the v6 tracker, which adds the
self-soothing, muscle-tension and swallowing cue groups plus the
tracking-pattern ``events`` / ``timeline`` used on the responder side.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ExpressionFeatures(BaseModel):
    """Mean blend-shape activations (0-1) over the frames where a face was found."""

    brow_furrow: float = Field(default=0.0, ge=0, le=1)
    brow_raise: float = Field(default=0.0, ge=0, le=1)
    lip_press: float = Field(default=0.0, ge=0, le=1)
    mouth_frown: float = Field(default=0.0, ge=0, le=1)
    eye_squint: float = Field(default=0.0, ge=0, le=1)
    jaw_tension: float = Field(default=0.0, ge=0, le=1)
    smile: float = Field(default=0.0, ge=0, le=1)


class TrackingEvent(BaseModel):
    """One detected body-movement episode on the tracking-pattern timeline."""

    type: str = Field(..., min_length=1, max_length=40)
    start: float = Field(..., ge=0)
    duration: float = Field(default=0.0, ge=0)
    intensity: Optional[float] = Field(default=None, ge=0)
    note: Optional[str] = Field(default=None, max_length=120)


class TimelineSample(BaseModel):
    """Per-second cue intensities for the responder-side chart."""

    t: float = Field(..., ge=0)
    blink: Optional[float] = Field(default=None, ge=0)
    gaze_away: Optional[float] = Field(default=None, ge=0, le=1)
    self_touch: Optional[float] = Field(default=None, ge=0, le=1)
    hand_motion: Optional[float] = Field(default=None, ge=0)
    head_motion: Optional[float] = Field(default=None, ge=0)
    tension: Optional[float] = Field(default=None, ge=0, le=1)
    expression: Optional[float] = Field(default=None, ge=0, le=1)


class BehaviorFeatures(BaseModel):
    available: bool = True

    # Which tracker produced this capture
    extended: bool = False
    tracker: Optional[str] = Field(default=None, max_length=40)

    # Capture quality
    duration_sec: float = Field(default=0.0, ge=0, le=3600)
    frames_analyzed: int = Field(default=0, ge=0)
    fps: float = Field(default=0.0, ge=0, le=240)
    face_detected_ratio: float = Field(default=0.0, ge=0, le=1)
    hands_detected_ratio: float = Field(default=0.0, ge=0, le=1)
    pose_detected_ratio: float = Field(default=0.0, ge=0, le=1)

    # Eyes
    blink_count: int = Field(default=0, ge=0)
    blink_rate_per_min: float = Field(default=0.0, ge=0, le=300)
    blink_burst_count: int = Field(default=0, ge=0)          # rapid flurries of blinks
    blink_interval_cv: float = Field(default=0.0, ge=0, le=10)  # irregular blink rhythm
    gaze_aversion_ratio: float = Field(default=0.0, ge=0, le=1)
    gaze_shift_rate_per_min: float = Field(default=0.0, ge=0, le=600)
    eye_closure_ratio: float = Field(default=0.0, ge=0, le=1)

    # Hands / self-touch
    face_touch_count: int = Field(default=0, ge=0)
    face_touch_duration_sec: float = Field(default=0.0, ge=0)
    hand_movement_energy: float = Field(default=0.0, ge=0, le=10)
    hand_fidget_rate_per_min: float = Field(default=0.0, ge=0, le=600)
    hands_together_ratio: float = Field(default=0.0, ge=0, le=1)

    # Self-soothing / self-adaptor gestures (extended tracker)
    hand_rub_count: int = Field(default=0, ge=0)
    hand_rub_duration_sec: float = Field(default=0.0, ge=0)
    finger_clasp_ratio: float = Field(default=0.0, ge=0, le=1)
    arm_stroke_count: int = Field(default=0, ge=0)
    arm_stroke_duration_sec: float = Field(default=0.0, ge=0)
    self_hug_ratio: float = Field(default=0.0, ge=0, le=1)
    neck_touch_count: int = Field(default=0, ge=0)
    neck_touch_duration_sec: float = Field(default=0.0, ge=0)
    hair_touch_count: int = Field(default=0, ge=0)
    lip_bite_ratio: float = Field(default=0.0, ge=0, le=1)

    # Swallowing / throat (extended tracker; approximate from face mesh)
    swallow_count: int = Field(default=0, ge=0)
    swallow_rate_per_min: float = Field(default=0.0, ge=0, le=300)

    # Muscle tension / posture (extended tracker)
    shoulder_raise_ratio: float = Field(default=0.0, ge=0, le=1)
    shoulder_asymmetry: float = Field(default=0.0, ge=0, le=1)
    jaw_clench_ratio: float = Field(default=0.0, ge=0, le=1)
    freeze_ratio: float = Field(default=0.0, ge=0, le=1)
    slouch_ratio: float = Field(default=0.0, ge=0, le=1)
    lean_away_ratio: float = Field(default=0.0, ge=0, le=1)

    # Head / posture
    head_movement_energy: float = Field(default=0.0, ge=0, le=10)
    head_shake_rate_per_min: float = Field(default=0.0, ge=0, le=600)
    posture_shift_count: int = Field(default=0, ge=0)
    head_down_ratio: float = Field(default=0.0, ge=0, le=1)

    # Facial expression
    expression: ExpressionFeatures = Field(default_factory=ExpressionFeatures)

    # Tracking pattern (responder side only)
    events: Optional[List[TrackingEvent]] = None
    timeline: Optional[List[TimelineSample]] = None

    # Free-form extra numbers from the client (ignored by scoring, kept for audit)
    extras: Optional[Dict[str, Any]] = None
