/**
 * Behaviour analyser core (pure, no MediaPipe import)
 * ====================================================
 *
 * Frame-by-frame aggregation of body-language cues into the backend
 * feature contract (backend/models/behavior.py) plus the responder-side
 * tracking pattern (`events`, `timeline`).  Kept free of browser / WASM
 * dependencies so it can be unit-tested in Node.  See behaviorAnalyzer.js
 * for model loading and overlay drawing.
 */

export const TRACKER_VERSION = "browser-v6";

// Thresholds (tuned for MediaPipe blend-shape scales, 0..1, and
// normalised image coordinates).  Engineering values for a prototype.
const BLINK_ON = 0.5;
const BLINK_OFF = 0.3;
const BLINK_BURST_WINDOW_MS = 2000;
const BLINK_BURST_MIN = 3;
const GAZE_H_AVERT = 0.45;
const GAZE_DOWN_AVERT = 0.5;
const HEAD_YAW_AVERT_DEG = 22;
const HEAD_PITCH_AVERT_DEG = 20;
const HEAD_DOWN_DEG = -12;
const HEAD_SHAKE_SWING_DEG = 6;
const FACE_TOUCH_MARGIN = 0.12;
const FIDGET_SPEED = 0.6;          // normalised frame-widths per second
const HANDS_TOGETHER_DIST = 0.13;
const POSTURE_SHIFT_DIST = 0.08;
const CLASP_DIST = 0.045;
const RUB_REL_SPEED = 0.25;
const RUB_MIN_REVERSALS = 2;
const RUB_WINDOW_MS = 1500;
const ARM_STROKE_DIST = 0.07;
const ARM_STROKE_SPEED = 0.15;
const JAW_CLENCH_PRESS = 0.35;
const LIP_BITE = 0.35;
const SWALLOW_DEV = 0.012;
const SWALLOW_MIN_MS = 200;
const SWALLOW_MAX_MS = 900;
const SWALLOW_REFRACTORY_MS = 1200;
const FREEZE_WINDOW_MS = 1000;     // stillness judged over the last second (noise tolerant)
const FREEZE_HEAD_RANGE_DEG = 2.5;
const FREEZE_HAND_RANGE = 0.02;
const FREEZE_MIN_MS = 3000;
const EPISODE_MIN_MS = { gaze_away: 1000, head_down: 1500, jaw_clench: 1000, shoulder_raise: 1500, finger_clasp: 1500, self_hug: 1500 };

const FINGERTIPS = [4, 8, 12, 16, 20, 0, 9];
const TIPS = [8, 12, 16, 20];
const MCPS = [5, 9, 13, 17];

/* ------------------------------------------------------------------ */
/* helpers                                                             */
/* ------------------------------------------------------------------ */

const blend = (shapes, name) => shapes?.find((c) => c.categoryName === name)?.score ?? 0;
const deg = (rad) => (rad * 180) / Math.PI;
const dist = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);
const mean = (arr) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : 0);
const median = (arr) => {
  if (!arr.length) return 0;
  const s = [...arr].sort((a, b) => a - b);
  const m = s.length >> 1;
  return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2;
};

/** Yaw / pitch (degrees) from a 4x4 column-major transformation matrix. */
function headPose(matrixData) {
  if (!matrixData || matrixData.length < 16) return null;
  const m = matrixData;
  const fx = m[8];
  const fy = m[9];
  const fz = m[10];
  const yaw = deg(Math.atan2(fx, fz));
  const pitch = deg(Math.asin(Math.max(-1, Math.min(1, fy))));
  return { yaw, pitch };
}

function faceBox(landmarks) {
  let minX = 1, minY = 1, maxX = 0, maxY = 0;
  for (const p of landmarks) {
    if (p.x < minX) minX = p.x;
    if (p.y < minY) minY = p.y;
    if (p.x > maxX) maxX = p.x;
    if (p.y > maxY) maxY = p.y;
  }
  return { minX, minY, maxX, maxY, cx: (minX + maxX) / 2, cy: (minY + maxY) / 2, w: maxX - minX, h: maxY - minY };
}

/** Distance from point p to segment ab. */
function segDist(p, a, b) {
  const abx = b.x - a.x, aby = b.y - a.y;
  const len2 = abx * abx + aby * aby || 1e-9;
  let t = ((p.x - a.x) * abx + (p.y - a.y) * aby) / len2;
  t = Math.max(0, Math.min(1, t));
  return Math.hypot(p.x - (a.x + t * abx), p.y - (a.y + t * aby));
}

/* ------------------------------------------------------------------ */
/* episode tracker                                                     */
/* ------------------------------------------------------------------ */

/**
 * Turns a per-frame boolean into timed episodes.  `minMs` filters out
 * flickers; episodes are pushed to `events` with their duration.
 */
