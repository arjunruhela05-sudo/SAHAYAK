# SAHAYAK Backend — Multilingual Semantic AI Engine v2

FastAPI backend for the SAHAYAK AI-assisted Stress, Trauma and Vulnerability Assessment & Triage prototype.

## AI engine v2

The text pipeline now uses a multilingual Sentence Transformer as the primary semantic detector when enabled, with a deterministic keyword layer retained as a development fallback.

- Semantic sentence-level signal detection
- English + Hindi + Hinglish routing/prototypes
- Contextual paraphrase detection rather than exact-phrase-only matching
- Signal-specific negation handling
- Evidence sentences returned for explainability
- Existing transparent SVI/risk scoring retained
- Human review remains mandatory

The default semantic model is `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Its model card describes 384-dimensional sentence embeddings and support for 50 languages. Sentence Transformers supports semantic textual similarity by comparing embeddings. This model is used here as a semantic similarity layer, not as a clinical or diagnostic model.

## Setup (Windows)

```powershell
python -m venv venv
venv\\Scripts\\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
uvicorn main:app --reload
```

On first semantic inference, the configured Hugging Face model may be downloaded and cached locally. Internet access is therefore required for the first model download unless the model has already been cached.

Server: `http://127.0.0.1:8000`
Swagger: `http://127.0.0.1:8000/docs`
Health: `http://127.0.0.1:8000/api/health`

## Configuration

`.env.example` contains:

```text
SAHAYAK_SEMANTIC_ENABLED=true
SAHAYAK_SEMANTIC_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
SAHAYAK_SEMANTIC_THRESHOLD=0.55
```

For emergency fallback/testing without the model:

```text
SAHAYAK_SEMANTIC_ENABLED=false
```

## Test

```powershell
pytest
```

## Important prototype limitation

Semantic similarity improves robustness to paraphrasing, but it is not a validated risk classifier. Thresholds and signal definitions must be evaluated on representative, consented, multilingual data before any real government deployment. The system must remain human-in-the-loop and must not be presented as a clinical diagnosis.

## AI Engine v2.2 safety calibration

v2.2 preserves the semantic scoring behavior for multilingual/Hinglish narratives while adding stronger contextual safety handling:

- Direct lethal threats in English, Hindi, and Hinglish receive a high-severity safety floor.
- Near-term lethal threats (for example, threats mentioning today/tomorrow/now) receive SVI 96 / CRITICAL.
- Direct lethal threats without an explicit near-term marker receive SVI 92 / CRITICAL.
- Threat negation is explicitly checked before applying the safety floor, including English and Hindi patterns.
- The immediate-threat severity now reports CRITICAL at scores >=90, keeping the API internally consistent with the overall risk level.
- Semantic signal scores remain independent; the system does not artificially reduce strong semantic scores for Hinglish threat narratives.

These are prototype engineering rules and require representative, consented multilingual validation before operational deployment.


## Multimodal engine v5 — voice nuance & body language

New services:

| Service | Purpose |
| --- | --- |
| `services/prosody_engine.py` | Pauses / hesitation timing, pitch (F0) mean, range, variability, jitter, shimmer, HNR (via Praat/parselmouth when installed), audible breathing events, 4–10 Hz voice tremor (amplitude + frequency), syllable rate, vocal depth (spectral weight). Produces a 0–100 indicator with sub-scores and cues. |
| `services/disfluency_engine.py` | "Fumbling" from the transcript: filler sounds (English, Hinglish, Devanagari), stutters and repetitions, restarts / self-corrections, hedging, trailing or broken sentences, hesitation gaps and low-confidence segments from Whisper timing. |
| `services/behavior_engine.py` + `models/behavior.py` | Validates and scores the body-language feature contract sent by the browser (blink rate, gaze aversion, face touches, fidgeting, head/posture, expression) with a capture-reliability estimate. |
| `services/multimodal_service.py` | Shared pipeline: text engine → supplementary engines → fusion → explanation → persistence. |
| `services/fusion_engine.py` | Text-primary fusion with capped voice (+10) and behaviour (+6) nudges, incongruence flag and confidence bonus. Backwards compatible with the v4 acoustic-only call. |

New endpoints:

- `POST /api/assess-video` — multipart: `file` (audio/webm or a video container; only the audio track is decoded), `case_id`, `consent`, `behavior` (JSON string of features), `language`.
- `POST /api/behavior-score` — JSON body of behaviour features → live indicator (no case created).

`POST /api/assess-audio` now also runs the prosody and disfluency engines.

Optional dependency: `praat-parselmouth` (in `requirements.txt`) gives Praat-grade jitter / shimmer / HNR. If it is missing the engine falls back to librosa-only estimates. `ffmpeg` must be on PATH for Whisper and for extracting audio from video uploads.

Raw audio and video are never persisted; cases store only the numeric feature summaries (`voice_analysis`, `behavior_analysis`) and the fusion breakdown (`modalities`).


## Multimodal engine v6 — context, tone, extended body language, participant privacy

| Service | Purpose |
| --- | --- |
| `services/context_engine.py` | Whole-passage reading: 2–3-sentence windows + passage embeddings against the signal prototypes, discourse features (escalation, fragmentation, rumination, immediacy, helplessness, absolutism, self-focus, hedged safety) → narrative stress index and a capped SVI nudge. |
| `services/tone_engine.py` | Vocal tone over the whole recording: arousal vs. the speaker's own baseline, flatness, strain, instability, trajectory; per-window timeline. Attached to `extract_prosody_features()` output as `tone`. |
| `services/video_behavior_engine.py` | Server-side port of the browser tracker for uploaded video files (MediaPipe Face / Hand / Pose + OpenCV). Same feature contract, including `events` / `timeline`. |
| `services/participant_view.py` | Receipt / status-only views for the assessed person. |

New / changed endpoints: `participant_view` on all assessment endpoints, `?view=participant` on case reads, `analyze_footage` on `/api/assess-video`, `GET /api/video-capabilities`.

Optional dependencies: `mediapipe`, `opencv-python-headless` (uploaded-video footage analysis). The `.task` models are downloaded into `backend/models_cache/` on first use (set `SAHAYAK_MEDIAPIPE_DIR` to reuse the frontend's `public/models` copy).

Tests: `pytest` (156 tests; the semantic model is not required — the context engine degrades to discourse-only and the tests use a fake encoder).
