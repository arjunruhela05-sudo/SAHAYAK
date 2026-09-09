"""
Video behaviour engine (server side)
====================================

Analyses the *footage* of an uploaded video file for the same body
language cues the browser tracker extracts from the live camera:

    blinking pattern, eye contact / gaze, face / neck / hair touching,
    self-soothing gestures (rubbing hands, clasping fingers, stroking the
    arms, self-hugging, lip biting), hand fidgeting, muscle tension
    (jaw clench, raised / uneven shoulders, slouching, leaning away,
    freezing), swallowing / throat movements, head movement and posture
    shifts, facial tension.

It is a direct port of ``frontend/src/lib/behaviorAnalyzer.js`` so that a
live capture and an uploaded file produce the same feature contract
(``models/behavior.py``), including the tracking-pattern ``events`` and
per-second ``timeline`` used on the responder side.

Dependencies (optional): ``mediapipe`` and ``opencv-python-headless``.
When they are missing the engine returns ``{"available": False}`` and
the assessment continues with audio only.  Model files are downloaded
once into ``SAHAYAK_MEDIAPIPE_DIR`` (default ``backend/models_cache``).
Frames are processed in memory and never stored.
"""

from __future__ import annotations

import math
import os
import statistics
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional


TRACKER_VERSION = "server-v6"

MODEL_URLS = {
    "face_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
        "face_landmarker/float16/1/face_landmarker.task"
    ),
    "hand_landmarker.task": (
        "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
        "hand_landmarker/float16/1/hand_landmarker.task"
    ),
    "pose_landmarker_lite.task": (
        "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
        "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
    ),
}

TARGET_FPS = float(os.getenv("SAHAYAK_VIDEO_FPS", "12"))
MAX_ANALYSIS_SEC = float(os.getenv("SAHAYAK_VIDEO_MAX_SEC", "600"))

# Thresholds — identical to the browser analyser.
BLINK_ON = 0.5
BLINK_OFF = 0.3
BLINK_BURST_WINDOW_MS = 2000
BLINK_BURST_MIN = 3
GAZE_H_AVERT = 0.45
GAZE_DOWN_AVERT = 0.5
HEAD_YAW_AVERT_DEG = 22
HEAD_PITCH_AVERT_DEG = 20
HEAD_DOWN_DEG = -12
HEAD_SHAKE_SWING_DEG = 6
FACE_TOUCH_MARGIN = 0.12
FIDGET_SPEED = 0.6
HANDS_TOGETHER_DIST = 0.13
POSTURE_SHIFT_DIST = 0.08
CLASP_DIST = 0.045
RUB_REL_SPEED = 0.25
RUB_MIN_REVERSALS = 2
RUB_WINDOW_MS = 1500
ARM_STROKE_DIST = 0.07
ARM_STROKE_SPEED = 0.15
JAW_CLENCH_PRESS = 0.35
LIP_BITE = 0.35
SWALLOW_DEV = 0.012
SWALLOW_MIN_MS = 200
SWALLOW_MAX_MS = 900
SWALLOW_REFRACTORY_MS = 1200
FREEZE_WINDOW_MS = 1000
FREEZE_HEAD_RANGE_DEG = 2.5
FREEZE_HAND_RANGE = 0.02
FREEZE_MIN_MS = 3000
EPISODE_MIN_MS = {
    "face_touch": 150, "neck_touch": 150, "hair_touch": 150,
    "hand_rub": 400, "arm_stroke": 400,
    "finger_clasp": 1500, "self_hug": 1500, "gaze_away": 1000, "head_down": 1500,
    "jaw_clench": 1000, "shoulder_raise": 1500, "freeze": FREEZE_MIN_MS,
}

FINGERTIPS = [4, 8, 12, 16, 20, 0, 9]
TIPS = [8, 12, 16, 20]
MCPS = [5, 9, 13, 17]


# ---------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------

class P:
    __slots__ = ("x", "y")

    def __init__(self, x: float, y: float):
        self.x = float(x)
        self.y = float(y)