function makeEpisode(type, minMs = 150) {
  return { type, minMs, on: false, start: 0, count: 0, duration: 0 };
}

function updateEpisode(ep, active, ts, events, origin) {
  if (active && !ep.on) {
    ep.on = true;
    ep.start = ts;
  } else if (!active && ep.on) {
    ep.on = false;
    const dur = ts - ep.start;
    if (dur >= ep.minMs) {
      ep.count += 1;
      ep.duration += dur / 1000;
      events.push({ type: ep.type, start: +((ep.start - origin) / 1000).toFixed(2), duration: +(dur / 1000).toFixed(2) });
    }
  }
}

/* ------------------------------------------------------------------ */
/* analyser                                                            */
/* ------------------------------------------------------------------ */

function initialState() {
  return {
    startTs: 0,
    lastTs: 0,
    frames: 0,
    faceFrames: 0,
    handFrames: 0,
    poseFrames: 0,
    events: [],
    timeline: [],
    // per-second accumulator
    sec: null,
    // eyes
    blinkCount: 0,
    blinkOn: false,
    closedFrames: 0,
    blinkTimes: [],
    blinkBursts: 0,
    lastBurstTs: -1e9,
    // gaze
    avertedFrames: 0,
    gazeShifts: 0,
    lastGazeBucket: null,
    // hands
    prevHands: null,
    speedSum: 0,
    speedFrames: 0,
    fidgetBursts: 0,
    lastFidgetTs: -1e9,
    fidgetOn: false,
    handsTogetherFrames: 0,
    claspFrames: 0,
    rubRel: null,
    rubReversals: [],
    rubLastSign: 0,
    lipBiteFrames: 0,
    // pose
    shoulderBase: null,
    shoulderSamples: [],
    torsoBase: null,
    torsoSamples: [],
    widthBase: null,
    widthSamples: [],
    shoulderRaiseFrames: 0,
    shoulderAsymSum: 0,
    slouchFrames: 0,
    leanAwayFrames: 0,
    selfHugFrames: 0,
    // head
    prevPose: null,
    headSpeedSum: 0,
    headFrames: 0,
    headDownFrames: 0,
    yawVelSign: 0,
    yawSwingStart: null,
    headShakes: 0,
    lastShakeTs: -1e9,
    // posture shift
    postureAnchor: null,
    postureShifts: 0,
    lastPostureTs: -1e9,
    // tension / freeze
    jawClenchFrames: 0,
    freezeSince: null,
    freezeMs: 0,
    motionBuf: [],
    // swallow
    throatBuf: [],
    swallowOn: false,
    swallowStart: 0,
    swallowCount: 0,
    lastSwallowTs: -1e9,
    // expression sums
    expr: { brow_furrow: 0, brow_raise: 0, lip_press: 0, mouth_frown: 0, eye_squint: 0, jaw_tension: 0, smile: 0 },
    // episodes
    ep: {
      face_touch: makeEpisode("face_touch", 150),
      neck_touch: makeEpisode("neck_touch", 150),
      hair_touch: makeEpisode("hair_touch", 150),
      hand_rub: makeEpisode("hand_rub", 400),
      arm_stroke: makeEpisode("arm_stroke", 400),
      finger_clasp: makeEpisode("finger_clasp", EPISODE_MIN_MS.finger_clasp),
      self_hug: makeEpisode("self_hug", EPISODE_MIN_MS.self_hug),
      gaze_away: makeEpisode("gaze_away", EPISODE_MIN_MS.gaze_away),
      head_down: makeEpisode("head_down", EPISODE_MIN_MS.head_down),
      jaw_clench: makeEpisode("jaw_clench", EPISODE_MIN_MS.jaw_clench),
      shoulder_raise: makeEpisode("shoulder_raise", EPISODE_MIN_MS.shoulder_raise),
      freeze: makeEpisode("freeze", FREEZE_MIN_MS),
    },
    // live
    lastFace: null,
    lastHands: null,
    lastPose: null,
  };
}

function newSecond(t) {
  return { t, frames: 0, faceFrames: 0, blinks: 0, away: 0, touch: 0, handSpeed: 0, handN: 0, headSpeed: 0, headN: 0, tension: 0, expr: 0 };
}

