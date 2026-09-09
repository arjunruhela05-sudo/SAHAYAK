# MediaPipe landmark models

The video step loads three MediaPipe Tasks models in the browser:

| Model | Default URL |
| --- | --- |
| Face Landmarker | https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task |
| Hand Landmarker | https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task |
| Pose Landmarker (lite) | https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task |

By default they are fetched from Google's model storage the first time the
video step opens (~17 MB total, cached by the browser afterwards).  The pose
model is optional — shoulder / posture / arm cues are skipped without it.

For a fully offline demo, download the files into this folder and set in
`frontend/.env`:

    VITE_MEDIAPIPE_FACE_MODEL=/models/face_landmarker.task
    VITE_MEDIAPIPE_HAND_MODEL=/models/hand_landmarker.task
    VITE_MEDIAPIPE_POSE_MODEL=/models/pose_landmarker_lite.task

The backend uses the same three files for uploaded video files; copy them
into `backend/models_cache/` (or point `SAHAYAK_MEDIAPIPE_DIR` at this
folder) to avoid a second download.

The WebAssembly runtime is already bundled under `public/mediapipe/wasm`.
