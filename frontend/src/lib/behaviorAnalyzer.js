/**
 * Behaviour analyser (v6 — extended tracker)
 * ==========================================
 *
 * Runs MediaPipe Face Landmarker + Hand Landmarker + Pose Landmarker on a
 * live <video> element and aggregates *numbers only* — the video frames
 * never leave the browser.  The aggregate matches backend/models/behavior.py.
 *
 * Cues tracked
 * ------------
 *  - blink rate, blink bursts, irregular blink rhythm, eye closure
 *  - gaze aversion & gaze shifting              (eye-look blend-shapes + head yaw/pitch)
 *  - face / neck / hair touching                (hand landmarks vs. face regions)
 *  - self-soothing: rubbing hands, clasping / interlacing fingers,
 *    stroking the arms, self-hugging, lip biting
 *  - hand fidgeting / hands wringing            (wrist velocity, wrist distance)
 *  - muscle tension: jaw clench, raised / uneven shoulders,
 *    slouching, leaning away, freezing (rigid stillness)
 *  - swallowing / throat movements              (approximate: chin-nose distance dips)
 *  - head movement / shaking / down, posture shifts
 *  - expression tension                         (brow / lip / frown / squint / jaw)
 *
 * Besides the aggregate it keeps a *tracking pattern*: a timestamped list
 * of movement episodes (`events`) and per-second cue intensities
 * (`timeline`).  These are meant for the responder view only — the
 * recorder component never shows them to the person being recorded.
 */

import { FilesetResolver, FaceLandmarker, HandLandmarker, PoseLandmarker, DrawingUtils } from "@mediapipe/tasks-vision";
import { createBehaviorAnalyzer, TRACKER_VERSION } from "./behaviorCore";

export { createBehaviorAnalyzer, TRACKER_VERSION };

const WASM_BASE = import.meta.env.VITE_MEDIAPIPE_WASM || "/mediapipe/wasm";
const FACE_MODEL =
  import.meta.env.VITE_MEDIAPIPE_FACE_MODEL ||
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";
const HAND_MODEL =
  import.meta.env.VITE_MEDIAPIPE_HAND_MODEL ||
  "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task";
const POSE_MODEL =
  import.meta.env.VITE_MEDIAPIPE_POSE_MODEL ||
  "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task";

let modelsPromise = null;

/** Load (once) the WASM runtime and the three landmarkers. */
export async function loadModels(onProgress) {
  if (!modelsPromise) {
    modelsPromise = (async () => {
      onProgress?.("Loading vision runtime…");
      const vision = await FilesetResolver.forVisionTasks(WASM_BASE);
      onProgress?.("Loading face model…");
      const face = await FaceLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: FACE_MODEL, delegate: "GPU" },
        runningMode: "VIDEO",
        numFaces: 1,
        outputFaceBlendshapes: true,
        outputFacialTransformationMatrixes: true,
      });
      onProgress?.("Loading hand model…");
      const hands = await HandLandmarker.createFromOptions(vision, {
        baseOptions: { modelAssetPath: HAND_MODEL, delegate: "GPU" },
        runningMode: "VIDEO",
        numHands: 2,
      });
      let pose = null;
      try {
        onProgress?.("Loading posture model…");
        pose = await PoseLandmarker.createFromOptions(vision, {
          baseOptions: { modelAssetPath: POSE_MODEL, delegate: "GPU" },
          runningMode: "VIDEO",
          numPoses: 1,
        });
      } catch (err) {
        // Posture cues are optional; face + hands still work without them.
        console.warn("Pose model unavailable", err);
      }
      onProgress?.("Ready");
      return { face, hands, pose };
    })().catch((err) => {
      modelsPromise = null;
      throw err;
    });
  }
  return modelsPromise;
}

/* ------------------------------------------------------------------ */
/* overlay drawing (responder / debugging view only)                   */
/* ------------------------------------------------------------------ */

export function drawOverlay(canvas, video, faceResult, handResult, poseResult, live) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  if (canvas.width !== video.videoWidth || canvas.height !== video.videoHeight) {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
  }
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const utils = new DrawingUtils(ctx);

  const faceColor = live?.averted ? "#f79009" : live?.tense ? "#d92d20" : "#12b76a";
  for (const lm of faceResult?.faceLandmarks || []) {
    utils.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_FACE_OVAL, { color: faceColor, lineWidth: 1.5 });
    utils.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_LEFT_EYE, { color: "#5ed4cf", lineWidth: 1 });
    utils.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_RIGHT_EYE, { color: "#5ed4cf", lineWidth: 1 });
    utils.drawConnectors(lm, FaceLandmarker.FACE_LANDMARKS_LIPS, { color: "#5ed4cf", lineWidth: 1 });
  }
  for (const lm of poseResult?.landmarks || []) {
    utils.drawConnectors(lm, PoseLandmarker.POSE_CONNECTIONS, { color: "rgba(255,255,255,.45)", lineWidth: 1.5 });
  }
  const handColor = live?.touching ? "#d92d20" : "#ffffff";
  for (const lm of handResult?.landmarks || []) {
    utils.drawConnectors(lm, HandLandmarker.HAND_CONNECTIONS, { color: handColor, lineWidth: 2 });
    utils.drawLandmarks(lm, { color: handColor, radius: 2 });
  }
  if (live?.flags?.length) {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.font = "bold 13px system-ui, sans-serif";
    ctx.fillStyle = "rgba(11,22,34,.75)";
    const text = live.flags.map((f) => f.replace(/_/g, " ")).join("  ·  ");
    const w = ctx.measureText(text).width + 16;
    ctx.fillRect(canvas.width - w - 10, canvas.height - 34, w, 24);
    ctx.fillStyle = "#fff";
    ctx.fillText(text, canvas.width - w - 2, canvas.height - 17);
    ctx.restore();
  }
}
