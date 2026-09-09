"""
Prosody engine
==============

Extracts *paralinguistic* voice nuances from an audio recording:

    * pauses / hesitation timing
    * pitch (F0) level, range, variability and jitter
    * loudness stability (shimmer)
    * voice depth (spectral weight of the voice)
    * breathing pattern (audible breath events between phrases)
    * voice tremor (4-10 Hz amplitude modulation)
    * speech rate (syllable-nucleus estimate)

Every feature is a plain number, and every number is turned into a
transparent 0-100 sub-score with a human readable "cue" so the
responder can see *why* the voice contributed to the SVI.

Design rules
------------
* Prosody is SUPPLEMENTARY. It never determines risk on its own.
* Normalisation ranges are engineering ranges for a prototype, not
  clinical thresholds.  They are declared once at the top so they are
  easy to tune against real data.
* Everything degrades gracefully: any failure returns
  ``{"available": False, "error": ...}``.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np


# ---------------------------------------------------------------------
# Analysis constants
# ---------------------------------------------------------------------

TARGET_SR = 16000
FRAME_LENGTH = 400          # 25 ms @ 16 kHz
HOP_LENGTH = 160            # 10 ms @ 16 kHz  -> envelope sampled at 100 Hz
ENVELOPE_RATE = TARGET_SR / HOP_LENGTH

MIN_PAUSE_SEC = 0.30        # silence shorter than this is normal articulation
BRIDGE_GAP_SEC = 0.25       # gaps shorter than this are merged into speech
LONG_PAUSE_SEC = 1.00
MIN_SPEECH_RUN_SEC = 0.10

F0_MIN = 65.0
F0_MAX = 450.0

BREATH_MIN_SEC = 0.12
BREATH_MAX_SEC = 0.80

TREMOR_BAND = (4.0, 10.0)   # Hz, physiological voice tremor band


# Engineering normalisation ranges (value -> 0..100 score).
# Each tuple is (low, high): value <= low -> 0, value >= high -> 100.
RANGES = {
    "pause_rate_per_min": (4.0, 20.0),
    "long_pause_count": (0.0, 6.0),
    "pause_ratio": (0.10, 0.45),
    "f0_cv": (0.10, 0.45),            # coefficient of variation of pitch
    "f0_semitone_range": (4.0, 16.0),
    "jitter_local": (0.006, 0.03),
    "shimmer_local": (0.03, 0.14),
    "breath_rate_per_min": (8.0, 26.0),
    "breath_intensity": (0.05, 0.35),
    "tremor_index": (0.10, 0.45),
    "voice_depth_index": (0.35, 0.75),  # higher = thinner / less chest resonance
}

# Speech-rate deviation: both very slow and very fast speech score.
SPEECH_RATE_NORMAL = (3.0, 5.5)       # syllables / sec
SPEECH_RATE_EXTREME = (1.5, 7.5)


SUB_WEIGHTS = {
    "pauses": 0.22,
    "pitch": 0.24,
    "breathing": 0.18,
    "tremor": 0.16,
    "rate": 0.10,
    "depth": 0.10,
}


# ---------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------

def scale(value: float, low: float, high: float) -> float:
    """Linear 0-100 scaling with clamping."""
    if high <= low:
        return 0.0
    score = (float(value) - low) / (high - low) * 100.0
    return round(max(0.0, min(100.0, score)), 1)


def _runs(mask: np.ndarray) -> List[tuple]:
    """Return (start, end) index pairs for runs of True."""
    runs = []
    if mask.size == 0:
        return runs
    padded = np.concatenate([[False], mask, [False]])
    diff = np.diff(padded.astype(np.int8))
    starts = np.where(diff == 1)[0]
    ends = np.where(diff == -1)[0]
    for s, e in zip(starts, ends):
        runs.append((int(s), int(e)))
    return runs


def _safe_mean(values) -> float:
    arr = np.asarray(list(values), dtype=np.float64)
    if arr.size == 0:
        return 0.0
    return float(np.mean(arr))


# ---------------------------------------------------------------------
# Audio loading
# ---------------------------------------------------------------------

def load_audio(audio_path: str):
    import librosa

    samples, sr = librosa.load(audio_path, sr=TARGET_SR, mono=True)
    samples = np.asarray(samples, dtype=np.float32)

    # Light normalisation so thresholds behave the same for quiet and
    # loud recordings.
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak > 0:
        samples = samples / peak * 0.9
    return samples, sr


# ---------------------------------------------------------------------
# Envelope / voice activity
# ---------------------------------------------------------------------

def compute_envelope(samples: np.ndarray) -> Dict[str, np.ndarray]:
    import librosa

    rms = librosa.feature.rms(
        y=samples,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
        center=True,
    )[0]

    zcr = librosa.feature.zero_crossing_rate(
        y=samples,
        frame_length=FRAME_LENGTH,
        hop_length=HOP_LENGTH,
        center=True,
    )[0]

    flatness = librosa.feature.spectral_flatness(
        y=samples,
        n_fft=512,
        hop_length=HOP_LENGTH,
    )[0]

    n = min(len(rms), len(zcr), len(flatness))
    return {
        "rms": rms[:n],
        "zcr": zcr[:n],
        "flatness": flatness[:n],
    }


def voice_activity(rms: np.ndarray) -> Dict[str, Any]:
    """
    Adaptive energy based voice-activity detection.

    Speech threshold sits between the noise floor (10th percentile)
    and the loud speech level (90th percentile).
    """
    if rms.size == 0:
        return {"speech": np.zeros(0, dtype=bool), "noise_floor": 0.0, "speech_level": 0.0}

    noise_floor = float(np.percentile(rms, 10))
    speech_level = float(np.percentile(rms, 90))
    threshold = noise_floor + 0.25 * (speech_level - noise_floor)
    threshold = max(threshold, 0.01)

    speech = rms > threshold

    # Bridge the tiny dips between syllables / words so a phrase is one
    # continuous speech run.  Only gaps >= MIN_PAUSE_SEC count as pauses.
    bridge = int(BRIDGE_GAP_SEC * ENVELOPE_RATE)
    for s, e in _runs(~speech):
        if 0 < s and e < len(speech) and (e - s) < bridge:
            speech[s:e] = True

    # Remove tiny speech blips
    min_run = int(MIN_SPEECH_RUN_SEC * ENVELOPE_RATE)
    for s, e in _runs(speech):
        if e - s < min_run:
            speech[s:e] = False

    return {
        "speech": speech,
        "noise_floor": noise_floor,
        "speech_level": speech_level,
        "threshold": threshold,
    }


# ---------------------------------------------------------------------
# Pauses
# ---------------------------------------------------------------------

def analyze_pauses(speech: np.ndarray) -> Dict[str, Any]:
    speech_runs = _runs(speech)
    if not speech_runs:
        return {
            "pause_count": 0,
            "long_pause_count": 0,
            "mean_pause_sec": 0.0,
            "max_pause_sec": 0.0,
            "pause_ratio": 0.0,
            "pause_rate_per_min": 0.0,
            "speech_time_sec": 0.0,
            "leading_silence_sec": 0.0,
        }

    first_speech = speech_runs[0][0]
    last_speech = speech_runs[-1][1]
    active = speech[first_speech:last_speech]

    pauses = [
        (e - s) / ENVELOPE_RATE
        for s, e in _runs(~active)
        if (e - s) / ENVELOPE_RATE >= MIN_PAUSE_SEC
    ]

    span_sec = max(len(active) / ENVELOPE_RATE, 1e-6)
    speech_time = float(active.sum()) / ENVELOPE_RATE
    total_pause = float(sum(pauses))

    return {
        "pause_count": len(pauses),
        "long_pause_count": int(sum(1 for p in pauses if p >= LONG_PAUSE_SEC)),
        "mean_pause_sec": round(_safe_mean(pauses), 2),
        "max_pause_sec": round(max(pauses) if pauses else 0.0, 2),
        "pause_ratio": round(total_pause / span_sec, 3),
        "pause_rate_per_min": round(len(pauses) / span_sec * 60.0, 1),
        "speech_time_sec": round(speech_time, 2),
        "leading_silence_sec": round(first_speech / ENVELOPE_RATE, 2),
    }


# ---------------------------------------------------------------------
# Pitch
# ---------------------------------------------------------------------

def analyze_pitch(samples: np.ndarray, sr: int, speech: np.ndarray) -> Dict[str, Any]:
    import librosa

    try:
        f0, voiced_flag, _ = librosa.pyin(
            samples,
            fmin=F0_MIN,
            fmax=F0_MAX,
            sr=sr,
            frame_length=1024,
            hop_length=HOP_LENGTH,
            fill_na=np.nan,
        )
    except Exception:
        return {"available": False}

    n = min(len(f0), len(speech))
    f0 = f0[:n]
    voiced = (~np.isnan(f0)) & speech[:n]
    values = f0[voiced]

    if values.size < 5:
        return {
            "available": False,
            "voiced_ratio": 0.0,
        }

    mean_f0 = float(np.mean(values))
    std_f0 = float(np.std(values))
    semitones = 12.0 * np.log2(values / max(mean_f0, 1e-6))
    p5, p95 = np.percentile(semitones, [5, 95])

    # Local jitter: cycle-to-cycle F0 perturbation approximated on
    # consecutive voiced frames.
    consecutive = []
    for s, e in _runs(voiced):
        seg = f0[s:e]
        if len(seg) >= 2:
            consecutive.append(np.abs(np.diff(seg)) / np.maximum(seg[:-1], 1e-6))
    jitter = float(np.mean(np.concatenate(consecutive))) if consecutive else 0.0

    # Pitch drift towards the end of the recording (rising pitch under
    # stress is a well-known effect).
    half = values.size // 2
    drift = float(np.mean(values[half:]) - np.mean(values[:half])) if half > 2 else 0.0

    return {
        "available": True,
        "_f0": f0,
        "f0_mean_hz": round(mean_f0, 1),
        "f0_std_hz": round(std_f0, 1),
        "f0_cv": round(std_f0 / max(mean_f0, 1e-6), 3),
        "f0_semitone_range": round(float(p95 - p5), 2),
        "f0_min_hz": round(float(np.min(values)), 1),
        "f0_max_hz": round(float(np.max(values)), 1),
        "jitter_local": round(jitter, 4),
        "pitch_drift_hz": round(drift, 1),
        "voiced_ratio": round(float(voiced.sum()) / max(float(speech[:n].sum()), 1.0), 3),
    }


# ---------------------------------------------------------------------
# Praat (parselmouth) refinements: jitter, shimmer, HNR
# ---------------------------------------------------------------------

def praat_voice_quality(audio_path: str) -> Dict[str, Any]:
    """
    Optional, higher fidelity jitter / shimmer / harmonic-to-noise ratio
    using Praat via parselmouth.  Silently skipped if not installed.
    """
    try:
        import parselmouth
        from parselmouth.praat import call
    except ImportError:
        return {"available": False}

    try:
        snd = parselmouth.Sound(audio_path)
        point_process = call(snd, "To PointProcess (periodic, cc)", F0_MIN, F0_MAX)
        jitter = call(point_process, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        shimmer = call(
            [snd, point_process],
            "Get shimmer (local)",
            0, 0, 0.0001, 0.02, 1.3, 1.6,
        )
        harmonicity = call(snd, "To Harmonicity (cc)", 0.01, F0_MIN, 0.1, 1.0)
        hnr = call(harmonicity, "Get mean", 0, 0)

        def clean(v):
            return None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 4)

        return {
            "available": True,
            "jitter_local": clean(jitter),
            "shimmer_local": clean(shimmer),
            "hnr_db": clean(hnr),
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


def fallback_shimmer(rms: np.ndarray, speech: np.ndarray) -> float:
    """Amplitude perturbation on consecutive speech frames."""
    vals = []
    for s, e in _runs(speech):
        seg = rms[s:e]
        if len(seg) >= 2:
            vals.append(np.abs(np.diff(seg)) / np.maximum(seg[:-1], 1e-6))
    if not vals:
        return 0.0
    return float(np.median(np.concatenate(vals)))


# ---------------------------------------------------------------------
# Voice depth
# ---------------------------------------------------------------------

def analyze_voice_depth(samples: np.ndarray, sr: int, speech: np.ndarray) -> Dict[str, Any]:
    """
    "Depth" of the voice = how much of the spectral energy sits in the
    low (chest resonance) band.  A tense / stressed voice typically gets
    thinner: energy shifts upward and the spectral centroid rises.

    voice_depth_index: 0 = very deep / relaxed, 1 = very thin / tense.
    """
    import librosa

    n_fft = 1024
    spec = np.abs(librosa.stft(samples, n_fft=n_fft, hop_length=HOP_LENGTH)) ** 2
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)

    n = min(spec.shape[1], len(speech))
    spec = spec[:, :n]
    mask = speech[:n]
    if mask.sum() == 0:
        return {"available": False}

    speech_spec = spec[:, mask]
    total = speech_spec.sum(axis=0) + 1e-9
    low = speech_spec[freqs < 500].sum(axis=0)
    high = speech_spec[(freqs >= 1500) & (freqs < 4000)].sum(axis=0)

    low_ratio = float(np.mean(low / total))
    high_ratio = float(np.mean(high / total))
    centroid = librosa.feature.spectral_centroid(S=np.sqrt(speech_spec), sr=sr)[0]
    centroid_mean = float(np.mean(centroid))

    # Map centroid 600 Hz (deep) .. 2400 Hz (thin) to 0..1 and blend
    # with high/low band balance.
    centroid_index = (centroid_mean - 600.0) / 1800.0
    band_index = high_ratio / max(high_ratio + low_ratio, 1e-6)
    depth_index = 0.6 * centroid_index + 0.4 * band_index
    depth_index = max(0.0, min(1.0, depth_index))

    return {
        "available": True,
        "spectral_centroid_hz": round(centroid_mean, 1),
        "low_band_ratio": round(low_ratio, 3),
        "high_band_ratio": round(high_ratio, 3),
        "voice_depth_index": round(depth_index, 3),
    }


# ---------------------------------------------------------------------
# Breathing
# ---------------------------------------------------------------------

def analyze_breathing(
    env: Dict[str, np.ndarray],
    speech: np.ndarray,
    noise_floor: float,
    speech_level: float,
) -> Dict[str, Any]:
    """
    Audible breath events: short, noise-like (high spectral flatness /
    high ZCR) bursts inside non-speech gaps, louder than the noise floor
    but well below speech level.
    """
    rms = env["rms"]
    zcr = env["zcr"]
    flat = env["flatness"]

    n = min(len(rms), len(speech))
    low = noise_floor + 0.08 * (speech_level - noise_floor)
    high = noise_floor + 0.45 * (speech_level - noise_floor)

    candidate = (~speech[:n]) & (rms[:n] > low) & (rms[:n] < high)
    noisy = (flat[:n] > 0.25) | (zcr[:n] > 0.15)
    candidate &= noisy

    min_len = int(BREATH_MIN_SEC * ENVELOPE_RATE)
    max_len = int(BREATH_MAX_SEC * ENVELOPE_RATE)

    breaths = []
    for s, e in _runs(candidate):
        if min_len <= (e - s) <= max_len:
            intensity = float(np.mean(rms[s:e])) / max(speech_level, 1e-6)
            breaths.append({"start": s / ENVELOPE_RATE, "duration": (e - s) / ENVELOPE_RATE, "intensity": intensity})

    duration_sec = max(n / ENVELOPE_RATE, 1e-6)
    intervals = np.diff([b["start"] for b in breaths]) if len(breaths) > 1 else np.array([])

    return {
        "breath_count": len(breaths),
        "breath_rate_per_min": round(len(breaths) / duration_sec * 60.0, 1),
        "breath_intensity": round(_safe_mean(b["intensity"] for b in breaths), 3),
        "mean_breath_duration_sec": round(_safe_mean(b["duration"] for b in breaths), 2),
        "breath_interval_cv": round(
            float(np.std(intervals) / max(np.mean(intervals), 1e-6)) if intervals.size > 1 else 0.0,
            3,
        ),
    }


# ---------------------------------------------------------------------
# Tremor
# ---------------------------------------------------------------------

def _band_ratio(signal: np.ndarray, notch_hz: Optional[float] = None) -> Optional[float]:
    """
    Energy in the tremor band relative to the 1-20 Hz modulation band of
    a 100 Hz-sampled contour.  ``notch_hz`` removes the syllable rhythm
    (which naturally sits at 3-6 Hz and would otherwise masquerade as
    tremor).
    """
    if len(signal) < int(0.6 * ENVELOPE_RATE):
        return None
    seg = signal - np.mean(signal)
    seg = seg * np.hanning(len(seg))
    spectrum = np.abs(np.fft.rfft(seg)) ** 2
    freqs = np.fft.rfftfreq(len(seg), d=1.0 / ENVELOPE_RATE)

    reference = (freqs >= 1.0) & (freqs <= 20.0)
    in_band = (freqs >= TREMOR_BAND[0]) & (freqs <= TREMOR_BAND[1])
    if notch_hz:
        notch = (freqs >= notch_hz - 0.75) & (freqs <= notch_hz + 0.75)
        in_band &= ~notch
        reference &= ~notch
    total = float(spectrum[reference].sum())
    if total <= 0:
        return None
    return float(spectrum[in_band].sum() / total)


def analyze_tremor(
    rms: np.ndarray,
    speech: np.ndarray,
    f0: Optional[np.ndarray] = None,
    syllable_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Voice tremor = rhythmic 4-10 Hz modulation of loudness (amplitude
    tremor) and/or pitch (frequency tremor) inside speech runs.

    The syllable rhythm is notched out of the amplitude estimate, and
    the pitch contour is detrended (250 ms moving average) so that
    normal intonation does not count as tremor.
    """
    amp_ratios: List[float] = []
    f0_ratios: List[float] = []
    notch = syllable_rate if syllable_rate and syllable_rate > 0 else None

    for s, e in _runs(speech):
        seg_rms = rms[s:e]
        ratio = _band_ratio(seg_rms, notch_hz=notch)
        if ratio is not None:
            # Gate on modulation depth: a flat envelope has no tremor
            # even if its tiny residual happens to sit in-band.
            depth = float(np.std(seg_rms) / max(np.mean(seg_rms), 1e-6))
            amp_ratios.append(ratio if depth >= 0.15 else 0.0)

        if f0 is not None and e <= len(f0):
            seg = f0[s:e]
            if np.isnan(seg).mean() < 0.3 and len(seg) >= int(0.6 * ENVELOPE_RATE):
                seg = np.where(np.isnan(seg), np.nanmean(seg), seg)
                semitones = 12.0 * np.log2(np.maximum(seg, 1.0) / max(np.mean(seg), 1.0))
                kernel = np.ones(25) / 25.0
                residual = semitones - np.convolve(semitones, kernel, mode="same")
                ratio = _band_ratio(residual)
                if ratio is not None:
                    # Need at least ~0.25 semitone of wobble to count.
                    f0_ratios.append(ratio if float(np.std(residual)) >= 0.25 else 0.0)

    amp = float(np.mean(amp_ratios)) if amp_ratios else 0.0
    freq = float(np.mean(f0_ratios)) if f0_ratios else 0.0
    return {
        "tremor_index": round(max(amp, freq), 3),
        "amplitude_tremor": round(amp, 3),
        "frequency_tremor": round(freq, 3),
        "tremor_segments": len(amp_ratios),
    }


