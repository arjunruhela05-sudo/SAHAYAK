"""
Multimodal assessment service
=============================

Shared pipeline used by both the voice endpoint (/api/assess-audio) and
the video endpoint (/api/assess-video):

    transcript ──► text engine (primary SVI)
    audio      ──► acoustic stats + prosody engine
    transcript ──► disfluency engine
    behaviour  ──► behaviour engine (features computed in the browser)
                        │
                        ▼
                  fusion engine ──► final SVI / risk / explanation
                        │
                        ▼
                  case persistence

The API layers stay thin: they validate input, run transcription /
feature extraction (which tests patch), and hand everything here.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from models.assessment import AssessmentResponse, ModalityBreakdown

from services.assessment_service import assess_text
from services.behavior_engine import calculate_behavior_indicator
from services.case_service import create_case, get_case
from services.disfluency_engine import (
    calculate_disfluency_indicator,
    extract_disfluency_features,
)
from services.fusion_engine import fuse_multimodal_signals
from services.prosody_engine import calculate_prosody_indicator
from services.scoring_engine import classify_risk
from services.tone_engine import calculate_tone_indicator


# =========================================================
# EXPLANATION HELPERS
# =========================================================

def _voice_explanation(fusion: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    prosody = fusion.get("prosody", {})
    disfluency = fusion.get("disfluency", {})
    tone = fusion.get("tone", {})

    if (
        fusion.get("acoustic_available")
        or prosody.get("available")
        or disfluency.get("available")
        or tone.get("available")
    ):
        tone_note = f", tone: {tone['label']}" if tone.get("available") and tone.get("label") else ""
        lines.append(
            "Voice delivery (pitch, pauses, breathing, tremor, pace, tone, "
            "fumbling) was analysed over the whole recording as a "
            f"supplementary indicator (voice indicator "
            f"{fusion.get('voice_indicator', 0):.0f}/100, "
            f"adjustment +{fusion.get('voice_adjustment', 0):.1f}{tone_note})."
        )
    else:
        lines.append(
            "Acoustic features were unavailable; the assessment relied on the "
            "transcribed narrative."
        )

    for cue in prosody.get("cues", [])[:4]:
        lines.append(f"Voice: {cue}")
    for cue in tone.get("cues", [])[:4]:
        lines.append(f"Tone: {cue}")
    for cue in disfluency.get("cues", [])[:4]:
        lines.append(f"Speech pattern: {cue}")
    return lines


def _behavior_explanation(fusion: Dict[str, Any]) -> List[str]:
    lines: List[str] = []
    behavior = fusion.get("behavior", {})
    if not behavior.get("available"):
        return lines

    reliability = behavior.get("reliability")
    reliability_note = (
        f", capture reliability {reliability * 100:.0f}%" if reliability is not None else ""
    )
    lines.append(
        "Body-language cues from the video (blinking, eye contact, "
        "self-soothing gestures, muscle tension, posture, swallowing, "
        "expression) were analysed as a supplementary indicator "
        f"(behaviour indicator {fusion.get('behavior_indicator', 0):.0f}/100, "
        f"adjustment +{fusion.get('behavior_adjustment', 0):.1f}{reliability_note})."
    )
    for cue in behavior.get("cues", [])[:6]:
        lines.append(f"Body language: {cue}")
    return lines


# =========================================================
# MAIN PIPELINE
# =========================================================

def build_multimodal_assessment(
    *,
    case_id: str,
    transcript: str,
    language: str,
    acoustic_features: Dict[str, Any],
    prosody_features: Optional[Dict[str, Any]] = None,
    transcription_segments: Optional[List[Dict[str, Any]]] = None,
    behavior_payload: Optional[Dict[str, Any]] = None,
    capture_mode: str = "voice",
    persist: bool = True,
) -> AssessmentResponse:
    """
    Run text assessment, all supplementary engines, fusion and (optionally)
    persistence.  Returns the final AssessmentResponse.
    """

    # -----------------------------------------------------
    # 1. Primary text assessment (same engine as typed input)
    # -----------------------------------------------------
    text_assessment = assess_text(
        case_id=case_id,
        narrative=transcript,
        language=language,
    )

    # -----------------------------------------------------
    # 2. Supplementary engines
    # -----------------------------------------------------
    prosody_result = (
        calculate_prosody_indicator(prosody_features)
        if prosody_features is not None
        else None
    )

    tone_result = (
        calculate_tone_indicator((prosody_features or {}).get("tone"))
        if prosody_features is not None
        else None
    )

    disfluency_features = extract_disfluency_features(
        transcript,
        segments=transcription_segments,
    )
    disfluency_result = calculate_disfluency_indicator(disfluency_features)

    behavior_result = (
        calculate_behavior_indicator(behavior_payload)
        if behavior_payload is not None
        else None
    )

    # -----------------------------------------------------
    # 3. Fusion
    # -----------------------------------------------------
    fusion = fuse_multimodal_signals(
        text_svi=text_assessment.svi_score,
        acoustic_features=acoustic_features or {"available": False},
        prosody_result=prosody_result,
        disfluency_result=disfluency_result,
        behavior_result=behavior_result,
        tone_result=tone_result,
    )

    final_svi = float(fusion["fused_svi"])
    final_risk = classify_risk(final_svi)

    # Risk can only be raised by fusion, never lowered below the text
    # classification.
    order = ["LOW", "MODERATE", "HIGH", "CRITICAL"]
    if order.index(final_risk) < order.index(text_assessment.risk_level):
        final_risk = text_assessment.risk_level

    # -----------------------------------------------------
    # 4. Explanation / recommendations
    # -----------------------------------------------------
    explanation = list(text_assessment.explanation)
    explanation.extend(_voice_explanation(fusion))
    explanation.extend(_behavior_explanation(fusion))

    recommendations = list(text_assessment.recommendations)

    if fusion.get("incongruence_flag"):
        explanation.append(
            "Note: the words used were relatively calm but the voice and/or "
            "body language showed clear signs of distress. This mismatch is "
            "itself a signal and has been flagged for the responder."
        )
        recommendations.insert(
            0,
            "Non-verbal distress exceeded the narrative content; conduct a "
            "gentle follow-up conversation in a private setting.",
        )

    behavior_block = fusion.get("behavior", {})
    if behavior_block.get("available") and behavior_block.get("reliability", 1.0) < 0.6:
        explanation.append(
            "Video capture quality was limited; behavioural cues were "
            "down-weighted accordingly."
        )

    # -----------------------------------------------------
    # 5. Confidence
    # -----------------------------------------------------
    confidence = round(
        min(0.97, text_assessment.confidence + float(fusion.get("confidence_bonus", 0.0))),
        2,
    )

    # -----------------------------------------------------
    # 6. Response
    # -----------------------------------------------------
    modalities = ModalityBreakdown(
        text_svi=fusion["text_svi"],
        fused_svi=fusion["fused_svi"],
        fusion_method=fusion["fusion_method"],
        voice_indicator=fusion.get("voice_indicator", 0.0),
        behavior_indicator=fusion.get("behavior_indicator", 0.0),
        voice_adjustment=fusion.get("voice_adjustment", 0.0),
        behavior_adjustment=fusion.get("behavior_adjustment", 0.0),
        acoustic=fusion.get("acoustic", {}),
        prosody=fusion.get("prosody", {}),
        disfluency=fusion.get("disfluency", {}),
        tone=fusion.get("tone", {}),
        behavior=fusion.get("behavior", {}),
        incongruence_flag=bool(fusion.get("incongruence_flag", False)),
        modalities_used=list(fusion.get("modalities_used", ["text"])),
    )

    voice_analysis = {
        "acoustic": acoustic_features or {"available": False},
        "prosody": prosody_features or {"available": False},
        "disfluency": disfluency_features,
    }

    behavior_analysis = None
    if behavior_payload is not None:
        behavior_analysis = {
            "features": behavior_payload,
            "result": behavior_result,
        }

    final_assessment = AssessmentResponse(
        case_id=case_id,
        svi_score=final_svi,
        risk_level=final_risk,
        confidence=confidence,
        signals=text_assessment.signals,
        vulnerability_profile=text_assessment.vulnerability_profile,
        explanation=explanation,
        evidence=text_assessment.evidence,
        immediate_threat=text_assessment.immediate_threat,
        recommendations=recommendations,
        human_review_required=True,
        language=language,
        transcript=transcript,
        narrative_context=text_assessment.narrative_context,
        modalities=modalities,
        voice_analysis=voice_analysis,
        behavior_analysis=behavior_analysis,
    )

    # -----------------------------------------------------
    # 7. Persistence
    # -----------------------------------------------------
    if persist:
        create_case(
            case_id=final_assessment.case_id,
            svi_score=final_assessment.svi_score,
            risk_level=final_assessment.risk_level,
            human_review_required=final_assessment.human_review_required,
            language=final_assessment.language,
            signals=final_assessment.signals.model_dump(),
            vulnerability_profile=final_assessment.vulnerability_profile.model_dump(),
            explanation=final_assessment.explanation,
            evidence=[item.model_dump() for item in final_assessment.evidence],
            recommendations=final_assessment.recommendations,
            capture_mode=capture_mode,
            modalities=modalities.model_dump(),
            voice_analysis=voice_analysis,
            behavior_analysis=behavior_analysis,
            narrative_context=(
                text_assessment.narrative_context.model_dump()
                if text_assessment.narrative_context
                else None
            ),
            transcript=transcript,
        )

        if get_case(case_id) is None:
            raise HTTPException(
                status_code=500,
                detail="Assessment completed but case persistence failed.",
            )

    return final_assessment
