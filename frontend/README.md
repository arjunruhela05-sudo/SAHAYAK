# SAHAYAK Frontend

React + Vite client for the SAHAYAK assessment platform.

```bash
npm install
cp .env.example .env
npm run dev
```

## Video step (body-language analysis)

Step 5 of the assessment wizard (`src/pages/Assessment.jsx`) mounts
`src/components/VideoRecorder.jsx`, which:

1. Opens the camera + microphone.
2. Loads MediaPipe **Face Landmarker** (with blend-shapes and head pose) and
   **Hand Landmarker** from `@mediapipe/tasks-vision`. The WASM runtime is
   bundled in `public/mediapipe/wasm`; the two `.task` models are fetched
   from Google's model storage on first use (or from `public/models` when
   `VITE_MEDIAPIPE_FACE_MODEL` / `VITE_MEDIAPIPE_HAND_MODEL` are set — see
   `public/models/README.md`).
3. Records only the audio track with `MediaRecorder`.
4. Runs `src/lib/behaviorAnalyzer.js` on every frame (~20 fps) to aggregate:
   blink rate, eye closure, gaze aversion / shifts, face touches, hand
   fidgeting, hands-together, head movement / shake / down, posture shifts
   and expression tension (brow, lips, frown, squint, jaw, smile).
5. Shows live indicators (polling `POST /api/behavior-score`).
6. Uploads the audio + the feature JSON to `POST /api/assess-video`.

The video frames never leave the browser.

`src/components/ModalityBreakdown.jsx` renders the fusion breakdown
(text / voice / body language) on the Result and Case Details pages.

## v6 additions

- **Extended tracker** (`src/lib/behaviorCore.js`, pure / unit-testable; `behaviorAnalyzer.js` adds MediaPipe
  loading incl. the optional **Pose Landmarker**): blink bursts & rhythm, neck / hair touching, self-soothing
  gestures (rubbing hands, clasping fingers, stroking arms, self-hug, lip biting), muscle tension (jaw clench,
  raised / uneven shoulders, slouch, lean-away, freeze), approximate swallowing, plus a timestamped
  **tracking pattern** (`events` + per-second `timeline`).
- **Video file upload** on the video step: the server extracts the audio and analyses the footage itself
  (`api.assessVideoFile`).
- **Participant mode**: when the signed-in role is `user`, the wizard sends `participant_view=true`; the recorder
  shows a plain camera view (no overlay, no counters, no indicator), the Result page shows a receipt, the
  dashboard (`UserDashboard.jsx`) lists submission status only and `CaseDetails` shows a status card. Nothing
  score-related is fetched by that role (`?view=participant`).
- **Responder view**: `NarrativeContextPanel.jsx` (whole-passage reading), the *Voice tone* channel with a
  timeline chart in `ModalityBreakdown.jsx`, and `TrackingPattern.jsx` (body-movement timeline).
- **Voice-guided mode** (`src/lib/voiceGuide.js`, `components/VoiceGuideBar.jsx`): spoken prompts
  ("Speak now", "Say 'I am done' when finished") and spoken commands in English / Hindi / Hinglish —
  *I consent · proceed · back · start · I am done · submit · record again · start dictation · voice · video ·
  help*. Uses the Web Speech API (Chrome / Edge). While recording, only stop phrases are honoured so the
  statement itself never triggers a command.

## Environment

```text
VITE_API_BASE_URL=http://127.0.0.1:8000
# optional, for offline demos:
# VITE_MEDIAPIPE_FACE_MODEL=/models/face_landmarker.task
# VITE_MEDIAPIPE_HAND_MODEL=/models/hand_landmarker.task
# VITE_MEDIAPIPE_WASM=/mediapipe/wasm
```
