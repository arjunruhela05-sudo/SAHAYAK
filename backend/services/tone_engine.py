"""
Tone engine
===========

Reads the *emotional tone* of a recording over its whole course, rather
than as one averaged number.  Where the prosody engine answers "how much
jitter / how many pauses", the tone engine answers:

    * arousal        is the voice agitated (louder, higher, faster than the
                     speaker's own opening baseline) or withdrawn?
    * flatness       monotone, low-energy delivery (numbing / withdrawal)
    * strain         hoarse, pressed voice quality (low HNR, noisy spectrum)
    * instability    loudness and pace swinging between phrases,
                     phrases trailing off, sudden loud bursts
    * trajectory     how arousal evolves across the recording:
                     steady / escalating / collapsing / volatile

All features are derived from the same 100 Hz contours the prosody engine
already computes (RMS envelope, speech mask, F0), so the cost is small.
A per-window timeline is returned for the responder-side chart.

Tone is SUPPLEMENTARY: it never determines risk on its own.  Ranges are
engineering values for a prototype, not clinical thresholds.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


ENVELOPE_RATE = 100.0          # frames per second of the contours
WINDOW_SEC = 3.0
HOP_SEC = 1.5
MIN_SPEECH_IN_WINDOW = 0.35    # a window needs this much speech to count
BASELINE_WINDOWS = 3           # opening windows define the speaker's own baseline

RANGES = {
    "f0_rise_semitones": (1.0, 6.0),
    "energy_rise_ratio": (0.10, 0.60),       # (late - early) / early
    "rate_rise_ratio": (0.10, 0.45),
    "f0_range_semitones_flat": (5.0, 2.0),   # inverted: smaller range -> flatter
    "energy_cv_flat": (0.30, 0.10),          # inverted
    "hnr_db_strain": (16.0, 6.0),            # inverted: lower HNR -> more strain
    "flatness_strain": (0.10, 0.30),
    "energy_cv_unstable": (0.35, 0.80),
    "rate_cv_unstable": (0.20, 0.55),
    "trail_off_ratio": (0.15, 0.55),
    "burst_ratio": (0.08, 0.30),
    "fade_ratio": (0.85, 0.55),              # inverted: last/first energy
    "arousal_slope": (0.03, 0.15),
    "arousal_range": (0.30, 0.90),
}

SUB_WEIGHTS = {
    "arousal": 0.25,
    "flatness": 0.20,
    "strain": 0.15,
    "instability": 0.20,
    "trajectory": 0.20,
}


def _scale(value: float, low: float, high: float) -> float:
    """0-100 linear scaling; supports inverted ranges (low > high)."""
    if low == high:
        return 0.0
    if low < high:
        score = (float(value) - low) / (high - low) * 100.0
    else:
        score = (low - float(value)) / (low - high) * 100.0
    return round(max(0.0, min(100.0, score)), 1)


def _runs(mask: np.ndarray) -> List[tuple]:
    runs = []
    if mask.size == 0:
        return runs
    padded = np.concatenate([[False], mask, [False]])
    diff = np.diff(padded.astype(np.int8))
    for s, e in zip(np.where(diff == 1)[0], np.where(diff == -1)[0]):
        runs.append((int(s), int(e)))
    return runs


def _cv(values: List[float]) -> float:
    arr = np.asarray(values, dtype=np.float64)
    if arr.size < 2:
        return 0.0
    mean = float(np.mean(arr))
    if mean <= 1e-9:
        return 0.0
    return float(np.std(arr) / mean)


def _slope(values: List[float]) -> float:
    if len(values) < 3:
        return 0.0
    xs = np.arange(len(values), dtype=np.float64)
    ys = np.asarray(values, dtype=np.float64)
    xs -= xs.mean()
    den = float((xs ** 2).sum()) or 1.0
    return float((xs * (ys - ys.mean())).sum() / den)


# ---------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------

def extract_tone_features(
    rms: np.ndarray,
    speech: np.ndarray,
    f0: Optional[np.ndarray] = None,
    flatness: Optional[np.ndarray] = None,
    hnr_db: Optional[float] = None,
    f0_semitone_range: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Windowed tone description of the recording.

    ``rms`` / ``speech`` / ``f0`` / ``flatness`` are 100 Hz contours of the
    same length (``f0`` may contain NaN on unvoiced frames).
    """
    n = int(min(len(rms), len(speech)))
    if f0 is not None:
        n = min(n, len(f0))
    if flatness is not None:
        n = min(n, len(flatness))
    if n < int(2 * WINDOW_SEC * ENVELOPE_RATE):
        return {"available": False, "error": "Recording too short for tone analysis."}

    rms = np.asarray(rms[:n], dtype=np.float64)
    speech = np.asarray(speech[:n], dtype=bool)
    f0 = np.asarray(f0[:n], dtype=np.float64) if f0 is not None else None
    flatness = np.asarray(flatness[:n], dtype=np.float64) if flatness is not None else None

    if speech.sum() < int(1.0 * ENVELOPE_RATE):
        return {"available": False, "error": "Too little speech for tone analysis."}

    # Global pitch reference (semitones relative to the median voiced F0)
    f0_ref = None
    if f0 is not None:
        voiced = (~np.isnan(f0)) & speech
        if voiced.sum() >= 10:
            f0_ref = float(np.median(f0[voiced]))

    # Syllable nuclei (same estimate as the prosody engine, per window)
    kernel = np.ones(5) / 5.0
    smooth = np.convolve(rms, kernel, mode="same")
    nuclei = np.zeros(n, dtype=bool)
    for s, e in _runs(speech):
        seg = smooth[s:e]
        if len(seg) < 3:
            continue
        local = (seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:]) & (seg[1:-1] > 0.3 * seg.max())
        last = -100
        for i in np.where(local)[0]:
            if i - last >= int(0.12 * ENVELOPE_RATE):
                nuclei[s + 1 + i] = True
                last = i

    win = int(WINDOW_SEC * ENVELOPE_RATE)
    hop = int(HOP_SEC * ENVELOPE_RATE)

    windows: List[Dict[str, float]] = []
    for start in range(0, max(n - win, 0) + 1, hop):
        end = start + win
        sp = speech[start:end]
        speech_frac = float(sp.mean()) if sp.size else 0.0
        if speech_frac < MIN_SPEECH_IN_WINDOW:
            continue
        seg_rms = rms[start:end][sp]
        energy = float(np.mean(seg_rms)) if seg_rms.size else 0.0
        speech_sec = float(sp.sum()) / ENVELOPE_RATE
        rate = float(nuclei[start:end].sum()) / max(speech_sec, 1e-6)

        pitch_st = None
        if f0 is not None and f0_ref:
            seg_f0 = f0[start:end]
            v = (~np.isnan(seg_f0)) & sp
            if v.sum() >= 5:
                pitch_st = float(12.0 * np.log2(np.median(seg_f0[v]) / f0_ref))

        flat = None
        if flatness is not None:
            seg_flat = flatness[start:end][sp]
            if seg_flat.size:
                flat = float(np.mean(seg_flat))

        windows.append({
            "t": round(start / ENVELOPE_RATE, 2),
            "energy": energy,
            "pitch_st": pitch_st,
            "rate": rate,
            "pause_ratio": round(1.0 - speech_frac, 3),
            "flatness": flat,
        })

    if len(windows) < 2:
        return {"available": False, "error": "Not enough speech windows for tone analysis."}

    energies = [w["energy"] for w in windows]
    rates = [w["rate"] for w in windows]
    pitches = [w["pitch_st"] for w in windows if w["pitch_st"] is not None]

    # --- speaker's own baseline = opening windows --------------------
    k = min(BASELINE_WINDOWS, max(1, len(windows) // 3))
    base_energy = float(np.mean(energies[:k])) or 1e-6
    base_rate = float(np.mean(rates[:k])) or 1e-6
    base_pitch = float(np.mean(pitches[:k])) if len(pitches) >= k else 0.0

    # --- per-window arousal (relative to baseline) -------------------
    arousal: List[float] = []
    for w in windows:
        e = (w["energy"] - base_energy) / base_energy            # ~ -1 .. +1
        r = (w["rate"] - base_rate) / base_rate
        p = ((w["pitch_st"] - base_pitch) / 6.0) if w["pitch_st"] is not None else 0.0
        value = 0.4 * np.tanh(e) + 0.3 * np.tanh(r) + 0.3 * np.tanh(p)
        w["arousal"] = round(float(value), 3)
        arousal.append(float(value))

    third = max(1, len(windows) // 3)
    early = windows[:third]
    late = windows[-third:]

    def _mean(items, key):
        vals = [i[key] for i in items if i.get(key) is not None]
        return float(np.mean(vals)) if vals else 0.0

    early_energy = _mean(early, "energy") or 1e-6
    late_energy = _mean(late, "energy")
    energy_rise_ratio = (late_energy - early_energy) / early_energy
    fade_ratio = late_energy / early_energy

    early_rate = _mean(early, "rate") or 1e-6
    late_rate = _mean(late, "rate")
    rate_rise_ratio = (late_rate - early_rate) / early_rate

    f0_rise = _mean(late, "pitch_st") - _mean(early, "pitch_st") if pitches else 0.0

    # --- trailing off: energy in the last 20 % of each phrase ---------
    trail = 0
    phrases = 0
    for s, e in _runs(speech):
        if e - s < int(0.8 * ENVELOPE_RATE):
            continue
        phrases += 1
        seg = rms[s:e]
        tail = seg[int(0.8 * len(seg)):]
        if tail.size and float(np.mean(tail)) < 0.5 * float(np.mean(seg)):
            trail += 1
    trail_off_ratio = trail / phrases if phrases else 0.0

    # --- bursts: windows far louder than the typical window -----------
    median_energy = float(np.median(energies)) or 1e-6
    burst_ratio = float(np.mean([e > 1.8 * median_energy for e in energies]))

    flat_mean = float(np.mean([w["flatness"] for w in windows if w["flatness"] is not None])) if flatness is not None else None

    slope = _slope(arousal)
    arousal_range = float(max(arousal) - min(arousal))
    if slope >= RANGES["arousal_slope"][0]:
        trajectory = "escalating"
    elif slope <= -RANGES["arousal_slope"][0]:
        trajectory = "collapsing"
    elif arousal_range >= RANGES["arousal_range"][0]:
        trajectory = "volatile"
    else:
        trajectory = "steady"

    return {
        "available": True,
        "window_sec": WINDOW_SEC,
        "window_count": len(windows),
        "f0_rise_semitones": round(float(f0_rise), 2),
        "energy_rise_ratio": round(float(energy_rise_ratio), 3),
        "rate_rise_ratio": round(float(rate_rise_ratio), 3),
        "fade_ratio": round(float(fade_ratio), 3),
        "energy_cv": round(_cv(energies), 3),
        "rate_cv": round(_cv(rates), 3),
        "pitch_cv_semitones": round(float(np.std(pitches)), 2) if len(pitches) >= 2 else 0.0,
        "f0_semitone_range": round(float(f0_semitone_range), 2) if f0_semitone_range is not None else None,
        "hnr_db": round(float(hnr_db), 2) if hnr_db is not None else None,
        "spectral_flatness": round(flat_mean, 3) if flat_mean is not None else None,
        "trail_off_ratio": round(float(trail_off_ratio), 3),
        "burst_ratio": round(float(burst_ratio), 3),
        "arousal_mean": round(float(np.mean(arousal)), 3),
        "arousal_slope": round(float(slope), 4),
        "arousal_range": round(arousal_range, 3),
        "trajectory": trajectory,
        "timeline": [
            {
                "t": w["t"],
                "energy": round(w["energy"], 4),
                "pitch_st": round(w["pitch_st"], 2) if w["pitch_st"] is not None else None,
                "rate": round(w["rate"], 2),
                "pause_ratio": w["pause_ratio"],
                "arousal": w["arousal"],
            }
            for w in windows
        ],
    }


# ---------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------

def calculate_tone_indicator(features: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not features or not features.get("available"):
        return {"available": False, "indicator": 0.0, "sub_scores": {}, "cues": [], "label": "unavailable"}

    cues: List[str] = []
    f = features

    # --- arousal: louder / higher / faster than the speaker's own start
    arousal_score = max(
        _scale(f.get("f0_rise_semitones", 0), *RANGES["f0_rise_semitones"]),
        _scale(f.get("energy_rise_ratio", 0), *RANGES["energy_rise_ratio"]),
        _scale(f.get("rate_rise_ratio", 0), *RANGES["rate_rise_ratio"]),
    )
    rising = []
    if f.get("f0_rise_semitones", 0) >= RANGES["f0_rise_semitones"][0] * 1.5:
        rising.append("higher-pitched")
    if f.get("energy_rise_ratio", 0) >= RANGES["energy_rise_ratio"][0] * 1.5:
        rising.append("louder")
    if f.get("rate_rise_ratio", 0) >= RANGES["rate_rise_ratio"][0] * 1.5:
        rising.append("faster")
    if rising:
        cues.append(f"The voice became {' and '.join(rising)} as the account went on (rising arousal).")

    # --- flatness: monotone, low-dynamic delivery ----------------------
    flat_parts = []
    if f.get("f0_semitone_range") is not None:
        flat_parts.append(_scale(f["f0_semitone_range"], *RANGES["f0_range_semitones_flat"]))
    flat_parts.append(_scale(f.get("energy_cv", 1.0), *RANGES["energy_cv_flat"]))
    flatness_score = float(np.mean(flat_parts)) if flat_parts else 0.0
    if flatness_score >= 60:
        cues.append("Flat, monotone delivery with little vocal energy — consistent with emotional numbing or withdrawal.")

    # --- strain: hoarse / pressed voice -------------------------------
    strain_parts = []
    if f.get("hnr_db") is not None:
        strain_parts.append(_scale(f["hnr_db"], *RANGES["hnr_db_strain"]))
    if f.get("spectral_flatness") is not None:
        strain_parts.append(_scale(f["spectral_flatness"], *RANGES["flatness_strain"]))
    strain_score = float(max(strain_parts)) if strain_parts else 0.0
    if strain_score >= 55:
        cues.append("Strained, hoarse voice quality (noisy, low harmonic-to-noise ratio).")

    # --- instability ------------------------------------------------------
    instability_score = max(
        _scale(f.get("energy_cv", 0), *RANGES["energy_cv_unstable"]),
        _scale(f.get("rate_cv", 0), *RANGES["rate_cv_unstable"]),
        _scale(f.get("trail_off_ratio", 0), *RANGES["trail_off_ratio"]),
        0.8 * _scale(f.get("burst_ratio", 0), *RANGES["burst_ratio"]),
        0.8 * _scale(f.get("fade_ratio", 1.0), *RANGES["fade_ratio"]),
    )
    if f.get("energy_cv", 0) >= RANGES["energy_cv_unstable"][0] * 1.3:
        cues.append("Loudness swung sharply between phrases.")
    if f.get("rate_cv", 0) >= RANGES["rate_cv_unstable"][0] * 1.3:
        cues.append("Speaking pace was erratic — rushing, then slowing.")
    if f.get("trail_off_ratio", 0) >= RANGES["trail_off_ratio"][0] * 1.5:
        cues.append("Many phrases trailed off into near-silence.")
    if f.get("fade_ratio", 1.0) <= RANGES["fade_ratio"][1] * 1.15:
        cues.append("The voice faded noticeably towards the end of the recording.")
    if f.get("burst_ratio", 0) >= RANGES["burst_ratio"][0] * 1.5:
        cues.append("Sudden loud outbursts between quieter passages.")

    # --- trajectory -------------------------------------------------------
    trajectory = f.get("trajectory", "steady")
    trajectory_score = max(
        _scale(abs(f.get("arousal_slope", 0)), *RANGES["arousal_slope"]),
        0.9 * _scale(f.get("arousal_range", 0), *RANGES["arousal_range"]),
    )
    if trajectory == "escalating" and trajectory_score >= 40:
        cues.append("Emotional arousal escalated steadily over the recording.")
    elif trajectory == "collapsing" and trajectory_score >= 40:
        cues.append("The voice lost energy and pitch over the recording (collapsing arousal).")
    elif trajectory == "volatile" and trajectory_score >= 40:
        cues.append("Emotional arousal was volatile, rising and falling sharply.")

    sub_scores = {
        "arousal": round(arousal_score, 1),
        "flatness": round(flatness_score, 1),
        "strain": round(strain_score, 1),
        "instability": round(instability_score, 1),
        "trajectory": round(trajectory_score, 1),
    }
    indicator = sum(sub_scores[k] * w for k, w in SUB_WEIGHTS.items())

    # A short tone label for the responder view.
    if arousal_score >= 55 and instability_score >= 40:
        label = "agitated"
    elif flatness_score >= 60:
        label = "flat / withdrawn"
    elif strain_score >= 55:
        label = "strained"
    elif instability_score >= 55:
        label = "unstable"
    elif trajectory in ("escalating", "volatile") and trajectory_score >= 40:
        label = trajectory
    else:
        label = "steady"

    return {
        "available": True,
        "indicator": round(max(0.0, min(100.0, indicator)), 1),
        "sub_scores": sub_scores,
        "cues": cues,
        "label": label,
        "trajectory": trajectory,
    }


__all__ = ["extract_tone_features", "calculate_tone_indicator"]