def _dist(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def _seg_dist(p, a, b) -> float:
    abx, aby = b.x - a.x, b.y - a.y
    len2 = abx * abx + aby * aby or 1e-9
    t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / len2
    t = max(0.0, min(1.0, t))
    return math.hypot(p.x - (a.x + t * abx), p.y - (a.y + t * aby))


def _median(values: List[float]) -> float:
    return float(statistics.median(values)) if values else 0.0


def _mean(values: List[float]) -> float:
    return float(sum(values) / len(values)) if values else 0.0


def _sign(v: float) -> int:
    return (v > 0) - (v < 0)


def _blend(shapes: Dict[str, float], name: str) -> float:
    return float(shapes.get(name, 0.0))


def _face_box(landmarks) -> Dict[str, float]:
    xs = [p.x for p in landmarks]
    ys = [p.y for p in landmarks]
    min_x, max_x, min_y, max_y = min(xs), max(xs), min(ys), max(ys)
    return {
        "minX": min_x, "minY": min_y, "maxX": max_x, "maxY": max_y,
        "cx": (min_x + max_x) / 2, "cy": (min_y + max_y) / 2,
        "w": max_x - min_x, "h": max_y - min_y,
    }


def _head_pose(matrix) -> Optional[Dict[str, float]]:
    """Yaw / pitch (deg) from a 4x4 facial transformation matrix (row-major)."""
    if matrix is None:
        return None
    try:
        fx, fy, fz = float(matrix[0][2]), float(matrix[1][2]), float(matrix[2][2])
    except Exception:
        return None
    yaw = math.degrees(math.atan2(fx, fz))
    pitch = math.degrees(math.asin(max(-1.0, min(1.0, fy))))
    return {"yaw": yaw, "pitch": pitch}


class _Episode:
    __slots__ = ("type", "min_ms", "on", "start", "count", "duration")

    def __init__(self, type_: str, min_ms: float):
        self.type = type_
        self.min_ms = min_ms
        self.on = False
        self.start = 0.0
        self.count = 0
        self.duration = 0.0

    def update(self, active: bool, ts: float, events: List[Dict[str, Any]], origin: float) -> None:
        if active and not self.on:
            self.on = True
            self.start = ts
        elif not active and self.on:
            self.on = False
            dur = ts - self.start
            if dur >= self.min_ms:
                self.count += 1
                self.duration += dur / 1000.0
                events.append({
                    "type": self.type,
                    "start": round((self.start - origin) / 1000.0, 2),
                    "duration": round(dur / 1000.0, 2),
                })


# ---------------------------------------------------------------------
# aggregator (port of createBehaviorAnalyzer)
# ---------------------------------------------------------------------

class BehaviorAggregator:
    """Frame-by-frame aggregation of body-language cues (numbers only)."""

    def __init__(self) -> None:
        self.start_ts = 0.0
        self.last_ts = 0.0
        self.frames = 0
        self.face_frames = 0
        self.hand_frames = 0
        self.pose_frames = 0
        self.events: List[Dict[str, Any]] = []
        self.timeline: List[Dict[str, Any]] = []
        self.sec: Optional[Dict[str, Any]] = None
        # eyes
        self.blink_count = 0
        self.blink_on = False
        self.closed_frames = 0
        self.blink_times: List[float] = []
        self.blink_bursts = 0
        self.last_burst_ts = -1e9
        # gaze
        self.averted_frames = 0
        self.gaze_shifts = 0
        self.last_gaze_bucket: Optional[str] = None
        # hands
        self.prev_hands = None
        self.speed_sum = 0.0
        self.speed_frames = 0
        self.fidget_bursts = 0
        self.last_fidget_ts = -1e9
        self.fidget_on = False
        self.hands_together_frames = 0
        self.clasp_frames = 0
        self.rub_rel = None
        self.rub_reversals: List[float] = []
        self.rub_last_sign = 0
        self.lip_bite_frames = 0
        # pose
        self.shoulder_base = None
        self.shoulder_samples: List[float] = []
        self.torso_base = None
        self.torso_samples: List[float] = []
        self.width_base = None
        self.width_samples: List[float] = []
        self.shoulder_raise_frames = 0
        self.shoulder_asym_sum = 0.0
        self.slouch_frames = 0
        self.lean_away_frames = 0
        self.self_hug_frames = 0
        # head
        self.prev_pose = None
        self.head_speed_sum = 0.0
        self.head_frames = 0
        self.head_down_frames = 0
        self.yaw_vel_sign = 0
        self.yaw_swing_start = None
        self.head_shakes = 0
        self.last_shake_ts = -1e9
        # posture shift
        self.posture_anchor = None
        self.posture_shifts = 0
        self.last_posture_ts = -1e9
        # tension / freeze
        self.jaw_clench_frames = 0
        self.freeze_since = None
        self.freeze_ms = 0.0
        self.motion_buf: List[Dict[str, Any]] = []
        # swallow
        self.throat_buf: List[tuple] = []
        self.swallow_on = False
        self.swallow_start = 0.0
        self.swallow_count = 0
        self.last_swallow_ts = -1e9
        # expression
        self.expr = {k: 0.0 for k in ("brow_furrow", "brow_raise", "lip_press", "mouth_frown", "eye_squint", "jaw_tension", "smile")}
        # episodes
        self.ep = {name: _Episode(name, ms) for name, ms in EPISODE_MIN_MS.items()}

    # ------------------------------------------------------------------
    def _new_second(self, t: int) -> Dict[str, Any]:
        return {"t": t, "frames": 0, "faceFrames": 0, "blinks": 0, "away": 0, "touch": 0,
                "handSpeed": 0.0, "handN": 0, "headSpeed": 0.0, "headN": 0, "tension": 0, "expr": 0.0}

    def _flush_second(self) -> None:
        c = self.sec
        if not c or not c["frames"]:
            return
        ff = max(c["faceFrames"], 1)
        self.timeline.append({
            "t": c["t"],
            "blink": c["blinks"],
            "gaze_away": round(c["away"] / ff, 2),
            "self_touch": round(c["touch"] / c["frames"], 2),
            "hand_motion": round(c["handSpeed"] / c["handN"] if c["handN"] else 0.0, 3),
            "head_motion": round(c["headSpeed"] / c["headN"] / 60.0 if c["headN"] else 0.0, 3),
            "tension": round(c["tension"] / c["frames"], 2),
            "expression": round(c["expr"] / ff, 2),
        })

    def _rel(self, ts: float) -> float:
        return round((ts - self.start_ts) / 1000.0, 2)

    # ------------------------------------------------------------------
    def process_frame(
        self,
        ts: float,
        face_landmarks=None,
        blendshapes: Optional[Dict[str, float]] = None,
        matrix=None,
        hands: Optional[List[List[P]]] = None,
        pose=None,
        pose_visibility: Optional[List[float]] = None,
    ) -> None:
        """``ts`` in milliseconds; landmarks as objects with ``.x`` / ``.y``."""
        if not self.start_ts:
            self.start_ts = ts
        dt = (ts - self.last_ts) / 1000.0 if self.last_ts else 0.0
        self.last_ts = ts
        self.frames += 1

        sec_idx = int((ts - self.start_ts) // 1000)
        if not self.sec or self.sec["t"] != sec_idx:
            self._flush_second()
            self.sec = self._new_second(sec_idx)
        sec = self.sec
        sec["frames"] += 1

        events = self.events
        origin = self.start_ts
        hands = hands or []

        box = None
        head = None
        averted = False
        head_speed = 0.0
        jaw_clench = False
        mouth_open = 0.0

        if face_landmarks and blendshapes is not None:
            self.face_frames += 1
            sec["faceFrames"] += 1
            box = _face_box(face_landmarks)
            head = _head_pose(matrix)
            sh = blendshapes

            # blinking
            blink_score = (_blend(sh, "eyeBlinkLeft") + _blend(sh, "eyeBlinkRight")) / 2
            if not self.blink_on and blink_score > BLINK_ON:
                self.blink_on = True
                self.blink_count += 1
                sec["blinks"] += 1
                self.blink_times.append(ts)
                recent = [t for t in self.blink_times if ts - t <= BLINK_BURST_WINDOW_MS]
                if len(recent) >= BLINK_BURST_MIN and ts - self.last_burst_ts > BLINK_BURST_WINDOW_MS:
                    self.blink_bursts += 1
                    self.last_burst_ts = ts
                    events.append({"type": "blink_burst", "start": self._rel(recent[0]),
                                   "duration": round((ts - recent[0]) / 1000.0, 2), "intensity": len(recent)})
            elif self.blink_on and blink_score < BLINK_OFF:
                self.blink_on = False
            if blink_score > BLINK_ON:
                self.closed_frames += 1

            # gaze
            look_left = (_blend(sh, "eyeLookOutLeft") + _blend(sh, "eyeLookInRight")) / 2
            look_right = (_blend(sh, "eyeLookInLeft") + _blend(sh, "eyeLookOutRight")) / 2
            look_down = (_blend(sh, "eyeLookDownLeft") + _blend(sh, "eyeLookDownRight")) / 2
            look_up = (_blend(sh, "eyeLookUpLeft") + _blend(sh, "eyeLookUpRight")) / 2
            gaze_h = look_left - look_right
            gaze_v = look_up - look_down
            averted = (
                abs(gaze_h) > GAZE_H_AVERT
                or look_down > GAZE_DOWN_AVERT
                or bool(head and (abs(head["yaw"]) > HEAD_YAW_AVERT_DEG or abs(head["pitch"]) > HEAD_PITCH_AVERT_DEG))
            )
            if averted:
                self.averted_frames += 1
                sec["away"] += 1
            self.ep["gaze_away"].update(averted, ts, events, origin)

            bucket = ("L" if gaze_h > 0.3 else "R" if gaze_h < -0.3 else "C") + ("U" if gaze_v > 0.3 else "D" if gaze_v < -0.3 else "C")
            if self.last_gaze_bucket and bucket != self.last_gaze_bucket:
                self.gaze_shifts += 1
            self.last_gaze_bucket = bucket

            # head pose
            head_down = False
            if head:
                head_down = head["pitch"] < HEAD_DOWN_DEG or look_down > 0.6
                if head_down:
                    self.head_down_frames += 1
                if self.prev_pose and dt > 0:
                    dyaw = head["yaw"] - self.prev_pose["yaw"]
                    dpitch = head["pitch"] - self.prev_pose["pitch"]
                    head_speed = math.hypot(dyaw, dpitch) / dt
                    self.head_speed_sum += head_speed
                    self.head_frames += 1
                    sec["headSpeed"] += head_speed
                    sec["headN"] += 1
                    sign = _sign(dyaw)
                    if sign != 0:
                        if self.yaw_swing_start is None:
                            self.yaw_swing_start = self.prev_pose["yaw"]
                        if self.yaw_vel_sign != 0 and sign != self.yaw_vel_sign:
                            swing = abs(self.prev_pose["yaw"] - self.yaw_swing_start)
                            if swing >= HEAD_SHAKE_SWING_DEG and ts - self.last_shake_ts > 250:
                                self.head_shakes += 1
                                self.last_shake_ts = ts
                                events.append({"type": "head_shake", "start": self._rel(ts), "duration": 0.3, "intensity": round(swing, 1)})
                            self.yaw_swing_start = self.prev_pose["yaw"]
                        self.yaw_vel_sign = sign
                self.prev_pose = head
            self.ep["head_down"].update(head_down, ts, events, origin)

            # posture shift
            if not self.posture_anchor:
                self.posture_anchor = (box["cx"], box["cy"])
            moved = math.hypot(box["cx"] - self.posture_anchor[0], box["cy"] - self.posture_anchor[1])
            if moved > POSTURE_SHIFT_DIST:
                if ts - self.last_posture_ts > 1500:
                    self.posture_shifts += 1
                    self.last_posture_ts = ts
                    events.append({"type": "posture_shift", "start": self._rel(ts), "duration": 0.5, "intensity": round(moved, 3)})
                self.posture_anchor = (box["cx"], box["cy"])

            # expression
            brow_furrow = (_blend(sh, "browDownLeft") + _blend(sh, "browDownRight")) / 2
            lip_press = (_blend(sh, "mouthPressLeft") + _blend(sh, "mouthPressRight")) / 2
            frown = (_blend(sh, "mouthFrownLeft") + _blend(sh, "mouthFrownRight")) / 2
            squint = (_blend(sh, "eyeSquintLeft") + _blend(sh, "eyeSquintRight")) / 2
            jaw_forward = _blend(sh, "jawForward")
            cheek_squint = (_blend(sh, "cheekSquintLeft") + _blend(sh, "cheekSquintRight")) / 2
            mouth_open = _blend(sh, "jawOpen")
            self.expr["brow_furrow"] += brow_furrow
            self.expr["brow_raise"] += _blend(sh, "browInnerUp")
            self.expr["lip_press"] += lip_press
            self.expr["mouth_frown"] += frown
            self.expr["eye_squint"] += squint
            self.expr["jaw_tension"] += max(jaw_forward, _blend(sh, "mouthPucker") * 0.5)
            self.expr["smile"] += (_blend(sh, "mouthSmileLeft") + _blend(sh, "mouthSmileRight")) / 2
            sec["expr"] += (brow_furrow + lip_press + frown) / 3

            lip_roll = max(_blend(sh, "mouthRollLower"), _blend(sh, "mouthRollUpper"))
            if lip_roll > LIP_BITE:
                self.lip_bite_frames += 1

            jaw_clench = mouth_open < 0.06 and (lip_press > JAW_CLENCH_PRESS or jaw_forward > 0.3 or (cheek_squint > 0.2 and lip_press > 0.2))
            if jaw_clench:
                self.jaw_clench_frames += 1
            self.ep["jaw_clench"].update(jaw_clench, ts, events, origin)

            # swallowing (approximate)
            throat = (face_landmarks[152].y - face_landmarks[1].y) / max(box["h"], 1e-3)
            self.throat_buf.append((ts, throat))
            while self.throat_buf and ts - self.throat_buf[0][0] > 1500:
                self.throat_buf.pop(0)
            if len(self.throat_buf) >= 8:
                base = _median([v for _, v in self.throat_buf[:-3]])
                dip = base - throat
                still = head_speed < 30 and mouth_open < 0.12
                if not self.swallow_on and dip > SWALLOW_DEV and still and ts - self.last_swallow_ts > SWALLOW_REFRACTORY_MS:
                    self.swallow_on = True
                    self.swallow_start = ts
                elif self.swallow_on and (dip < SWALLOW_DEV * 0.4 or not still):
                    self.swallow_on = False
                    dur = ts - self.swallow_start
                    if SWALLOW_MIN_MS <= dur <= SWALLOW_MAX_MS and still:
                        self.swallow_count += 1
                        self.last_swallow_ts = ts
                        events.append({"type": "swallow", "start": self._rel(self.swallow_start), "duration": round(dur / 1000.0, 2), "note": "approximate"})
                elif self.swallow_on and ts - self.swallow_start > SWALLOW_MAX_MS:
                    self.swallow_on = False
        else:
            self.ep["gaze_away"].update(False, ts, events, origin)
            self.ep["head_down"].update(False, ts, events, origin)
            self.ep["jaw_clench"].update(False, ts, events, origin)

        # pose
        shoulder_raised = False
        self_hug = False
        arms = None
        if pose is not None and len(pose) >= 25:
            vis = pose_visibility or [1.0] * len(pose)

            def v(i: int) -> bool:
                return vis[i] > 0.5

            if v(11) and v(12):
                self.pose_frames += 1
                L, R = pose[11], pose[12]
                width = max(_dist(L, R), 1e-3)
                shoulder_y = (L.y + R.y) / 2
                ear_y = (pose[7].y + pose[8].y) / 2 if v(7) and v(8) else pose[0].y
                neck = (shoulder_y - ear_y) / width
                torso = (shoulder_y - pose[0].y) / width
                asym = abs(L.y - R.y) / width
                self.shoulder_asym_sum += asym
                if len(self.shoulder_samples) < 60:
                    self.shoulder_samples.append(neck)
                    self.torso_samples.append(torso)
                    self.width_samples.append(width)
                else:
                    if self.shoulder_base is None:
                        self.shoulder_base = _median(self.shoulder_samples)
                        self.torso_base = _median(self.torso_samples)
                        self.width_base = _median(self.width_samples)
                    shoulder_raised = neck < self.shoulder_base * 0.82
                    if shoulder_raised:
                        self.shoulder_raise_frames += 1
                    if torso < self.torso_base * 0.85:
                        self.slouch_frames += 1
                    if width < self.width_base * 0.85:
                        self.lean_away_frames += 1

                if v(13) and v(14) and v(15) and v(16):
                    arms = {
                        "left": {"shoulder": L, "elbow": pose[13], "wrist": pose[15]},
                        "right": {"shoulder": R, "elbow": pose[14], "wrist": pose[16]},
                    }
                    mid_x = (L.x + R.x) / 2
                    hip_y = (pose[23].y + pose[24].y) / 2 if v(23) and v(24) else shoulder_y + width * 1.6

                    def torso_band(p) -> bool:
                        return shoulder_y - width * 0.1 < p.y < hip_y

                    l_across = (pose[15].x - mid_x) * (L.x - mid_x) < 0 and torso_band(pose[15]) and _seg_dist(pose[15], R, pose[14]) < ARM_STROKE_DIST * 1.4
                    r_across = (pose[16].x - mid_x) * (R.x - mid_x) < 0 and torso_band(pose[16]) and _seg_dist(pose[16], L, pose[13]) < ARM_STROKE_DIST * 1.4
                    self_hug = l_across and r_across
                    if self_hug:
                        self.self_hug_frames += 1
        self.ep["shoulder_raise"].update(shoulder_raised, ts, events, origin)
        self.ep["self_hug"].update(self_hug, ts, events, origin)
        if shoulder_raised or jaw_clench or self_hug:
            sec["tension"] += 1

        # hands
        touching = neck = hair = clasp = rub = stroke = False
        hand_speed = 0.0
        if hands:
            self.hand_frames += 1
            if box:
                m = FACE_TOUCH_MARGIN
                bx = box

                def in_face(p) -> bool:
                    return bx["minX"] - m < p.x < bx["maxX"] + m and bx["minY"] - m * 0.5 < p.y < bx["maxY"] + m * 0.4

                def in_neck(p) -> bool:
                    return bx["minX"] + bx["w"] * 0.15 < p.x < bx["maxX"] - bx["w"] * 0.15 and bx["maxY"] + m * 0.4 <= p.y < bx["maxY"] + bx["h"] * 0.55

                def in_hair(p) -> bool:
                    return bx["minX"] - m < p.x < bx["maxX"] + m and bx["minY"] - bx["h"] * 0.6 < p.y < bx["minY"] - m * 0.5

                for h in hands:
                    for i in FINGERTIPS:
                        if i >= len(h):
                            continue
                        p = h[i]
                        if in_face(p):
                            touching = True
                        elif in_neck(p):
                            neck = True
                        elif in_hair(p):
                            hair = True

            if self.prev_hands and dt > 0:
                total = 0.0
                n = 0
                for h in hands:
                    best = None
                    for ph in self.prev_hands:
                        d = _dist(h[0], ph[0])
                        if best is None or d < best:
                            best = d
                    if best is not None and best < 0.3:
                        total += best / dt
                        n += 1
                if n:
                    hand_speed = total / n
                    self.speed_sum += hand_speed
                    self.speed_frames += 1
                    sec["handSpeed"] += hand_speed
                    sec["handN"] += 1
                    if not self.fidget_on and hand_speed > FIDGET_SPEED and ts - self.last_fidget_ts > 300:
                        self.fidget_bursts += 1
                        self.last_fidget_ts = ts
                        self.fidget_on = True
                        events.append({"type": "fidget", "start": self._rel(ts), "duration": 0.3, "intensity": round(hand_speed, 2)})
                    elif self.fidget_on and hand_speed < FIDGET_SPEED * 0.5:
                        self.fidget_on = False
            self.prev_hands = hands

            if len(hands) == 2:
                a, b = hands
                palm = _dist(a[9], b[9])
                if palm < HANDS_TOGETHER_DIST:
                    self.hands_together_frames += 1

                    def near(tips_of, mcps_of) -> int:
                        return sum(1 for i in TIPS if any(_dist(tips_of[i], mcps_of[j]) < CLASP_DIST for j in MCPS))

                    clasp = near(a, b) >= 2 and near(b, a) >= 2

                    rel = (a[9].x - b[9].x, a[9].y - b[9].y)
                    if self.rub_rel and dt > 0:
                        vx = (rel[0] - self.rub_rel[0]) / dt
                        vy = (rel[1] - self.rub_rel[1]) / dt
                        rel_speed = math.hypot(vx, vy)
                        axis = vx if abs(vx) >= abs(vy) else vy
                        sign = _sign(axis)
                        if rel_speed > RUB_REL_SPEED and sign != 0:
                            if self.rub_last_sign != 0 and sign != self.rub_last_sign:
                                self.rub_reversals.append(ts)
                            self.rub_last_sign = sign
                    self.rub_rel = rel
                    self.rub_reversals = [t for t in self.rub_reversals if ts - t <= RUB_WINDOW_MS]
                    rub = len(self.rub_reversals) >= RUB_MIN_REVERSALS
                else:
                    self.rub_rel = None
                    self.rub_reversals = []
                    self.rub_last_sign = 0
            else:
                self.rub_rel = None
                self.rub_reversals = []
                self.rub_last_sign = 0
            if clasp:
                self.clasp_frames += 1

            if arms:
                for h in hands:
                    wrist = h[0]
                    for side in ("left", "right"):
                        arm = arms[side]
                        other = arms["right"] if side == "left" else arms["left"]
                        if _dist(wrist, arm["wrist"]) > _dist(wrist, other["wrist"]):
                            continue
                        d_upper = _seg_dist(wrist, other["shoulder"], other["elbow"])
                        d_fore = _seg_dist(wrist, other["elbow"], other["wrist"])
                        if min(d_upper, d_fore) < ARM_STROKE_DIST and hand_speed > ARM_STROKE_SPEED:
                            stroke = True
        else:
            self.prev_hands = None
            self.rub_rel = None
            self.rub_reversals = []
            self.rub_last_sign = 0

        self.ep["face_touch"].update(touching, ts, events, origin)
        self.ep["neck_touch"].update(neck, ts, events, origin)
        self.ep["hair_touch"].update(hair, ts, events, origin)
        self.ep["finger_clasp"].update(clasp, ts, events, origin)
        self.ep["hand_rub"].update(rub, ts, events, origin)
        self.ep["arm_stroke"].update(stroke, ts, events, origin)
        if touching or neck or hair or rub or stroke:
            sec["touch"] += 1

        still = False
        if face_landmarks and head:
            wrists = [h[0] for h in hands] if hands else []
            self.motion_buf.append({
                "ts": ts, "yaw": head["yaw"], "pitch": head["pitch"],
                "wx": _mean([w.x for w in wrists]) if wrists else None,
                "wy": _mean([w.y for w in wrists]) if wrists else None,
            })
            while self.motion_buf and ts - self.motion_buf[0]["ts"] > FREEZE_WINDOW_MS:
                self.motion_buf.pop(0)
            if len(self.motion_buf) >= 5 and ts - self.motion_buf[0]["ts"] >= FREEZE_WINDOW_MS * 0.8:
                yaws = [b["yaw"] for b in self.motion_buf]
                pitches = [b["pitch"] for b in self.motion_buf]
                head_range = max(max(yaws) - min(yaws), max(pitches) - min(pitches))
                with_hands = [b for b in self.motion_buf if b["wx"] is not None]
                hand_range = 0.0
                if len(with_hands) >= 3:
                    xs = [b["wx"] for b in with_hands]
                    ys = [b["wy"] for b in with_hands]
                    hand_range = max(max(xs) - min(xs), max(ys) - min(ys))
                hands_stable = not with_hands or len(with_hands) == len(self.motion_buf)
                still = head_range < FREEZE_HEAD_RANGE_DEG and hand_range < FREEZE_HAND_RANGE and hands_stable
        else:
            self.motion_buf = []
        if still:
            if self.freeze_since is None:
                self.freeze_since = ts
        else:
            if self.freeze_since is not None and ts - self.freeze_since >= FREEZE_MIN_MS:
                self.freeze_ms += ts - self.freeze_since
            self.freeze_since = None
        self.ep["freeze"].update(still, ts, events, origin)

    # ------------------------------------------------------------------
    def summary(self) -> Dict[str, Any]:
        elapsed = max((self.last_ts - self.start_ts) / 1000.0, 0.001)
        minutes = elapsed / 60.0
        face_frames = max(self.face_frames, 1)
        frames = max(self.frames, 1)
        expression = {k: round(min(1.0, v / face_frames), 3) for k, v in self.expr.items()}

        ts = self.last_ts
        events = list(self.events)
        counts: Dict[str, Dict[str, float]] = {}
        for name, ep in self.ep.items():
            count, duration = ep.count, ep.duration
            if ep.on and ts - ep.start >= ep.min_ms:
                count += 1
                duration += (ts - ep.start) / 1000.0
                events.append({"type": ep.type, "start": self._rel(ep.start), "duration": round((ts - ep.start) / 1000.0, 2)})
            counts[name] = {"count": count, "duration": duration}
        freeze_ms = self.freeze_ms
        if self.freeze_since is not None and ts - self.freeze_since >= FREEZE_MIN_MS:
            freeze_ms += ts - self.freeze_since

        intervals = [(b - a) / 1000.0 for a, b in zip(self.blink_times, self.blink_times[1:])]
        i_mean = _mean(intervals)
        i_std = float(statistics.pstdev(intervals)) if len(intervals) > 1 else 0.0

        timeline = list(self.timeline)
        c = self.sec
        if c and c["frames"]:
            ff = max(c["faceFrames"], 1)
            timeline.append({
                "t": c["t"], "blink": c["blinks"],
                "gaze_away": round(c["away"] / ff, 2),
                "self_touch": round(c["touch"] / c["frames"], 2),
                "hand_motion": round(c["handSpeed"] / c["handN"] if c["handN"] else 0.0, 3),
                "head_motion": round(c["headSpeed"] / c["headN"] / 60.0 if c["headN"] else 0.0, 3),
                "tension": round(c["tension"] / c["frames"], 2),
                "expression": round(c["expr"] / ff, 2),
            })
        events.sort(key=lambda e: e["start"])

        pf = self.pose_frames
        return {
            "available": self.frames > 0,
            "extended": True,
            "tracker": TRACKER_VERSION,
            "duration_sec": round(elapsed, 2),
            "frames_analyzed": self.frames,
            "fps": round(self.frames / elapsed, 1),
            "face_detected_ratio": round(self.face_frames / frames, 3),
            "hands_detected_ratio": round(self.hand_frames / frames, 3),
            "pose_detected_ratio": round(self.pose_frames / frames, 3),
            "blink_count": self.blink_count,
            "blink_rate_per_min": round(self.blink_count / minutes, 1),
            "blink_burst_count": self.blink_bursts,
            "blink_interval_cv": round(min(10.0, i_std / i_mean) if i_mean > 0 else 0.0, 3),
            "gaze_aversion_ratio": round(self.averted_frames / face_frames, 3),
            "gaze_shift_rate_per_min": round(self.gaze_shifts / minutes, 1),
            "eye_closure_ratio": round(self.closed_frames / face_frames, 3),
            "face_touch_count": int(counts["face_touch"]["count"]),
            "face_touch_duration_sec": round(counts["face_touch"]["duration"], 2),
            "hand_movement_energy": round(self.speed_sum / self.speed_frames if self.speed_frames else 0.0, 3),
            "hand_fidget_rate_per_min": round(self.fidget_bursts / minutes, 1),
            "hands_together_ratio": round(self.hands_together_frames / frames, 3),
            "hand_rub_count": int(counts["hand_rub"]["count"]),
            "hand_rub_duration_sec": round(counts["hand_rub"]["duration"], 2),
            "finger_clasp_ratio": round(self.clasp_frames / frames, 3),
            "arm_stroke_count": int(counts["arm_stroke"]["count"]),
            "arm_stroke_duration_sec": round(counts["arm_stroke"]["duration"], 2),
            "self_hug_ratio": round(self.self_hug_frames / frames, 3),
            "neck_touch_count": int(counts["neck_touch"]["count"]),
            "neck_touch_duration_sec": round(counts["neck_touch"]["duration"], 2),
            "hair_touch_count": int(counts["hair_touch"]["count"]),
            "lip_bite_ratio": round(self.lip_bite_frames / face_frames, 3),
            "swallow_count": self.swallow_count,
            "swallow_rate_per_min": round(self.swallow_count / minutes, 1),
            "shoulder_raise_ratio": round(self.shoulder_raise_frames / pf if pf else 0.0, 3),
            "shoulder_asymmetry": round(min(1.0, self.shoulder_asym_sum / pf) if pf else 0.0, 3),
            "jaw_clench_ratio": round(self.jaw_clench_frames / face_frames, 3),
            "freeze_ratio": round(min(1.0, freeze_ms / 1000.0 / elapsed), 3),
            "slouch_ratio": round(self.slouch_frames / pf if pf else 0.0, 3),
            "lean_away_ratio": round(self.lean_away_frames / pf if pf else 0.0, 3),
            "head_movement_energy": round(self.head_speed_sum / self.head_frames / 60.0 if self.head_frames else 0.0, 3),
            "head_shake_rate_per_min": round(self.head_shakes / minutes, 1),
            "posture_shift_count": self.posture_shifts,
            "head_down_ratio": round(self.head_down_frames / face_frames, 3),
            "expression": expression,
            "events": events[-400:],
            "timeline": timeline[-900:],
        }


# ---------------------------------------------------------------------
# MediaPipe plumbing
# ---------------------------------------------------------------------

def models_dir() -> Path:
    base = os.getenv("SAHAYAK_MEDIAPIPE_DIR")
    path = Path(base) if base else Path(__file__).resolve().parent.parent / "models_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_models() -> Dict[str, Path]:
    """Download the .task files once (needs internet the first time)."""
    out: Dict[str, Path] = {}
    for name, url in MODEL_URLS.items():
        target = models_dir() / name
        if not target.exists() or target.stat().st_size < 1000:
            urllib.request.urlretrieve(url, target)  # noqa: S310 - fixed, trusted URLs
        out[name] = target
    return out


_DETECTORS: Optional[Dict[str, Any]] = None


def _load_detectors() -> Dict[str, Any]:
    global _DETECTORS
    if _DETECTORS is not None:
        return _DETECTORS

    import mediapipe as mp
    from mediapipe.tasks import python as mp_python
    from mediapipe.tasks.python import vision

    paths = ensure_models()
    mode = vision.RunningMode.VIDEO

    face = vision.FaceLandmarker.create_from_options(
        vision.FaceLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(paths["face_landmarker.task"])),
            running_mode=mode,
            num_faces=1,
            output_face_blendshapes=True,
            output_facial_transformation_matrixes=True,
        )
    )
    hands = vision.HandLandmarker.create_from_options(
        vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=str(paths["hand_landmarker.task"])),
            running_mode=mode,
            num_hands=2,
        )
    )
    pose = None
    try:
        pose = vision.PoseLandmarker.create_from_options(
            vision.PoseLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(paths["pose_landmarker_lite.task"])),
                running_mode=mode,
                num_poses=1,
            )
        )
    except Exception:
        pose = None

    _DETECTORS = {"mp": mp, "face": face, "hands": hands, "pose": pose}
    return _DETECTORS