# ---------------------------------------------------------------------
# Speech rate
# ---------------------------------------------------------------------

def analyze_speech_rate(rms: np.ndarray, speech: np.ndarray, speech_time_sec: float) -> Dict[str, Any]:
    """
    Syllable-nucleus estimate: local peaks of a smoothed envelope inside
    speech regions.  Rough but robust across languages.
    """
    if speech_time_sec <= 0:
        return {"syllable_rate": 0.0, "syllable_count": 0}

    kernel = np.ones(5) / 5.0
    smooth = np.convolve(rms, kernel, mode="same")
    peaks = 0
    for s, e in _runs(speech):
        seg = smooth[s:e]
        if len(seg) < 3:
            continue
        local = (seg[1:-1] > seg[:-2]) & (seg[1:-1] >= seg[2:]) & (seg[1:-1] > 0.3 * seg.max())
        # Enforce a minimum 120 ms distance between nuclei
        idx = np.where(local)[0]
        last = -100
        for i in idx:
            if i - last >= int(0.12 * ENVELOPE_RATE):
                peaks += 1
                last = i

    return {
        "syllable_count": int(peaks),
        "syllable_rate": round(peaks / speech_time_sec, 2),
    }


# ---------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------

def extract_prosody_features(audio_path: str) -> Dict[str, Any]:
    """
    Extract every prosodic feature from an audio file.

    Returns a flat dictionary (with nested ``pitch`` / ``breathing`` /
    ``pauses`` groups for readability).
    """
    try:
        samples, sr = load_audio(audio_path)
    except Exception as exc:
        return {"available": False, "error": f"Could not decode audio: {exc}"}

    if samples.size < sr * 0.5:
        return {"available": False, "error": "Audio too short for prosodic analysis."}

    try:
        env = compute_envelope(samples)
        vad = voice_activity(env["rms"])
        speech = vad["speech"]

        pauses = analyze_pauses(speech)
        pitch = analyze_pitch(samples, sr, speech)
        f0_contour = pitch.pop("_f0", None)
        depth = analyze_voice_depth(samples, sr, speech)
        breathing = analyze_breathing(env, speech, vad["noise_floor"], vad["speech_level"])
        rate = analyze_speech_rate(env["rms"], speech, pauses["speech_time_sec"])
        tremor = analyze_tremor(
            env["rms"],
            speech,
            f0=f0_contour,
            syllable_rate=rate.get("syllable_rate"),
        )
        praat = praat_voice_quality(audio_path)

        if praat.get("available"):
            if praat.get("jitter_local") is not None:
                pitch["jitter_local"] = praat["jitter_local"]
            shimmer = praat.get("shimmer_local")
            hnr = praat.get("hnr_db")
        else:
            shimmer = None
            hnr = None

        if shimmer is None:
            shimmer = round(fallback_shimmer(env["rms"], speech), 4)

        # Whole-recording tone: arousal vs. the speaker's own opening
        # baseline, flatness, strain, instability and trajectory.
        try:
            from services.tone_engine import extract_tone_features

            tone = extract_tone_features(
                env["rms"],
                speech,
                f0=f0_contour,
                flatness=env["flatness"],
                hnr_db=hnr,
                f0_semitone_range=pitch.get("f0_semitone_range") if pitch.get("available") else None,
            )
        except Exception as exc:  # tone is optional
            tone = {"available": False, "error": str(exc)}

        duration = len(samples) / sr
        return {
            "available": True,
            "duration_sec": round(duration, 2),
            "speech_ratio": round(pauses["speech_time_sec"] / max(duration, 1e-6), 3),
            "pauses": pauses,
            "pitch": pitch,
            "voice_quality": {
                "shimmer_local": shimmer,
                "hnr_db": hnr,
                "praat_used": bool(praat.get("available")),
            },
            "depth": depth,
            "breathing": breathing,
            "tremor": tremor,
            "rate": rate,
            "tone": tone,
        }
    except Exception as exc:
        return {"available": False, "error": str(exc)}


