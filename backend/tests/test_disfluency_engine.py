from services.disfluency_engine import (
    calculate_disfluency_indicator,
    extract_disfluency_features,
)


FLUENT = (
    "Yesterday evening my neighbour came to my house and returned the book "
    "he had borrowed. We spoke for ten minutes about the upcoming festival "
    "and then he left. Nothing unusual happened and I felt fine afterwards."
)

FUMBLING = (
    "Um, I... I don't know how to, uh, say this. He came- no wait, they came "
    "to my house last night and, um, I think maybe he said he will... "
    "I I I was so scared, matlab, pata nahi kya karu. W-w-woh bola ki he "
    "will kill me if I tell anyone and..."
)

HINDI = (
    "मुझे... मुझे पता नहीं, मतलब, वो वो आदमी रोज़ आता है और, अं, शायद वो "
    "मुझे मार देगा, मैं समझ नहीं पा रही हूँ कि..."
)


def test_empty_transcript():
    features = extract_disfluency_features("")
    assert features["available"] is False
    result = calculate_disfluency_indicator(features)
    assert result["indicator"] == 0.0


def test_fluent_text_scores_low():
    features = extract_disfluency_features(FLUENT)
    result = calculate_disfluency_indicator(features)
    assert features["fillers"]["count"] == 0
    assert features["repetitions"]["count"] == 0
    assert result["indicator"] < 10


def test_fumbling_text_detects_everything():
    features = extract_disfluency_features(FUMBLING)
    result = calculate_disfluency_indicator(features)

    assert features["fillers"]["count"] >= 3
    assert "um" in features["fillers"]["examples"]
    assert features["repetitions"]["count"] >= 2
    assert "W-w-woh" in features["repetitions"]["stutters"]
    assert features["restarts"]["count"] >= 1
    assert features["hedging"]["count"] >= 3
    assert features["fragments"]["trailing_count"] >= 2

    assert result["indicator"] > 40
    assert any("filler" in cue.lower() for cue in result["cues"])
    assert any("repeated" in cue.lower() for cue in result["cues"])


def test_hindi_devanagari_support():
    features = extract_disfluency_features(HINDI)
    result = calculate_disfluency_indicator(features)
    assert features["fillers"]["count"] >= 2
    assert features["hedging"]["count"] >= 2
    assert result["indicator"] > 30


def test_segment_timing_hesitations():
    segments = [
        {"start": 0.0, "end": 3.0, "text": "I do not know", "avg_logprob": -0.3},
        {"start": 5.0, "end": 8.0, "text": "what to say", "avg_logprob": -0.4},
        {"start": 10.5, "end": 12.0, "text": "he hit me", "avg_logprob": -1.4},
    ]
    features = extract_disfluency_features("I do not know what to say he hit me", segments)
    timing = features["timing"]
    assert timing["available"] is True
    assert timing["hesitation_gap_count"] == 2
    assert timing["max_gap_sec"] == 2.5
    assert timing["low_confidence_ratio"] > 0

    result = calculate_disfluency_indicator(features)
    assert result["sub_scores"]["timing"] > 0
    assert any("hesitation" in cue.lower() for cue in result["cues"])


def test_short_statements_are_damped():
    features = extract_disfluency_features("um uh um")
    result = calculate_disfluency_indicator(features)
    assert result["indicator"] < 40