def video_analysis_available() -> bool:
    try:
        import cv2  # noqa: F401
        import mediapipe  # noqa: F401
    except Exception:
        return False
    return True


def analyze_video_file(video_path: str) -> Dict[str, Any]:
    """
    Run the body-language tracker over a video file and return the
    behaviour feature contract.  Frames are sampled at ~TARGET_FPS and
    processed in memory only.
    """
    try:
        import cv2
    except Exception as exc:
        return {"available": False, "error": f"opencv not installed: {exc}"}

    try:
        det = _load_detectors()
    except Exception as exc:
        return {"available": False, "error": f"MediaPipe unavailable: {exc}"}

    mp = det["mp"]
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return {"available": False, "error": "Could not open video."}

    src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    step = max(1, int(round(src_fps / TARGET_FPS)))
    agg = BehaviorAggregator()
    frame_index = 0
    last_ts = -1

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_index += 1
            if (frame_index - 1) % step:
                continue
            ts_ms = int((frame_index - 1) / src_fps * 1000.0)
            if ts_ms / 1000.0 > MAX_ANALYSIS_SEC:
                break
            if ts_ms <= last_ts:
                ts_ms = last_ts + 1
            last_ts = ts_ms

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)

            face_res = det["face"].detect_for_video(image, ts_ms)
            hand_res = det["hands"].detect_for_video(image, ts_ms)
            pose_res = det["pose"].detect_for_video(image, ts_ms) if det["pose"] else None

            face_lm = face_res.face_landmarks[0] if face_res.face_landmarks else None
            shapes = (
                {c.category_name: float(c.score) for c in face_res.face_blendshapes[0]}
                if face_res.face_blendshapes
                else None
            )
            matrix = (
                face_res.facial_transformation_matrixes[0]
                if face_res.facial_transformation_matrixes
                else None
            )
            hands = [list(h) for h in (hand_res.hand_landmarks or [])]
            pose_lm = pose_res.pose_landmarks[0] if pose_res and pose_res.pose_landmarks else None
            visibility = [float(getattr(p, "visibility", 1.0) or 0.0) for p in pose_lm] if pose_lm else None

            agg.process_frame(
                ts=float(ts_ms),
                face_landmarks=face_lm,
                blendshapes=shapes,
                matrix=matrix,
                hands=hands,
                pose=pose_lm,
                pose_visibility=visibility,
            )
    except Exception as exc:
        cap.release()
        return {"available": False, "error": f"Video analysis failed: {exc}"}

    cap.release()
    if agg.frames == 0:
        return {"available": False, "error": "No frames could be decoded."}
    result = agg.summary()
    result["source"] = "uploaded_video"
    return result


__all__ = ["BehaviorAggregator", "analyze_video_file", "video_analysis_available", "TRACKER_VERSION"]
