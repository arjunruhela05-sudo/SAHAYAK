from __future__ import annotations

from typing import Any, Dict, List, Optional


# =========================================================
# ACOUSTIC (basic signal statistics)
# =========================================================

# Acoustic features are supplementary indicators.
# They must NOT independently determine trauma or risk.
ACOUSTIC_WEIGHTS = {
    "rms": 0.30,
    "zero_crossing_rate": 0.20,
    "pitch_variability": 0.50,
}


def normalize_feature(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    """Normalize a numeric feature to a 0-100 range."""

    if maximum <= minimum:
        return 0.0

    normalized = (
        (value - minimum)
        / (maximum - minimum)
    ) * 100

    return round(
        max(0.0, min(100.0, normalized)),
        1,
    )


def calculate_acoustic_indicator(
    acoustic_features: Dict[str, Any],
) -> float:
    """
    Calculate a conservative supplementary acoustic indicator.

    This is NOT a clinical measurement and should never
    independently determine the final risk level.
    """

    if not acoustic_features.get("available"):
        return 0.0

    rms = float(acoustic_features.get("rms", 0.0))
    zcr = float(acoustic_features.get("zero_crossing_rate", 0.0))
    pitch_variability = float(acoustic_features.get("pitch_variability", 0.0))

    # Broad prototype ranges.
    # These are engineering normalization ranges,
    # not clinical thresholds.
    rms_score = normalize_feature(rms, 0.01, 0.20)
    zcr_score = normalize_feature(zcr, 0.01, 0.20)
    pitch_score = normalize_feature(pitch_variability, 10.0, 150.0)

    indicator = (
        rms_score * ACOUSTIC_WEIGHTS["rms"]
        + zcr_score * ACOUSTIC_WEIGHTS["zero_crossing_rate"]
        + pitch_score * ACOUSTIC_WEIGHTS["pitch_variability"]
    )

    return round(max(0.0, min(100.0, indicator)), 1)


# =========================================================
# MULTIMODAL FUSION
# =========================================================

# How the three voice channels combine into ONE voice indicator.
VOICE_CHANNEL_WEIGHTS = {
    "acoustic": 0.15,     # coarse energy / pitch statistics
    "prosody": 0.40,      # pauses, pitch dynamics, breathing, tremor, depth
    "disfluency": 0.25,   # fillers, repetitions, restarts, hedging, timing
    "tone": 0.20,         # arousal, flatness, strain, instability, trajectory
}

# Text is primary.  Supplementary channels only nudge the score upward,
# proportionally to how much they exceed the text score, and only
# within hard caps.
VOICE_BLEND = 0.15
VOICE_CAP = 10.0

BEHAVIOR_BLEND = 0.12
BEHAVIOR_CAP = 6.0

TOTAL_CAP = 14.0

# When words are calm but voice/body are clearly not, flag it for the
# responder instead of silently escalating.
INCONGRUENCE_TEXT_MAX = 35.0
INCONGRUENCE_SIGNAL_MIN = 60.0


def _indicator_block(result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Normalise an engine result into the ModalityIndicator shape."""
    if not result or not result.get("available"):
        return {"available": False, "indicator": 0.0, "sub_scores": {}, "cues": []}
    block = {
        "available": True,
        "indicator": round(float(result.get("indicator", 0.0)), 1),
        "sub_scores": {k: round(float(v), 1) for k, v in (result.get("sub_scores") or {}).items()},
        "cues": list(result.get("cues") or []),
    }
    if result.get("reliability") is not None:
        block["reliability"] = float(result["reliability"])
    return block


def combine_voice_channels(
    acoustic_indicator: float,
    acoustic_available: bool,
    prosody: Dict[str, Any],
    disfluency: Dict[str, Any],
    tone: Optional[Dict[str, Any]] = None,
) -> float:
    """Weighted mean of whichever voice channels are available."""
    channels = []
    if acoustic_available:
        channels.append(("acoustic", acoustic_indicator))
    if prosody.get("available"):
        channels.append(("prosody", prosody["indicator"]))
    if disfluency.get("available"):
        channels.append(("disfluency", disfluency["indicator"]))
    if tone and tone.get("available"):
        channels.append(("tone", tone["indicator"]))

    if not channels:
        return 0.0

    total_weight = sum(VOICE_CHANNEL_WEIGHTS[name] for name, _ in channels)
    value = sum(VOICE_CHANNEL_WEIGHTS[name] * score for name, score in channels) / total_weight
    return round(max(0.0, min(100.0, value)), 1)


def fuse_multimodal_signals(
    text_svi: float,
    acoustic_features: Dict[str, Any],
    prosody_result: Optional[Dict[str, Any]] = None,
    disfluency_result: Optional[Dict[str, Any]] = None,
    behavior_result: Optional[Dict[str, Any]] = None,
    tone_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Combine the text assessment with supplementary voice and behaviour
    information.

    Text remains the primary assessment signal.  Voice (acoustic +
    prosody + disfluency) and behaviour (video cues) provide limited
    supplementary context and cannot independently escalate risk.

    Backwards compatible: called with only ``text_svi`` and
    ``acoustic_features`` it behaves exactly like the original
    85 % text / 15 % acoustic fusion.
    """

    text_svi = float(text_svi)

    acoustic_available = bool(acoustic_features.get("available"))
    acoustic_indicator = calculate_acoustic_indicator(acoustic_features)

    prosody = _indicator_block(prosody_result)
    disfluency = _indicator_block(disfluency_result)
    tone = _indicator_block(tone_result)
    if tone_result and tone_result.get("label"):
        tone["label"] = str(tone_result["label"])
    behavior = _indicator_block(behavior_result)

    voice_available = (
        acoustic_available or prosody["available"] or disfluency["available"] or tone["available"]
    )
    behavior_available = behavior["available"]

    modalities_used: List[str] = ["text"]

    # -----------------------------------------------------
    # Nothing supplementary -> text only
    # -----------------------------------------------------
    if not voice_available and not behavior_available:
        return {
            "fused_svi": round(text_svi, 1),
            "text_svi": round(text_svi, 1),
            "acoustic_indicator": 0.0,
            "acoustic_available": False,
            "voice_indicator": 0.0,
            "behavior_indicator": 0.0,
            "voice_adjustment": 0.0,
            "behavior_adjustment": 0.0,
            "fusion_method": "text_only",
            "incongruence_flag": False,
            "modalities_used": modalities_used,
            "confidence_bonus": 0.0,
            "acoustic": _indicator_block(None),
            "prosody": prosody,
            "disfluency": disfluency,
            "tone": tone,
            "behavior": behavior,
        }

    # -----------------------------------------------------
    # Voice channel
    # -----------------------------------------------------
    voice_indicator = combine_voice_channels(
        acoustic_indicator, acoustic_available, prosody, disfluency, tone
    )
    voice_adjustment = 0.0
    if voice_available:
        modalities_used.append("voice")
        voice_adjustment = min(
            max(0.0, voice_indicator - text_svi) * VOICE_BLEND,
            VOICE_CAP,
        )

    # -----------------------------------------------------
    # Behaviour channel (scaled by capture reliability)
    # -----------------------------------------------------
    behavior_indicator = behavior["indicator"] if behavior_available else 0.0
    behavior_adjustment = 0.0
    if behavior_available:
        modalities_used.append("behavior")
        reliability = float(behavior.get("reliability", 1.0) or 1.0)
        behavior_adjustment = min(
            max(0.0, behavior_indicator - text_svi) * BEHAVIOR_BLEND * reliability,
            BEHAVIOR_CAP,
        )

    total_adjustment = min(voice_adjustment + behavior_adjustment, TOTAL_CAP)
    fused_svi = min(text_svi + total_adjustment, 100.0)

    # -----------------------------------------------------
    # Incongruence: calm words, distressed delivery
    # -----------------------------------------------------
    incongruence = text_svi <= INCONGRUENCE_TEXT_MAX and (
        (voice_available and voice_indicator >= INCONGRUENCE_SIGNAL_MIN)
        or (behavior_available and behavior_indicator >= INCONGRUENCE_SIGNAL_MIN)
    )

    # -----------------------------------------------------
    # Method label
    # -----------------------------------------------------
    only_basic_acoustic = (
        acoustic_available
        and not prosody["available"]
        and not disfluency["available"]
        and not tone["available"]
        and not behavior_available
    )
    if only_basic_acoustic:
        fusion_method = "85_text_15_acoustic"
    else:
        fusion_method = "text_primary+" + "+".join(m for m in modalities_used if m != "text")

    # Extra modalities add a little confidence (the service applies it).
    extra_channels = sum(
        1 for block in (prosody, disfluency, tone, behavior) if block["available"]
    ) + (1 if acoustic_available else 0)
    confidence_bonus = round(min(0.08, 0.02 * extra_channels), 2)

    acoustic_block = {
        "available": acoustic_available,
        "indicator": acoustic_indicator if acoustic_available else 0.0,
        "sub_scores": (
            {
                "rms": normalize_feature(float(acoustic_features.get("rms", 0.0)), 0.01, 0.20),
                "zero_crossing_rate": normalize_feature(
                    float(acoustic_features.get("zero_crossing_rate", 0.0)), 0.01, 0.20
                ),
                "pitch_variability": normalize_feature(
                    float(acoustic_features.get("pitch_variability", 0.0)), 10.0, 150.0
                ),
            }
            if acoustic_available
            else {}
        ),
        "cues": [],
    }

    return {
        "fused_svi": round(fused_svi, 1),
        "text_svi": round(text_svi, 1),
        "acoustic_indicator": round(acoustic_indicator, 1),
        "acoustic_available": acoustic_available,
        "voice_indicator": voice_indicator,
        "behavior_indicator": round(behavior_indicator, 1),
        "voice_adjustment": round(voice_adjustment, 1),
        "behavior_adjustment": round(behavior_adjustment, 1),
        "fusion_method": fusion_method,
        "incongruence_flag": bool(incongruence),
        "modalities_used": modalities_used,
        "confidence_bonus": confidence_bonus,
        "acoustic": acoustic_block,
        "prosody": prosody,
        "disfluency": disfluency,
        "tone": tone,
        "behavior": behavior,
    }
