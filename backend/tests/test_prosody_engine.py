import numpy as np
import pytest
import soundfile as sf

from services.prosody_engine import (
    calculate_prosody_indicator,
    extract_prosody_features,
    scale,
)


SR = 16000


def _phrase(duration, f0=140.0, tremor=0.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(int(duration * SR)) / SR
    phase = 2 * np.pi * f0 * t
    signal = np.sin(phase) + 0.5 * np.sin(2 * phase) + 0.25 * np.sin(3 * phase)
    syllables = 0.5 * (1 + np.sin(2 * np.pi * 4 * t))
    modulation = 1 + tremor * np.sin(2 * np.pi * 6 * t)
    return signal * syllables * modulation * 0.5 + rng.standard_normal(len(t)) * 0.002


def _silence(duration, seed=1):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(int(duration * SR)) * 0.002


def _breath(duration=0.3, seed=2):
    rng = np.random.default_rng(seed)
    return rng.standard_normal(int(duration * SR)) * 0.03


@pytest.fixture(scope="module")
def calm_wav(tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / "calm.wav"
    audio = np.concatenate([
        _silence(0.5), _phrase(2.0), _silence(0.2), _phrase(2.5), _silence(0.5),
    ])
    sf.write(path, audio, SR)
    return str(path)


@pytest.fixture(scope="module")
def stressed_wav(tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / "stressed.wav"
    audio = np.concatenate([
        _silence(0.5),
        _phrase(1.0, f0=220, tremor=0.5), _silence(0.4), _breath(), _silence(1.3),
        _phrase(0.8, f0=225, tremor=0.5), _breath(), _silence(1.5),
        _phrase(1.2, f0=230, tremor=0.5), _breath(), _silence(0.6),
        _phrase(0.5, f0=240, tremor=0.5), _silence(0.5),
    ])
    sf.write(path, audio, SR)
    return str(path)


def test_scale_clamps():
    assert scale(-5, 0, 10) == 0.0
    assert scale(5, 0, 10) == 50.0
    assert scale(50, 0, 10) == 100.0
    assert scale(1, 1, 1) == 0.0


def test_extract_features_on_garbage_is_graceful(tmp_path):
    path = tmp_path / "bad.wav"
    path.write_bytes(b"not-really-audio")
    result = extract_prosody_features(str(path))
    assert result["available"] is False
    assert "error" in result


def test_indicator_without_features():
    result = calculate_prosody_indicator({"available": False})
    assert result["available"] is False
    assert result["indicator"] == 0.0
    assert result["cues"] == []


def test_calm_audio_has_no_long_pauses(calm_wav):
    features = extract_prosody_features(calm_wav)
    assert features["available"] is True
    assert features["pauses"]["long_pause_count"] == 0
    assert features["pitch"]["available"] is True
    assert 120 <= features["pitch"]["f0_mean_hz"] <= 160


def test_stressed_audio_detects_pauses_breathing_and_tremor(stressed_wav):
    features = extract_prosody_features(stressed_wav)
    assert features["available"] is True
    assert features["pauses"]["long_pause_count"] >= 2
    assert features["breathing"]["breath_count"] >= 2
    assert features["tremor"]["tremor_index"] > 0.3
    assert features["pitch"]["f0_mean_hz"] > 200


def test_indicator_separates_calm_from_stressed(calm_wav, stressed_wav):
    calm = calculate_prosody_indicator(extract_prosody_features(calm_wav))
    stressed = calculate_prosody_indicator(extract_prosody_features(stressed_wav))

    assert 0 <= calm["indicator"] <= 100
    assert 0 <= stressed["indicator"] <= 100
    assert stressed["indicator"] > calm["indicator"] + 20
    assert set(stressed["sub_scores"]) == {"pauses", "pitch", "breathing", "tremor", "rate", "depth"}
    assert any("pause" in cue.lower() for cue in stressed["cues"])
    assert any("breath" in cue.lower() for cue in stressed["cues"])
