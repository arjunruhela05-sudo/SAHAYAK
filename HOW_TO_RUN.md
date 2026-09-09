# SAHAYAK v6 — how to run it

Everything is driven by **one file: `SAHAYAK.bat`**. It sets the project up the first
time and simply starts it every time after that.

## What you need

| | |
|---|---|
| Windows 10 / 11 | |
| **Anaconda or Miniconda** | already on this PC (`C:\Users\<you>\anaconda3`). It provides Python 3.11, ffmpeg and Node 22 inside an environment called `sahayak`, so nothing else has to be installed by hand. |
| **Chrome or Edge** | needed for the camera step and for voice-guided mode (they use the browser's speech engine and MediaPipe WebAssembly). |
| Internet — first run only | ~2 GB of Python packages (PyTorch, Whisper, MediaPipe…), the Node packages, then on first use the multilingual NLP model (~500 MB) and the three MediaPipe models (~17 MB). Afterwards it runs offline. |
| Microphone + webcam | for the voice / video steps. |

## First run

1. Put these in one folder (e.g. `Desktop\SAHAYAK`):
   `SAHAYAK.bat`, `SAHAYAK-multimodal-v6.zip` (or the already-extracted `SAHAYAK-main` folder), `HOW_TO_RUN.md`.
2. **Double-click `SAHAYAK.bat`.** It will
   - extract the zip (keeping any existing `cases.json`),
   - create the `sahayak` conda environment,
   - install the Python and frontend packages (10–20 minutes the first time),
   - open two server windows — **SAHAYAK backend** and **SAHAYAK frontend** — and then your browser at <http://localhost:5173>.
3. If Windows asks about network access for Python or Node, allow it (it only listens on your own machine).

The window that ran `SAHAYAK.bat` shows the sign-in details and can be closed. **Keep the two server windows open** while you use the app.

## Every run after that

Double-click `SAHAYAK.bat` again. Packages are only re-installed when `requirements.txt` or `package.json` changed, so it starts in a few seconds (the backend needs ~20–40 s to load Whisper the first time you record).

Other commands (open a terminal in the folder, or make a shortcut):

| Command | What it does |
|---|---|
| `SAHAYAK.bat` | set up if needed, then start |
| `SAHAYAK.bat stop` | close both server windows / free ports 8000 and 5173 |
| `SAHAYAK.bat test` | run the backend test-suite (156 tests) |
| `SAHAYAK.bat setup` | force a re-install of all packages |

## Signing in — two very different views

| Role | Sign in | What they see |
|---|---|---|
| **Authority / responder** | `authority@sahayak.local` / `Authority@123` | full result: SVI, risk, signals, whole-passage context, voice tone timeline, body-language tracking pattern, cues, recommendations, priority queue, analytics |
| **Admin** | `admin@sahayak.local` / `Admin@123` | same as authority plus administration |
| **User (the person being assessed)** | click **Create account**, choose *User* | consent → statement (type / dictate / voice / video) → **only a receipt**. No score, risk, cue, overlay or tracking is ever shown — the API itself returns a receipt for this role. Their dashboard shows submission status only. |

## Trying each new feature

**Whole-passage context** — sign in as authority, *New Assessment*, paste a narrative where the danger is spread across sentences, e.g. *"He came back last night. He had a knife. I locked the children in the bedroom and did not sleep. There is nothing I can do. I'm fine, but he will come again tonight."* The result page shows **"How the account reads as a whole"**: narrative stress index, trajectory, cues (helplessness, "I'm fine, but…", present-tense danger) and the sentences that were only caught by reading them together.

**Voice tone, pauses, breathing, pace, fumbling** — step 4 *Voice*, record 30+ seconds. The result shows the **Voice tone** channel (arousal vs. your own opening baseline, flatness, strain, instability, trajectory) with a timeline chart, plus prosody (pauses, breathing, pitch, jitter, tremor, rate) and speech-pattern (fillers, restarts) channels.

**Video, live** — step 5 *Video*. As authority you see the tracking overlay, live counters (blinks, eye contact, self-soothing, tension, swallowing…) and the live non-verbal indicator; the result adds the **Body-movement timeline**. As a *User* the same tracking runs silently — only a plain camera view is shown.

**Video, uploaded file** — on step 5 use *"Or upload a recorded video"*. The server extracts the audio (full voice pipeline) and analyses the footage with the same tracker. The first upload downloads the MediaPipe models (needs internet once).

**Voice-guided mode** — toggle **Voice-guided mode** at the top of the assessment (Chrome/Edge; allow the microphone). The app reads each step aloud and listens:

| Say… | English | Hindi / Hinglish |
|---|---|---|
| consent | "I consent" | "मैं सहमत हूँ" / "main sehmat hoon" |
| move | "proceed" / "next" · "back" | "आगे बढ़ो" · "वापस" |
| choose input | "text" · "voice" · "video" | |
| record | "start" → app says **"Speak now"** … "I am done" / "stop recording" | "शुरू करो" … "हो गया" / "बस" |
| send | "submit" · "record again" | "भेज दो" · "दोबारा" |
| dictate the narrative | "start dictation" … "stop dictation" | "बोलकर लिखो" … "लिखना बंद करो" |
| other | "repeat" · "help" · "stop voice mode" | "दोबारा बोलो" · "मदद" |

While you are recording a statement only the stop phrases are accepted, so nothing you say in the statement can trigger a command. Switch the language with the drop-down next to the toggle.

## If something goes wrong

| Symptom | Fix |
|---|---|
| "Anaconda / Miniconda was not found" | install Miniconda (link is printed), then run `SAHAYAK.bat` again |
| Package install fails on `mediapipe` / `opencv` | the launcher retries without them automatically; everything works except server-side analysis of *uploaded video files* (live camera tracking still works). |
| Backend window shows an error about the NLP model / no internet | first run needs internet for the model download. Offline fallback: set `SAHAYAK_SEMANTIC_ENABLED=false` in `SAHAYAK-main\backend\.env` — keyword + discourse analysis still run. |
| "port 5173 / 8000 already in use" | run `SAHAYAK.bat stop`, then `SAHAYAK.bat` |
| Camera / microphone not working | use Chrome or Edge on `http://localhost:5173` (not the 127.0.0.1 address), allow the permission prompt, close other apps using the camera |
| Voice-guided toggle is greyed out | the browser has no speech engine — use Chrome or Edge |
| Video step says models could not be loaded | first use downloads them from Google; check internet, or drop the `.task` files into `SAHAYAK-main\frontend\public\models` (see the README there) |
| Everything is slow on first recording | Whisper loads on the first request (20–40 s); later requests are fast |
| Want a clean re-install | delete `SAHAYAK-main\backend\.deps_installed` and `SAHAYAK-main\frontend\.deps_installed`, or run `SAHAYAK.bat setup` |

Logs: `sahayak.log` next to the launcher, plus the two server windows. API documentation: <http://127.0.0.1:8000/docs>.

## Where things live

```
SAHAYAK\
├─ SAHAYAK.bat                 ← the only file you run
├─ HOW_TO_RUN.md               ← this guide
├─ SAHAYAK-multimodal-v6.zip   ← project archive (extracted on first run)
├─ sahayak.log
└─ SAHAYAK-main\
   ├─ backend\    FastAPI + engines (services\context_engine.py, tone_engine.py,
   │              prosody_engine.py, disfluency_engine.py, behavior_engine.py,
   │              video_behavior_engine.py, fusion_engine.py …), tests\, data\cases.json
   └─ frontend\   React + Vite (src\lib\behaviorCore.js tracker, src\lib\voiceGuide.js,
                  pages\Assessment.jsx, Result.jsx, UserDashboard.jsx …)
```

SAHAYAK is a decision-support prototype: every result is marked *human review required* and thresholds are engineering values to be tuned on consented data before any real deployment.
