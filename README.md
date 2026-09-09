# SAHAYAK

## AI-Assisted Stress, Trauma & Vulnerability Assessment and Triage

SAHAYAK is an AI-assisted stress, trauma, and vulnerability assessment platform designed to help identify and prioritize potentially vulnerable victim/complainant cases.

The system analyzes **textual narratives, voice recordings and (optionally) live video** to detect indicators such as fear, distress, intimidation, isolation, immediate threat, and self-harm risk. Beyond *what* is said, it measures *how* it is said — pauses, pitch, breathing, tremor, fumbling — and *how the person behaves* — blinking, eye contact, face touching, fidgeting, posture and facial tension. It generates a transparent **Stress & Vulnerability Index (SVI)**, assigns a risk level, highlights supporting evidence, and recommends appropriate human review.

> **SAHAYAK is a prototype decision-support system. It does not provide medical or psychological diagnoses and does not replace authorized human assessment.**

---

## Problem Statement

Victims and complainants may communicate critical information through their words, emotional state, and speech patterns.

During initial intake, it can be difficult to consistently identify:

- Severe fear or distress
- Immediate safety threats
- Intimidation or coercion
- Social isolation
- Self-harm or suicidal-ideation indicators
- Extreme vulnerability

Important signals may therefore be missed or cases may not be prioritized appropriately.

SAHAYAK addresses this challenge by providing an **AI-assisted first-level assessment and triage layer** that helps human reviewers identify potentially high-risk cases earlier.

---

# Our Solution

SAHAYAK combines multiple AI-assisted analysis techniques:

