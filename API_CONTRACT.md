# SAHAYAK API Contract

**Version:** 3.0 (multimodal v6)  
**Backend:** FastAPI  
**Frontend:** React + Vite  
**API Base URL:** `http://127.0.0.1:8000`

---

## 1. Overview

SAHAYAK is an AI-assisted Stress, Trauma and Vulnerability Assessment & Triage prototype.

The backend provides APIs for:

- Text-based assessment
- Voice/audio assessment (with prosody + disfluency analysis)
- Video assessment (voice + on-device body-language features)
- Live behaviour scoring
- Audio transcription
- Case management
- Case status management
- Case timeline
- Analytics
- Backend health monitoring

The frontend must consume only the endpoints and fields defined in this document.

---

# 2. Common Conventions

## Base URL

```text
http://127.0.0.1:8000

---

# 3. Multimodal endpoints (v2.0)

## `POST /api/assess-audio`  (extended)

Unchanged request. The response now additionally contains:

| Field | Type | Description |
| --- | --- | --- |
| `transcript` | string | Whisper transcript used for the text assessment |
| `modalities` | object | Fusion breakdown (see below) |
| `voice_analysis` | object | Raw feature summaries: `acoustic`, `prosody`, `disfluency` |
| `behavior_analysis` | object \| null | `null` for audio-only assessments |

## `POST /api/assess-video`

`multipart/form-data`

| Field | Type | Required | Notes |
| --- | --- | --- | --- |
| `file` | file | yes | `audio/webm`, `audio/wav`, `audio/mpeg`, `audio/mp4`, `audio/ogg` **or** a video container (`video/webm`, `video/mp4`, `video/quicktime`) — only the audio track is decoded, max 100 MB |
| `case_id` | string | yes | unique case id |
| `consent` | bool | yes | must be `true` |
| `behavior` | string (JSON) | no | behaviour feature object (below). Empty / `{}` ⇒ behaviour unavailable |
| `language` | string | no | default `auto` |

Response: `AssessmentResponse` (same shape as `/api/assess-audio`, with `behavior_analysis` populated).

Errors: `400` consent / validation / bad `behavior` JSON, `409` duplicate case, `422` no speech, `503` transcription unavailable.

## `POST /api/behavior-score`

JSON body = behaviour feature object. Returns the behaviour indicator without creating a case:

```json
{ "available": true, "indicator": 63.4, "raw_indicator": 63.4, "reliability": 1.0,
  "quality_notes": [], "sub_scores": { "blinking": 70, "gaze": 85, "face_touch": 40,
  "fidgeting": 55, "head_posture": 30, "expression": 62 }, "cues": ["Rapid blinking (38 blinks/min; …)"] }
```

## Behaviour feature object

All numbers are aggregated in the browser by `frontend/src/lib/behaviorAnalyzer.js`; every field is optional.

```json
{
  "available": true,
  "duration_sec": 42.3, "frames_analyzed": 830, "fps": 19.6,
  "face_detected_ratio": 0.97, "hands_detected_ratio": 0.62,
  "blink_count": 27, "blink_rate_per_min": 38.3, "eye_closure_ratio": 0.09,
  "gaze_aversion_ratio": 0.48, "gaze_shift_rate_per_min": 22,
  "face_touch_count": 3, "face_touch_duration_sec": 5.1,
  "hand_movement_energy": 0.31, "hand_fidget_rate_per_min": 11, "hands_together_ratio": 0.2,
  "head_movement_energy": 0.18, "head_shake_rate_per_min": 4, "posture_shift_count": 2, "head_down_ratio": 0.33,
  "expression": { "brow_furrow": 0.32, "brow_raise": 0.1, "lip_press": 0.22, "mouth_frown": 0.18,
                  "eye_squint": 0.12, "jaw_tension": 0.05, "smile": 0.02 }
}
```

## `modalities` object

```json
{
  "text_svi": 42.0, "fused_svi": 51.5, "fusion_method": "text_primary+voice+behavior",
  "voice_indicator": 68.0, "behavior_indicator": 74.0,
  "voice_adjustment": 3.9, "behavior_adjustment": 3.8,
  "acoustic":   { "available": true, "indicator": 41.0, "sub_scores": {...}, "cues": [] },
  "prosody":    { "available": true, "indicator": 66.0, "sub_scores": { "pauses": 80, "pitch": 55, "breathing": 70, "tremor": 60, "rate": 20, "depth": 45 }, "cues": ["Frequent long pauses …"] },
  "disfluency": { "available": true, "indicator": 58.0, "sub_scores": { "fillers": 60, "repetitions": 70, "restarts": 30, "hedging": 50, "fragments": 40, "timing": 65 }, "cues": ["Frequent filler sounds …"] },
  "behavior":   { "available": true, "indicator": 74.0, "reliability": 1.0, "sub_scores": { "blinking": 75, "gaze": 85, "face_touch": 60, "fidgeting": 70, "head_posture": 50, "expression": 65 }, "cues": ["Avoided eye contact for 48% of the recording."] },
  "incongruence_flag": false,
  "modalities_used": ["text", "voice", "behavior"]
}
```

Fusion rules: `fused_svi = text_svi + min(voice_adj + behavior_adj, 14)` where
`voice_adj = min(max(0, voice − text) × 0.15, 10)` and
`behavior_adj = min(max(0, behavior − text) × 0.12 × reliability, 6)`.
`incongruence_flag` is set when `text_svi ≤ 35` and voice or behaviour ≥ 60.

## Case record additions

`GET /api/cases/{id}` now includes `capture_mode` (`text` | `voice` | `video`), `modalities`, `voice_analysis` and `behavior_analysis`. Raw audio/video is never stored.


---

# 4. v3.0 additions (multimodal v6)

## Participant view (assessed person)

Every assessment endpoint accepts `participant_view` (`POST /api/assess` JSON field, `assess-audio` / `assess-video` form field).
When `true` the response is an **`AssessmentReceipt`** instead of the full assessment — no score, risk level, signal, cue or tracking data ever reaches the participant's device:

```json
{ "case_id": "SAH-2026-000123", "status": "RECEIVED", "capture_mode": "video", "language": "en",
  "human_review_required": true, "participant_view": true,
  "message": "Thank you. Your statement has been received and will be reviewed by an authorised responder.",
  "next_steps": ["An authorised responder will review your statement.", "..."] }