export function createBehaviorAnalyzer() {
  const s = initialState();

  function reset() {
    Object.assign(s, initialState());
  }

  function flushSecond() {
    const c = s.sec;
    if (!c || !c.frames) return;
    const ff = Math.max(c.faceFrames, 1);
    s.timeline.push({
      t: c.t,
      blink: c.blinks,
      gaze_away: +(c.away / ff).toFixed(2),
      self_touch: +(c.touch / c.frames).toFixed(2),
      hand_motion: +(c.handN ? c.handSpeed / c.handN : 0).toFixed(3),
      head_motion: +(c.headN ? c.headSpeed / c.headN / 60 : 0).toFixed(3),
      tension: +(c.tension / c.frames).toFixed(2),
      expression: +(c.expr / ff).toFixed(2),
    });
  }

  /**
   * Process one frame.  `ts` is performance.now() style milliseconds.
   * Returns a small live snapshot (for the responder overlay) or null.
   */
  function processFrame(faceResult, handResult, poseResult, ts) {
    if (!s.startTs) s.startTs = ts;
    const dt = s.lastTs ? (ts - s.lastTs) / 1000 : 0;
    s.lastTs = ts;
    s.frames += 1;

    const secIdx = Math.floor((ts - s.startTs) / 1000);
    if (!s.sec || s.sec.t !== secIdx) {
      flushSecond();
      s.sec = newSecond(secIdx);
    }
    const sec = s.sec;
    sec.frames += 1;

    const landmarks = faceResult?.faceLandmarks?.[0];
    const shapes = faceResult?.faceBlendshapes?.[0]?.categories;
    const matrix = faceResult?.facialTransformationMatrixes?.[0]?.data;
    const poseLm = poseResult?.landmarks?.[0];

    let box = null;
    let pose = null;
    let averted = false;
    let headSpeed = 0;
    let jawClench = false;
    let mouthOpen = 0;
    const flags = [];

    if (landmarks && shapes) {
      s.faceFrames += 1;
      sec.faceFrames += 1;
      box = faceBox(landmarks);
      pose = headPose(matrix);

      // ---- blinking --------------------------------------------------
      const blinkScore = (blend(shapes, "eyeBlinkLeft") + blend(shapes, "eyeBlinkRight")) / 2;
      if (!s.blinkOn && blinkScore > BLINK_ON) {
        s.blinkOn = true;
        s.blinkCount += 1;
        sec.blinks += 1;
        s.blinkTimes.push(ts);
        const recent = s.blinkTimes.filter((t) => ts - t <= BLINK_BURST_WINDOW_MS);
        if (recent.length >= BLINK_BURST_MIN && ts - s.lastBurstTs > BLINK_BURST_WINDOW_MS) {
          s.blinkBursts += 1;
          s.lastBurstTs = ts;
          s.events.push({ type: "blink_burst", start: +((recent[0] - s.startTs) / 1000).toFixed(2), duration: +((ts - recent[0]) / 1000).toFixed(2), intensity: recent.length });
        }
      } else if (s.blinkOn && blinkScore < BLINK_OFF) {
        s.blinkOn = false;
      }
      if (blinkScore > BLINK_ON) s.closedFrames += 1;

      // ---- gaze ------------------------------------------------------
      const lookLeft = (blend(shapes, "eyeLookOutLeft") + blend(shapes, "eyeLookInRight")) / 2;
      const lookRight = (blend(shapes, "eyeLookInLeft") + blend(shapes, "eyeLookOutRight")) / 2;
      const lookDown = (blend(shapes, "eyeLookDownLeft") + blend(shapes, "eyeLookDownRight")) / 2;
      const lookUp = (blend(shapes, "eyeLookUpLeft") + blend(shapes, "eyeLookUpRight")) / 2;
      const gazeH = lookLeft - lookRight;
      const gazeV = lookUp - lookDown;

      averted =
        Math.abs(gazeH) > GAZE_H_AVERT ||
        lookDown > GAZE_DOWN_AVERT ||
        (pose && (Math.abs(pose.yaw) > HEAD_YAW_AVERT_DEG || Math.abs(pose.pitch) > HEAD_PITCH_AVERT_DEG));
      if (averted) {
        s.avertedFrames += 1;
        sec.away += 1;
      }
      updateEpisode(s.ep.gaze_away, averted, ts, s.events, s.startTs);

      const bucket = `${gazeH > 0.3 ? "L" : gazeH < -0.3 ? "R" : "C"}${gazeV > 0.3 ? "U" : gazeV < -0.3 ? "D" : "C"}`;
      if (s.lastGazeBucket && bucket !== s.lastGazeBucket) s.gazeShifts += 1;
      s.lastGazeBucket = bucket;

      // ---- head pose -------------------------------------------------
      let headDown = false;
      if (pose) {
        headDown = pose.pitch < HEAD_DOWN_DEG || lookDown > 0.6;
        if (headDown) s.headDownFrames += 1;
        if (s.prevPose && dt > 0) {
          const dyaw = pose.yaw - s.prevPose.yaw;
          const dpitch = pose.pitch - s.prevPose.pitch;
          headSpeed = Math.hypot(dyaw, dpitch) / dt; // deg / s
          s.headSpeedSum += headSpeed;
          s.headFrames += 1;
          sec.headSpeed += headSpeed;
          sec.headN += 1;

          const sign = Math.sign(dyaw);
          if (sign !== 0) {
            if (s.yawSwingStart === null) s.yawSwingStart = s.prevPose.yaw;
            if (s.yawVelSign !== 0 && sign !== s.yawVelSign) {
              const swing = Math.abs(s.prevPose.yaw - s.yawSwingStart);
              if (swing >= HEAD_SHAKE_SWING_DEG && ts - s.lastShakeTs > 250) {
                s.headShakes += 1;
                s.lastShakeTs = ts;
                s.events.push({ type: "head_shake", start: +((ts - s.startTs) / 1000).toFixed(2), duration: 0.3, intensity: +swing.toFixed(1) });
              }
              s.yawSwingStart = s.prevPose.yaw;
            }
            s.yawVelSign = sign;
          }
        }
        s.prevPose = pose;
      }
      updateEpisode(s.ep.head_down, headDown, ts, s.events, s.startTs);

      // ---- posture shift ---------------------------------------------
      if (!s.postureAnchor) s.postureAnchor = { x: box.cx, y: box.cy };
      const moved = Math.hypot(box.cx - s.postureAnchor.x, box.cy - s.postureAnchor.y);
      if (moved > POSTURE_SHIFT_DIST) {
        if (ts - s.lastPostureTs > 1500) {
          s.postureShifts += 1;
          s.lastPostureTs = ts;
          s.events.push({ type: "posture_shift", start: +((ts - s.startTs) / 1000).toFixed(2), duration: 0.5, intensity: +moved.toFixed(3) });
        }
        s.postureAnchor = { x: box.cx, y: box.cy };
      }

      // ---- expression -----------------------------------------------
      const browFurrow = (blend(shapes, "browDownLeft") + blend(shapes, "browDownRight")) / 2;
      const lipPress = (blend(shapes, "mouthPressLeft") + blend(shapes, "mouthPressRight")) / 2;
      const frown = (blend(shapes, "mouthFrownLeft") + blend(shapes, "mouthFrownRight")) / 2;
      const squint = (blend(shapes, "eyeSquintLeft") + blend(shapes, "eyeSquintRight")) / 2;
      const jawForward = blend(shapes, "jawForward");
      const cheekSquint = (blend(shapes, "cheekSquintLeft") + blend(shapes, "cheekSquintRight")) / 2;
      mouthOpen = blend(shapes, "jawOpen");
      s.expr.brow_furrow += browFurrow;
      s.expr.brow_raise += blend(shapes, "browInnerUp");
      s.expr.lip_press += lipPress;
      s.expr.mouth_frown += frown;
      s.expr.eye_squint += squint;
      s.expr.jaw_tension += Math.max(jawForward, blend(shapes, "mouthPucker") * 0.5);
      s.expr.smile += (blend(shapes, "mouthSmileLeft") + blend(shapes, "mouthSmileRight")) / 2;
      sec.expr += (browFurrow + lipPress + frown) / 3;

      // ---- lip biting / rolling -------------------------------------------
      const lipRoll = Math.max(blend(shapes, "mouthRollLower"), blend(shapes, "mouthRollUpper"));
      if (lipRoll > LIP_BITE) {
        s.lipBiteFrames += 1;
        flags.push("lip_bite");
      }

      // ---- jaw clench (muscle tension) ------------------------------------
      jawClench = mouthOpen < 0.06 && (lipPress > JAW_CLENCH_PRESS || jawForward > 0.3 || (cheekSquint > 0.2 && lipPress > 0.2));
      if (jawClench) {
        s.jawClenchFrames += 1;
        flags.push("jaw_clench");
      }
      updateEpisode(s.ep.jaw_clench, jawClench, ts, s.events, s.startTs);

      // ---- swallowing (approximate) ----------------------------------------
      // Chin (152) to nose-tip (1) distance, normalised by face height,
      // briefly dips while the mouth stays closed and the head is still.
      const throat = (landmarks[152].y - landmarks[1].y) / Math.max(box.h, 1e-3);
      s.throatBuf.push({ ts, v: throat });
      while (s.throatBuf.length && ts - s.throatBuf[0].ts > 1500) s.throatBuf.shift();
      if (s.throatBuf.length >= 8) {
        const base = median(s.throatBuf.slice(0, -3).map((b) => b.v));
        const dip = base - throat;
        const still = headSpeed < 30 && mouthOpen < 0.12;
        if (!s.swallowOn && dip > SWALLOW_DEV && still && ts - s.lastSwallowTs > SWALLOW_REFRACTORY_MS) {
          s.swallowOn = true;
          s.swallowStart = ts;
        } else if (s.swallowOn && (dip < SWALLOW_DEV * 0.4 || !still)) {
          s.swallowOn = false;
          const dur = ts - s.swallowStart;
          if (dur >= SWALLOW_MIN_MS && dur <= SWALLOW_MAX_MS && still) {
            s.swallowCount += 1;
            s.lastSwallowTs = ts;
            s.events.push({ type: "swallow", start: +((s.swallowStart - s.startTs) / 1000).toFixed(2), duration: +(dur / 1000).toFixed(2), note: "approximate" });
          }
        } else if (s.swallowOn && ts - s.swallowStart > SWALLOW_MAX_MS) {
          s.swallowOn = false;
        }
      }
    } else {
      // No face: close face-dependent episodes without counting flicker.
      updateEpisode(s.ep.gaze_away, false, ts, s.events, s.startTs);
      updateEpisode(s.ep.head_down, false, ts, s.events, s.startTs);
      updateEpisode(s.ep.jaw_clench, false, ts, s.events, s.startTs);
    }

    // ---- pose: shoulders, torso, arms --------------------------------------
    let shoulderRaised = false;
    let selfHug = false;
    let arms = null;
    if (poseLm && poseLm.length >= 25) {
      const vis = (i) => (poseLm[i].visibility ?? 1) > 0.5;
      if (vis(11) && vis(12)) {
        s.poseFrames += 1;
        const L = poseLm[11], R = poseLm[12];
        const width = Math.max(dist(L, R), 1e-3);
        const shoulderY = (L.y + R.y) / 2;
        const earY = vis(7) && vis(8) ? (poseLm[7].y + poseLm[8].y) / 2 : poseLm[0].y;
        const neck = (shoulderY - earY) / width;          // shrinks when shoulders rise
        const torso = (shoulderY - poseLm[0].y) / width;   // nose-to-shoulder height
        const asym = Math.abs(L.y - R.y) / width;
        s.shoulderAsymSum += asym;

        // Baselines from the opening ~3 s of pose frames.
        if (s.shoulderSamples.length < 60) {
          s.shoulderSamples.push(neck);
          s.torsoSamples.push(torso);
          s.widthSamples.push(width);
        } else {
          if (s.shoulderBase === null) {
            s.shoulderBase = median(s.shoulderSamples);
            s.torsoBase = median(s.torsoSamples);
            s.widthBase = median(s.widthSamples);
          }
          shoulderRaised = neck < s.shoulderBase * 0.82;
          if (shoulderRaised) s.shoulderRaiseFrames += 1;
          if (torso < s.torsoBase * 0.85) s.slouchFrames += 1;
          if (width < s.widthBase * 0.85) s.leanAwayFrames += 1;
        }

        // Arms: wrists (15/16), elbows (13/14) for stroking / hugging.
        if (vis(13) && vis(14) && vis(15) && vis(16)) {
          arms = {
            left: { shoulder: L, elbow: poseLm[13], wrist: poseLm[15] },
            right: { shoulder: R, elbow: poseLm[14], wrist: poseLm[16] },
          };
          const midX = (L.x + R.x) / 2;
          const hipY = vis(23) && vis(24) ? (poseLm[23].y + poseLm[24].y) / 2 : shoulderY + width * 1.6;
          const torsoBand = (p) => p.y > shoulderY - width * 0.1 && p.y < hipY;
          // Self-hug / arms crossed: each wrist across the midline, resting on the opposite upper arm.
          const lAcross = (poseLm[15].x - midX) * (L.x - midX) < 0 && torsoBand(poseLm[15]) && segDist(poseLm[15], R, poseLm[14]) < ARM_STROKE_DIST * 1.4;
          const rAcross = (poseLm[16].x - midX) * (R.x - midX) < 0 && torsoBand(poseLm[16]) && segDist(poseLm[16], L, poseLm[13]) < ARM_STROKE_DIST * 1.4;
          selfHug = lAcross && rAcross;
          if (selfHug) s.selfHugFrames += 1;
        }
      }
    }
    updateEpisode(s.ep.shoulder_raise, shoulderRaised, ts, s.events, s.startTs);
    updateEpisode(s.ep.self_hug, selfHug, ts, s.events, s.startTs);
    if (shoulderRaised || jawClench || selfHug) sec.tension += 1;

    // ---- hands -----------------------------------------------------------
    const hands = handResult?.landmarks || [];
    let touchingNow = false;
    let neckNow = false;
    let hairNow = false;
    let claspNow = false;
    let rubNow = false;
    let strokeNow = false;
    let handSpeed = 0;

    if (hands.length) {
      s.handFrames += 1;

      // face / neck / hair regions
      if (box) {
        const m = FACE_TOUCH_MARGIN;
        const inFace = (p) => p.x > box.minX - m && p.x < box.maxX + m && p.y > box.minY - m * 0.5 && p.y < box.maxY + m * 0.4;
        // Neck: directly below the chin, narrower than the face, down to about the collarbone.
        const inNeck = (p) => p.x > box.minX + box.w * 0.15 && p.x < box.maxX - box.w * 0.15 && p.y >= box.maxY + m * 0.4 && p.y < box.maxY + box.h * 0.55;
        const inHair = (p) => p.x > box.minX - m && p.x < box.maxX + m && p.y < box.minY - m * 0.5 && p.y > box.minY - box.h * 0.6;
        for (const h of hands) {
          for (const i of FINGERTIPS) {
            const p = h[i];
            if (!p) continue;
            if (inFace(p)) touchingNow = true;
            else if (inNeck(p)) neckNow = true;
            else if (inHair(p)) hairNow = true;
          }
        }
      }

      // velocity (wrist) — match hands by nearest previous wrist
      if (s.prevHands && dt > 0) {
        let speedTotal = 0;
        let n = 0;
        for (const h of hands) {
          let best = null;
          for (const ph of s.prevHands) {
            const d = dist(h[0], ph[0]);
            if (best === null || d < best) best = d;
          }
          if (best !== null && best < 0.3) {
            speedTotal += best / dt;
            n += 1;
          }
        }
        if (n) {
          handSpeed = speedTotal / n;
          s.speedSum += handSpeed;
          s.speedFrames += 1;
          sec.handSpeed += handSpeed;
          sec.handN += 1;
          if (!s.fidgetOn && handSpeed > FIDGET_SPEED && ts - s.lastFidgetTs > 300) {
            s.fidgetBursts += 1;
            s.lastFidgetTs = ts;
            s.fidgetOn = true;
            s.events.push({ type: "fidget", start: +((ts - s.startTs) / 1000).toFixed(2), duration: 0.3, intensity: +handSpeed.toFixed(2) });
          } else if (s.fidgetOn && handSpeed < FIDGET_SPEED * 0.5) {
            s.fidgetOn = false;
          }
        }
      }
      s.prevHands = hands;

      // two-hand gestures
      if (hands.length === 2) {
        const [a, b] = hands;
        const palmDist = dist(a[9], b[9]);
        if (palmDist < HANDS_TOGETHER_DIST) {
          s.handsTogetherFrames += 1;

          // finger clasp / interlacing: fingertips of each hand sit on the
          // knuckles of the other.
          const near = (tipsOf, mcpsOf) =>
            TIPS.filter((i) => MCPS.some((j) => dist(tipsOf[i], mcpsOf[j]) < CLASP_DIST)).length;
          claspNow = near(a, b) >= 2 && near(b, a) >= 2;

          // hand rubbing: hands together + oscillating relative motion
          const rel = { x: a[9].x - b[9].x, y: a[9].y - b[9].y };
          if (s.rubRel && dt > 0) {
            const vx = (rel.x - s.rubRel.x) / dt;
            const vy = (rel.y - s.rubRel.y) / dt;
            const relSpeed = Math.hypot(vx, vy);
            const axis = Math.abs(vx) >= Math.abs(vy) ? vx : vy;
            const sign = Math.sign(axis);
            if (relSpeed > RUB_REL_SPEED && sign !== 0) {
              if (s.rubLastSign !== 0 && sign !== s.rubLastSign) s.rubReversals.push(ts);
              s.rubLastSign = sign;
            }
          }
          s.rubRel = rel;
          s.rubReversals = s.rubReversals.filter((t) => ts - t <= RUB_WINDOW_MS);
          rubNow = s.rubReversals.length >= RUB_MIN_REVERSALS;
        } else {
          s.rubRel = null;
          s.rubReversals = [];
          s.rubLastSign = 0;
        }
      } else {
        s.rubRel = null;
        s.rubReversals = [];
        s.rubLastSign = 0;
      }
      if (claspNow) s.claspFrames += 1;

      // arm stroking: a hand moving along the opposite arm (needs pose)
      if (arms) {
        for (const h of hands) {
          const wrist = h[0];
          for (const side of ["left", "right"]) {
            const arm = arms[side];
            const other = side === "left" ? arms.right : arms.left;
            // this hand belongs to the arm whose pose-wrist is nearest
            if (dist(wrist, arm.wrist) > dist(wrist, other.wrist)) continue;
            const dUpper = segDist(wrist, other.shoulder, other.elbow);
            const dFore = segDist(wrist, other.elbow, other.wrist);
            if (Math.min(dUpper, dFore) < ARM_STROKE_DIST && handSpeed > ARM_STROKE_SPEED) strokeNow = true;
          }
        }
      }
    } else {
      s.prevHands = null;
      s.rubRel = null;
      s.rubReversals = [];
      s.rubLastSign = 0;
    }

    updateEpisode(s.ep.face_touch, touchingNow, ts, s.events, s.startTs);
    updateEpisode(s.ep.neck_touch, neckNow, ts, s.events, s.startTs);
    updateEpisode(s.ep.hair_touch, hairNow, ts, s.events, s.startTs);
    updateEpisode(s.ep.finger_clasp, claspNow, ts, s.events, s.startTs);
    updateEpisode(s.ep.hand_rub, rubNow, ts, s.events, s.startTs);
    updateEpisode(s.ep.arm_stroke, strokeNow, ts, s.events, s.startTs);

    const selfTouch = touchingNow || neckNow || hairNow || rubNow || strokeNow;
    if (selfTouch) sec.touch += 1;

    // ---- freeze: prolonged near-total stillness ------------------------------
    // Judged over a 1 s window (range of head yaw/pitch and wrist position)
    // so landmark jitter does not break a genuine freeze.
    let stillNow = false;
    if (landmarks && pose) {
      const wrist = hands.length ? hands.map((h) => h[0]) : [];
      s.motionBuf.push({ ts, yaw: pose.yaw, pitch: pose.pitch, wx: wrist.length ? mean(wrist.map((w) => w.x)) : null, wy: wrist.length ? mean(wrist.map((w) => w.y)) : null, nHands: hands.length });
      while (s.motionBuf.length && ts - s.motionBuf[0].ts > FREEZE_WINDOW_MS) s.motionBuf.shift();
      if (s.motionBuf.length >= 5 && ts - s.motionBuf[0].ts >= FREEZE_WINDOW_MS * 0.8) {
        const yaws = s.motionBuf.map((b) => b.yaw), pitches = s.motionBuf.map((b) => b.pitch);
        const headRange = Math.max(Math.max(...yaws) - Math.min(...yaws), Math.max(...pitches) - Math.min(...pitches));
        const withHands = s.motionBuf.filter((b) => b.wx !== null);
        let handRange = 0;
        if (withHands.length >= 3) {
          const xs = withHands.map((b) => b.wx), ys = withHands.map((b) => b.wy);
          handRange = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys));
        }
        const handsStable = withHands.length === 0 || withHands.length === s.motionBuf.length;
        stillNow = headRange < FREEZE_HEAD_RANGE_DEG && handRange < FREEZE_HAND_RANGE && handsStable;
      }
    } else {
      s.motionBuf = [];
    }
    if (stillNow) {
      if (s.freezeSince === null) s.freezeSince = ts;
    } else {
      if (s.freezeSince !== null && ts - s.freezeSince >= FREEZE_MIN_MS) s.freezeMs += ts - s.freezeSince;
      s.freezeSince = null;
    }
    updateEpisode(s.ep.freeze, stillNow, ts, s.events, s.startTs);

    s.lastFace = landmarks || null;
    s.lastHands = hands;
    s.lastPose = poseLm || null;

    if (touchingNow) flags.push("face_touch");
    if (neckNow) flags.push("neck_touch");
    if (hairNow) flags.push("hair_touch");
    if (claspNow) flags.push("finger_clasp");
    if (rubNow) flags.push("hand_rub");
    if (strokeNow) flags.push("arm_stroke");
    if (selfHug) flags.push("self_hug");
    if (shoulderRaised) flags.push("shoulder_raise");
    if (averted) flags.push("gaze_away");

    return {
      faceVisible: Boolean(landmarks),
      handsVisible: hands.length,
      poseVisible: Boolean(poseLm),
      averted,
      touching: selfTouch,
      tense: jawClench || shoulderRaised,
      pose,
      flags,
    };
  }

  /** Aggregated features in the backend contract shape. */
  function summary() {
    const elapsed = Math.max((s.lastTs - s.startTs) / 1000, 0.001);
    const minutes = elapsed / 60;
    const faceFrames = Math.max(s.faceFrames, 1);
    const frames = Math.max(s.frames, 1);
    const expression = {};
    for (const key of Object.keys(s.expr)) {
      expression[key] = +Math.min(1, s.expr[key] / faceFrames).toFixed(3);
    }

    // close in-progress episodes into a copy of the event list
    const ts = s.lastTs;
    const events = [...s.events];
    const counts = {};
    for (const key of Object.keys(s.ep)) {
      const ep = s.ep[key];
      let count = ep.count;
      let duration = ep.duration;
      if (ep.on && ts - ep.start >= ep.minMs) {
        count += 1;
        duration += (ts - ep.start) / 1000;
        events.push({ type: ep.type, start: +((ep.start - s.startTs) / 1000).toFixed(2), duration: +((ts - ep.start) / 1000).toFixed(2) });
      }
      counts[key] = { count, duration };
    }
    let freezeMs = s.freezeMs;
    if (s.freezeSince !== null && ts - s.freezeSince >= FREEZE_MIN_MS) freezeMs += ts - s.freezeSince;

    // blink rhythm regularity
    const intervals = [];
    for (let i = 1; i < s.blinkTimes.length; i += 1) intervals.push((s.blinkTimes[i] - s.blinkTimes[i - 1]) / 1000);
    const iMean = mean(intervals);
    const iStd = intervals.length > 1 ? Math.sqrt(mean(intervals.map((v) => (v - iMean) ** 2))) : 0;

    // timeline: include the current second
    const timeline = [...s.timeline];
    if (s.sec && s.sec.frames) {
      const c = s.sec;
      const ff = Math.max(c.faceFrames, 1);
      timeline.push({
        t: c.t,
        blink: c.blinks,
        gaze_away: +(c.away / ff).toFixed(2),
        self_touch: +(c.touch / c.frames).toFixed(2),
        hand_motion: +(c.handN ? c.handSpeed / c.handN : 0).toFixed(3),
        head_motion: +(c.headN ? c.headSpeed / c.headN / 60 : 0).toFixed(3),
        tension: +(c.tension / c.frames).toFixed(2),
        expression: +(c.expr / ff).toFixed(2),
      });
    }

    events.sort((a, b) => a.start - b.start);

    return {
      available: s.frames > 0,
      extended: true,
      tracker: TRACKER_VERSION,
      duration_sec: +elapsed.toFixed(2),
      frames_analyzed: s.frames,
      fps: +(s.frames / elapsed).toFixed(1),
      face_detected_ratio: +(s.faceFrames / frames).toFixed(3),
      hands_detected_ratio: +(s.handFrames / frames).toFixed(3),
      pose_detected_ratio: +(s.poseFrames / frames).toFixed(3),

      blink_count: s.blinkCount,
      blink_rate_per_min: +(s.blinkCount / minutes).toFixed(1),
      blink_burst_count: s.blinkBursts,
      blink_interval_cv: +(iMean > 0 ? Math.min(10, iStd / iMean) : 0).toFixed(3),
      gaze_aversion_ratio: +(s.avertedFrames / faceFrames).toFixed(3),
      gaze_shift_rate_per_min: +(s.gazeShifts / minutes).toFixed(1),
      eye_closure_ratio: +(s.closedFrames / faceFrames).toFixed(3),

      face_touch_count: counts.face_touch.count,
      face_touch_duration_sec: +counts.face_touch.duration.toFixed(2),
      hand_movement_energy: +(s.speedFrames ? s.speedSum / s.speedFrames : 0).toFixed(3),
      hand_fidget_rate_per_min: +(s.fidgetBursts / minutes).toFixed(1),
      hands_together_ratio: +(s.handsTogetherFrames / frames).toFixed(3),

      hand_rub_count: counts.hand_rub.count,
      hand_rub_duration_sec: +counts.hand_rub.duration.toFixed(2),
      finger_clasp_ratio: +(s.claspFrames / frames).toFixed(3),
      arm_stroke_count: counts.arm_stroke.count,
      arm_stroke_duration_sec: +counts.arm_stroke.duration.toFixed(2),
      self_hug_ratio: +(s.selfHugFrames / frames).toFixed(3),
      neck_touch_count: counts.neck_touch.count,
      neck_touch_duration_sec: +counts.neck_touch.duration.toFixed(2),
      hair_touch_count: counts.hair_touch.count,
      lip_bite_ratio: +(s.lipBiteFrames / faceFrames).toFixed(3),

      swallow_count: s.swallowCount,
      swallow_rate_per_min: +(s.swallowCount / minutes).toFixed(1),

      shoulder_raise_ratio: +(s.poseFrames ? s.shoulderRaiseFrames / s.poseFrames : 0).toFixed(3),
      shoulder_asymmetry: +(s.poseFrames ? Math.min(1, s.shoulderAsymSum / s.poseFrames) : 0).toFixed(3),
      jaw_clench_ratio: +(s.jawClenchFrames / faceFrames).toFixed(3),
      freeze_ratio: +Math.min(1, freezeMs / 1000 / elapsed).toFixed(3),
      slouch_ratio: +(s.poseFrames ? s.slouchFrames / s.poseFrames : 0).toFixed(3),
      lean_away_ratio: +(s.poseFrames ? s.leanAwayFrames / s.poseFrames : 0).toFixed(3),

      // deg/s normalised so that 60 deg/s == 1.0
      head_movement_energy: +(s.headFrames ? s.headSpeedSum / s.headFrames / 60 : 0).toFixed(3),
      head_shake_rate_per_min: +(s.headShakes / minutes).toFixed(1),
      posture_shift_count: s.postureShifts,
      head_down_ratio: +(s.headDownFrames / faceFrames).toFixed(3),

      expression,

      events: events.slice(-400),
      timeline: timeline.slice(-900),
    };
  }

  return { processFrame, summary, reset, _state: s };
}