# ---------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------

def _rate_score(syllable_rate: float) -> float:
    if syllable_rate <= 0:
        return 0.0
    lo_n, hi_n = SPEECH_RATE_NORMAL
    lo_x, hi_x = SPEECH_RATE_EXTREME
    if lo_n <= syllable_rate <= hi_n:
        return 0.0
    if syllable_rate < lo_n:
        return scale(lo_n - syllable_rate, 0.0, lo_n - lo_x)
    return scale(syllable_rate - hi_n, 0.0, hi_x - hi_n)


def calculate_prosody_indicator(features: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert prosodic features into a 0-100 supplementary indicator with
    transparent sub-scores and human readable cues.
    """
    if not features.get("available"):
        return {
            "available": False,
            "indicator": 0.0,
            "sub_scores": {},
            "cues": [],
        }

    pauses = features.get("pauses", {})
    pitch = features.get("pitch", {})
    quality = features.get("voice_quality", {})
    depth = features.get("depth", {})
    breathing = features.get("breathing", {})
    tremor = features.get("tremor", {})
    rate = features.get("rate", {})

    cues: List[str] = []

    # --- pauses -----------------------------------------------------
    pause_score = max(
        scale(pauses.get("pause_rate_per_min", 0), *RANGES["pause_rate_per_min"]),
        scale(pauses.get("long_pause_count", 0), *RANGES["long_pause_count"]),
        scale(pauses.get("pause_ratio", 0), *RANGES["pause_ratio"]),
    )
    if pauses.get("long_pause_count", 0) >= 2:
        cues.append(
            f"Frequent long pauses ({pauses['long_pause_count']} pauses over "
            f"{LONG_PAUSE_SEC:.0f}s, longest {pauses.get('max_pause_sec', 0):.1f}s) "
            "suggesting hesitation or difficulty continuing."
        )
    elif pause_score >= 50:
        cues.append("Speech was frequently interrupted by pauses.")

    # --- pitch --------------------------------------------------------
    if pitch.get("available"):
        pitch_score = (
            0.35 * scale(pitch.get("f0_cv", 0), *RANGES["f0_cv"])
            + 0.25 * scale(pitch.get("f0_semitone_range", 0), *RANGES["f0_semitone_range"])
            + 0.40 * scale(pitch.get("jitter_local", 0), *RANGES["jitter_local"])
        )
        if pitch.get("jitter_local", 0) >= RANGES["jitter_local"][0] * 1.5:
            cues.append("Unsteady pitch (elevated jitter) consistent with a shaky or strained voice.")
        if pitch.get("f0_cv", 0) >= RANGES["f0_cv"][1] * 0.8:
            cues.append("Highly variable pitch across the statement.")
        if pitch.get("pitch_drift_hz", 0) >= 20:
            cues.append("Pitch rose noticeably as the statement went on.")
    else:
        pitch_score = 0.0

    shimmer = quality.get("shimmer_local") or 0.0
    shimmer_score = scale(shimmer, *RANGES["shimmer_local"])
    pitch_score = round(0.8 * pitch_score + 0.2 * shimmer_score, 1)
    if shimmer_score >= 60:
        cues.append("Unstable loudness (shimmer) indicating vocal tension.")

    # --- breathing ----------------------------------------------------
    breathing_score = max(
        scale(breathing.get("breath_rate_per_min", 0), *RANGES["breath_rate_per_min"]),
        0.7 * scale(breathing.get("breath_intensity", 0), *RANGES["breath_intensity"]),
    )
    if breathing.get("breath_rate_per_min", 0) >= RANGES["breath_rate_per_min"][1] * 0.75:
        cues.append(
            f"Rapid or audible breathing ({breathing['breath_rate_per_min']:.0f} breaths/min "
            "detected between phrases)."
        )
    if breathing.get("breath_interval_cv", 0) >= 0.8 and breathing.get("breath_count", 0) >= 4:
        cues.append("Irregular breathing rhythm.")

    # --- tremor -------------------------------------------------------
    tremor_score = scale(tremor.get("tremor_index", 0), *RANGES["tremor_index"])
    if tremor_score >= 50:
        cues.append("Voice tremor (4-10 Hz amplitude modulation) detected.")

    # --- speech rate ----------------------------------------------------
    syl_rate = rate.get("syllable_rate", 0)
    rate_score = _rate_score(syl_rate)
    if syl_rate and syl_rate > SPEECH_RATE_NORMAL[1]:
        cues.append(f"Fast, pressured speech (~{syl_rate:.1f} syllables/sec).")
    elif syl_rate and syl_rate < SPEECH_RATE_NORMAL[0]:
        cues.append(f"Slow, effortful speech (~{syl_rate:.1f} syllables/sec).")

    # --- voice depth ---------------------------------------------------
    depth_score = scale(depth.get("voice_depth_index", 0), *RANGES["voice_depth_index"]) if depth.get("available") else 0.0
    if depth_score >= 60:
        cues.append("Thin, tense vocal quality (reduced chest resonance).")

    sub_scores = {
        "pauses": round(pause_score, 1),
        "pitch": round(pitch_score, 1),
        "breathing": round(breathing_score, 1),
        "tremor": round(tremor_score, 1),
        "rate": round(rate_score, 1),
        "depth": round(depth_score, 1),
    }

    indicator = sum(sub_scores[k] * w for k, w in SUB_WEIGHTS.items())

    return {
        "available": True,
        "indicator": round(max(0.0, min(100.0, indicator)), 1),
        "sub_scores": sub_scores,
        "cues": cues,
    }


__all__ = [
    "extract_prosody_features",
    "calculate_prosody_indicator",
    "scale",
]