```

`GET /api/cases?view=participant` and `GET /api/cases/{id}?view=participant` return `ParticipantCaseSummary` objects
(`case_id`, `status`, `created_at`, `updated_at`, `capture_mode`, `human_review_required`, `message`). The case record itself is fully scored for responders.

## `narrative_context` (all assessments)

```json
{ "available": true, "engine": "context", "indicator": 58.0, "adjustment": 3.1,
  "sub_scores": { "escalation": 70, "fragmentation": 20, "rumination": 0, "immediacy": 60, "helplessness": 65, "absolutism": 30, "self_focus": 45 },
  "cues": ["The account becomes progressively more distressed towards the end.", "Language of helplessness / no way out."],
  "signals": { "immediate_threat": { "score": 80, "similarity": 0.71, "level": "window[1:4]", "evidence": "He came back last night. He had a knife. I locked the children in the bedroom." } },
  "discourse": { "sentence_count": 5, "word_count": 41, "trajectory": "escalating", "escalation_slope": 0.08, "fragmentation": 0.52, "rumination": 0.0, "immediacy_ratio": 0.4, "helplessness_count": 1, "absolutist_count": 2, "first_person_ratio": 0.2, "hedged_safety": true } }
```

`engine` is `context` when the sentence-transformer is available, `discourse_only` otherwise. The adjustment is `min(max(0, indicator − svi) × 0.10, 6)`.
Cases persist `narrative_context` and `transcript`.

## `modalities.tone` (voice / video)

Fourth voice channel (weights: acoustic 0.15, prosody 0.40, disfluency 0.25, tone 0.20):

```json
{ "available": true, "indicator": 47.0, "label": "escalating",
  "sub_scores": { "arousal": 80, "flatness": 10, "strain": 20, "instability": 35, "trajectory": 60 },
  "cues": ["The voice became louder and faster as the account went on (rising arousal)."] }
```

`voice_analysis.prosody.tone` holds the raw features including `timeline` — one entry per 3-second window
(`t`, `energy`, `pitch_st`, `rate`, `pause_ratio`, `arousal`) and `trajectory` (`steady | escalating | collapsing | volatile`).

## Behaviour feature object — v6 fields

All optional. `extended: true` marks captures from the v6 tracker; the new groups are weighted only when present, and hand-based groups only when `hands_detected_ratio ≥ 0.2`.

```json
{ "extended": true, "tracker": "browser-v6", "pose_detected_ratio": 0.9,
  "blink_burst_count": 3, "blink_interval_cv": 0.9,
  "hand_rub_count": 2, "hand_rub_duration_sec": 4.1, "finger_clasp_ratio": 0.3,
  "arm_stroke_count": 1, "arm_stroke_duration_sec": 1.2, "self_hug_ratio": 0.1,
  "neck_touch_count": 2, "neck_touch_duration_sec": 1.8, "hair_touch_count": 1, "lip_bite_ratio": 0.08,
  "swallow_count": 5, "swallow_rate_per_min": 7.5,
  "shoulder_raise_ratio": 0.3, "shoulder_asymmetry": 0.08, "jaw_clench_ratio": 0.25, "freeze_ratio": 0.2, "slouch_ratio": 0.1, "lean_away_ratio": 0.05,
  "events": [ { "type": "hand_rub", "start": 12.4, "duration": 2.1 }, { "type": "swallow", "start": 20.1, "duration": 0.4, "note": "approximate" } ],
  "timeline": [ { "t": 0, "blink": 1, "gaze_away": 0.2, "self_touch": 0.0, "hand_motion": 0.1, "head_motion": 0.05, "tension": 0.3, "expression": 0.2 } ] }
```

Event types: `face_touch, neck_touch, hair_touch, hand_rub, arm_stroke, finger_clasp, self_hug, jaw_clench, shoulder_raise, freeze, swallow, blink_burst, gaze_away, head_down, head_shake, posture_shift, fidget`.

Behaviour sub-scores are now `blinking, gaze, face_touch, self_soothing, fidgeting, head_posture, tension, swallowing, expression`; the result also carries `tracked_groups` and `event_count`.

## `POST /api/assess-video` — video files

`file` may be a video container. New form fields:

| Field | Values | Meaning |
| --- | --- | --- |
| `analyze_footage` | `auto` (default) / `always` / `never` | analyse the footage on the server; `auto` does so when no browser `behavior` cues were supplied |
| `participant_view` | bool | return a receipt |

Server-side footage analysis needs `mediapipe` + `opencv-python-headless`; `GET /api/video-capabilities` reports `server_footage_analysis`. Frames are processed in memory; the file is deleted after the request.
