import numpy as np
import pytest
import soundfile as sf

from services.prosody_engine import extract_prosody_features
from services.tone_engine import calculate_tone_indicator, extract_tone_features


SR = 16000


def _phrase(duration, f0=140.0, amp=0.5, syl=4.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(duration * SR)) / SR
    phase = 2 * np.pi * f0 * t
    signal = np.sin(phase) + 0.5 * np.sin(2 * phase) + 0.25 * np.sin(3 * phase)
    return signal * 0.5 * (1 + np.sin(2 * np.pi * syl * t)) * amp + rng.standard_normal(len(t)) * 0.002


def _silence(duration, seed=1):
    return np.random.default_rng(seed).standard_normal(int(duration * SR)) * 0.002


def _write(tmp_path_factory, name, audio):
    path = tmp_path_factory.mktemp("tone") / name
    sf.write(path, audio, SR)
    return str(path)


@pytest.fixture(scope="module")
def steady_wav(tmp_path_factory):
    parts = [_silence(0.5)]
    for i in range(6):
        parts += [_phrase(2.5, 140, 0.5, 4.0, seed=i), _silence(0.3)]
    return _write(tmp_path_factory, "steady.wav", np.concatenate(parts))


@pytest.fixture(scope="module")
def escalating_wav(tmp_path_factory):
    parts = [_silence(0.5)]
    for i in range(6):
        parts += [_phrase(2.5, 140 * (1 + 0.06 * i), 0.3 + 0.08 * i, 3.5 + 0.5 * i, seed=i), _silence(0.3)]
    return _write(tmp_path_factory, "escalating.wav", np.concatenate(parts))


def test_tone_features_are_attached_to_prosody(steady_wav):
    features = extract_prosody_features(steady_wav)
    assert features["available"]
    tone = features["tone"]
    assert tone["available"] is True
    assert tone["window_count"] >= 4
    assert tone["trajectory"] in {"steady", "escalating", "collapsing", "volatile"}
    assert len(tone["timeline"]) == tone["window_count"]
    assert {"t", "energy", "rate", "arousal"} <= set(tone["timeline"][0])


def test_escalating_voice_scores_higher_than_steady(steady_wav, escalating_wav):
    steady = extract_prosody_features(steady_wav)["tone"]
    escalating = extract_prosody_features(escalating_wav)["tone"]

    assert escalating["trajectory"] == "escalating"
    assert escalating["f0_rise_semitones"] > steady["f0_rise_semitones"] + 2
    assert escalating["energy_rise_ratio"] > steady["energy_rise_ratio"] + 0.3

    steady_score = calculate_tone_indicator(steady)
    escalating_score = calculate_tone_indicator(escalating)
    assert escalating_score["sub_scores"]["arousal"] > 80
    assert escalating_score["sub_scores"]["trajectory"] > steady_score["sub_scores"]["trajectory"]
    assert any("arousal" in c.lower() for c in escalating_score["cues"])
    assert escalating_score["label"] in {"escalating", "agitated", "unstable"}


def test_tone_indicator_handles_unavailable():
    result = calculate_tone_indicator({"available": False})
    assert result["available"] is False and result["indicator"] == 0.0
    assert calculate_tone_indicator(None)["available"] is False


def test_tone_features_too_short():
    rms = np.ones(200) * 0.1
    speech = np.ones(200, dtype=bool)
    assert extract_tone_features(rms, speech)["available"] is False


def test_tone_flat_and_unstable_scoring():
    flat = {
        "available": True, "f0_rise_semitones": 0, "energy_rise_ratio": 0, "rate_rise_ratio": 0,
        "fade_ratio": 1.0, "energy_cv": 0.05, "rate_cv": 0.05, "f0_semitone_range": 1.5, "hnr_db": 20,
        "spectral_flatness": 0.05, "trail_off_ratio": 0, "burst_ratio": 0, "arousal_slope": 0, "arousal_range": 0.05,
        "trajectory": "steady",
    }
    unstable = dict(flat, energy_cv=0.9, rate_cv=0.6, trail_off_ratio=0.6, fade_ratio=0.5, f0_semitone_range=8, arousal_range=1.0, trajectory="volatile")
    flat_result = calculate_tone_indicator(flat)
    unstable_result = calculate_tone_indicator(unstable)
    assert flat_result["sub_scores"]["flatness"] >= 90
    assert flat_result["label"] == "flat / withdrawn"
    assert unstable_result["sub_scores"]["instability"] >= 90
    assert any("trailed off" in c for c in unstable_result["cues"])
    assert any("faded" in c for c in unstable_result["cues"])