```text
Text / Voice / Video Input
        ↓
Speech Transcription (Whisper)
        ↓
NLP & Semantic Analysis            ── primary signal
        ↓
Vulnerability Signal Detection
        ↓
Voice nuance analysis              ── supplementary
  • prosody: pauses, pitch, jitter/shimmer, breathing,
             tremor, speech rate, voice depth
  • disfluency: fillers, repetitions, restarts,
             hedging, unfinished sentences, hesitation gaps
  • basic acoustics: energy, ZCR, pitch variability
        ↓
Body-language analysis (on-device) ── supplementary
  • blink rate, eye contact / gaze shifts
  • face touching, hand fidgeting, hand wringing
  • head movement, looking down, posture shifts
  • furrowed brow, pressed lips, frown, squint
        ↓
Multimodal Fusion (text primary, capped nudges,
                   incongruence flag)
        ↓
SVI Scoring
        ↓
Risk Classification
        ↓
Explainability + Evidence
        ↓
Recommendations
        ↓
Human Review

---

# Multimodal v5 — voice nuance + body language

| Layer | Where it runs | What it measures | Module |
| --- | --- | --- | --- |
| Text (primary) | backend | fear / threat / distress / isolation / intimidation / self-harm | `services/text_engine.py`, `semantic_engine.py` |
| Prosody | backend (librosa + Praat) | pauses & hesitations, pitch level/range/jitter, shimmer, breathing events, 4-10 Hz tremor, syllable rate, vocal depth | `services/prosody_engine.py` |
| Disfluency | backend | fillers (en / Hinglish / हिंदी), stutters & repetitions, restarts, hedging, trailing sentences, Whisper segment gaps | `services/disfluency_engine.py` |
| Behaviour | **browser** (MediaPipe) → numbers only to backend | blink rate, eye closure, gaze aversion & shifts, face touches, hand fidgeting, hands together, head movement / shake / down, posture shifts, expression tension | `frontend/src/lib/behaviorAnalyzer.js`, `services/behavior_engine.py` |
| Fusion | backend | text SVI + capped voice (≤ +10) and behaviour (≤ +6) nudges, total ≤ +14; incongruence flag when calm words meet distressed delivery | `services/fusion_engine.py`, `multimodal_service.py` |

Design guarantees:

- Text stays the primary signal. Voice and body language can only *raise* the SVI, never lower it, and only within declared caps.
- Every sub-score is exposed with human-readable cues (`modalities` in the API response) so a responder can see *why*.
- The video never leaves the device: MediaPipe Face/Hand Landmarkers run in the browser and only aggregated numbers (`behavior` JSON) are uploaded with the audio.
- Behaviour scores are scaled by capture reliability (short capture, face out of frame ⇒ down-weighted).
- Normalisation ranges are engineering ranges for a prototype, declared at the top of each engine for tuning on consented data. They are not clinical thresholds.

New endpoints: `POST /api/assess-video`, `POST /api/behavior-score` (see `API_CONTRACT.md`).

---

# Multimodal v6 — whole-context reading, voice tone, extended body language, participant privacy, voice guidance

| Upgrade | What changed | Module |
| --- | --- | --- |
| **Whole-passage context** | The narrative is no longer scored sentence by sentence only. 2–3-sentence windows and the passage as a whole are compared with the signal prototypes (a threat spread over "He came back. He had a knife. I locked the children in." is found), and *how* the story is told is measured: escalation, fragmentation, rumination, present-tense immediacy, helplessness, absolutist wording, self-focus, "I'm fine, but…". Produces a **narrative stress index** and a capped SVI nudge (≤ +6). | `services/context_engine.py`, `text_engine.py`, `scoring_engine.py` |
| **Voice tone over the whole recording** | 3-second windows relative to the speaker's own opening baseline: arousal (louder / higher / faster), flat / monotone delivery, strain (HNR, spectral noise), loudness & pace instability, phrases trailing off, fading, outbursts, and the arousal **trajectory** (steady / escalating / collapsing / volatile). Fourth voice channel next to prosody, disfluency and acoustics; a per-window timeline is stored for the responder chart. | `services/tone_engine.py`, `prosody_engine.py`, `fusion_engine.py` |
| **Extended body-language tracker (v6)** | Adds blink bursts & rhythm, neck / hair touching, **self-soothing gestures** (rubbing hands, clasping / interlacing fingers, stroking the arms, self-hug, lip biting), **muscle tension** (jaw clench, raised / uneven shoulders, slouch, lean-away, freeze), **swallowing** (approximate, from chin–nose micro-movement) and a timestamped **tracking pattern** (`events` + per-second `timeline`). Runs in the browser (Face + Hand + Pose Landmarkers) for live capture. | `frontend/src/lib/behaviorCore.js`, `behaviorAnalyzer.js`, `services/behavior_engine.py`, `models/behavior.py` |
| **Video file upload** | A recorded video can be uploaded: the audio track goes through the full voice pipeline and the **footage** is analysed on the server with the same tracker (MediaPipe Python + OpenCV, frames in memory only). | `services/video_behavior_engine.py`, `api/video.py` (`analyze_footage`), `GET /api/video-capabilities` |
| **Participant privacy** | The assessed person ("user" role) never sees the stress index, risk level, cues or tracking: the API returns a **receipt** (`participant_view=true`), `GET /api/cases?view=participant` is status-only, the recorder shows a plain camera view (no overlay, no counters) and the dashboard shows submission status only. Responders / admins keep the full view plus the new context, tone and tracking panels. | `services/participant_view.py`, `api/*`, `frontend/src/pages/{Assessment,Result,CaseDetails,UserDashboard}.jsx`, `components/VideoRecorder.jsx` |
| **Voice-guided mode** | Hands-free assessment: the app speaks each step ("Speak now", "Say 'I am done' when you have finished") and accepts spoken commands in English / Hindi / Hinglish — *I consent, proceed, back, start, I am done, submit, record again, start dictation, voice, video, help*. While a statement is being recorded only explicit stop phrases are honoured. Web Speech API (Chrome / Edge). | `frontend/src/lib/voiceGuide.js`, `components/VoiceGuideBar.jsx` |

Design guarantees are unchanged: text stays primary, supplementary channels only raise the SVI within declared caps, every number is explained with human-readable cues, raw audio / video is never stored, and human review is mandatory.
