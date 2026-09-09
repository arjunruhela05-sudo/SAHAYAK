from services.fusion_engine import (
    calculate_acoustic_indicator,
    fuse_multimodal_signals,
)


def test_acoustic_indicator_without_features():
    result = calculate_acoustic_indicator(
        {
            "available": False,
        }
    )

    assert result == 0.0


def test_acoustic_indicator_returns_valid_range():
    result = calculate_acoustic_indicator(
        {
            "available": True,
            "rms": 0.08,
            "zero_crossing_rate": 0.08,
            "pitch_variability": 70.0,
        }
    )

    assert 0 <= result <= 100


def test_text_only_fusion():
    result = fuse_multimodal_signals(
        text_svi=60.0,
        acoustic_features={
            "available": False,
        },
    )

    assert result["fused_svi"] == 60.0
    assert result["text_svi"] == 60.0
    assert result["acoustic_available"] is False
    assert result["fusion_method"] == "text_only"


def test_multimodal_fusion():
    result = fuse_multimodal_signals(
        text_svi=60.0,
        acoustic_features={
            "available": True,
            "rms": 0.08,
            "zero_crossing_rate": 0.08,
            "pitch_variability": 70.0,
        },
    )

    assert result["acoustic_available"] is True
    assert result["fused_svi"] >= 60.0
    assert result["fused_svi"] <= 70.0


def test_acoustic_signal_cannot_raise_score_by_more_than_ten():
    result = fuse_multimodal_signals(
        text_svi=40.0,
        acoustic_features={
            "available": True,
            "rms": 0.20,
            "zero_crossing_rate": 0.20,
            "pitch_variability": 150.0,
        },
    )

    assert result["fused_svi"] <= 50.0