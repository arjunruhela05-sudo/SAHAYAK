from models.assessment import (
    AssessmentResponse,
    NarrativeContext,
    SignalScores,
    VulnerabilityProfile,
    ThreatAssessment,
    EvidenceItem,
)

from services.text_engine import analyze_text, detect_language

from services.scoring_engine import (
    calculate_svi,
    classify_risk,
    build_vulnerability_profile,
    calculate_confidence,
    extract_threat_context,
    narrative_adjustment,
)

from services.recommendation_engine import (
    generate_recommendations,
)


# =========================================================
# SIGNAL LABELS
# =========================================================

SIGNAL_LABELS = {
    "fear": "Fear",
    "immediate_threat": "Immediate Threat",
    "distress": "Distress",
    "isolation": "Isolation",
    "intimidation": "Intimidation",
    "self_harm": "Self-harm",
}


# =========================================================
# EVIDENCE
# =========================================================

def build_evidence(
    analysis: dict,
) -> list[EvidenceItem]:

    evidence = []

    for signal, data in analysis.items():

        matches = data.get("matches", [])

        for phrase in matches:

            evidence.append(
                EvidenceItem(
                    text=phrase,
                    signal=SIGNAL_LABELS.get(
                        signal,
                        signal,
                    ),
                )
            )

    return evidence


# =========================================================
# EXPLANATION
# =========================================================

def build_explanation(
    signals: dict,
    risk_level: str,
    threat_detected: bool,
) -> list[str]:

    explanation = []

    explanation.append(
        f"The text assessment produced a "
        f"{risk_level} risk classification based "
        f"on detected vulnerability indicators."
    )

    for signal, score in signals.items():

        if score >= 50:

            label = SIGNAL_LABELS.get(
                signal,
                signal,
            )

            explanation.append(
                f"{label} indicators were detected "
                f"at an elevated level ({score:.0f}/100)."
            )

    if threat_detected:

        explanation.append(
            "Potential immediate safety indicators "
            "were detected and require human review."
        )

    if signals.get("self_harm", 0) >= 25:

        explanation.append(
            "Potential self-harm related language "
            "was detected and requires appropriate "
            "human-led safety assessment."
        )

    return explanation


# =========================================================
# NARRATIVE CONTEXT EXPLANATION
# =========================================================

def build_context_explanation(
    narrative_context: dict | None,
    adjustment: float,
) -> list[str]:
    """Human readable lines for the whole-passage reading."""

    if not narrative_context:
        return []

    lines: list[str] = []
    indicator = float(narrative_context.get("indicator", 0.0) or 0.0)
    discourse = narrative_context.get("discourse") or {}
    trajectory = discourse.get("trajectory")

    if narrative_context.get("available") or indicator > 0:
        summary = (
            "The narrative was also read as a whole (cross-sentence "
            f"context and discourse structure); narrative stress index "
            f"{indicator:.0f}/100"
        )
        if trajectory and trajectory != "steady":
            summary += f", trajectory: {trajectory}"
        if adjustment > 0:
            summary += f", SVI adjustment +{adjustment:.1f}"
        lines.append(summary + ".")

    for cue in (narrative_context.get("cues") or [])[:5]:
        lines.append(f"Narrative: {cue}")

    return lines


# =========================================================
# THREAT ASSESSMENT
# =========================================================

def build_threat_assessment(
    signals: dict,
    analysis: dict,
) -> ThreatAssessment:

    threat_score = signals.get(
        "immediate_threat",
        0,
    )

    detected = threat_score >= 25

    indicators = []

    if detected:

        indicators = (
            analysis
            .get("immediate_threat", {})
            .get("matches", [])
        )

    if threat_score >= 90:
        severity = "CRITICAL"

    elif threat_score >= 75:
        severity = "HIGH"

    elif threat_score >= 50:
        severity = "MODERATE"

    elif threat_score >= 25:
        severity = "LOW"

    else:
        severity = "NONE"

    return ThreatAssessment(
        detected=detected,
        severity=severity,
        indicators=indicators,
    )


# =========================================================
# MAIN ASSESSMENT SERVICE
# =========================================================

def assess_text(
    case_id: str,
    narrative: str,
    language: str = "en",
) -> AssessmentResponse:

    # -----------------------------------------------------
    # 1. Analyze text
    # -----------------------------------------------------

    analysis, narrative_context = analyze_text(
        narrative,
        return_context=True,
    )

    detected_language = detect_language(narrative)

    # -----------------------------------------------------
    # 2. Extract signal scores
    # -----------------------------------------------------

    signals = {
        signal: data["score"]
        for signal, data in analysis.items()
    }

    signal_scores = SignalScores(
        **signals
    )

    # -----------------------------------------------------
    # 3. Context-aware safety calibration
    # -----------------------------------------------------

    threat_context = extract_threat_context(narrative)

    # -----------------------------------------------------
    # 4. Calculate SVI
    # -----------------------------------------------------

    svi_score = calculate_svi(
        signals,
        threat_context,
    )

    # Whole-passage reading (escalation, helplessness, present-tense
    # danger, fragmentation ...) may nudge the SVI upward within a cap.
    context_indicator = (
        float(narrative_context.get("indicator", 0.0) or 0.0)
        if narrative_context
        else 0.0
    )
    context_adjustment = narrative_adjustment(svi_score, context_indicator)
    svi_score = round(min(svi_score + context_adjustment, 100.0), 1)

    # -----------------------------------------------------
    # 5. Classify risk
    # -----------------------------------------------------

    risk_level = classify_risk(
        svi_score,
        threat_context,
    )

    # -----------------------------------------------------
    # 5. Evidence
    # -----------------------------------------------------

    evidence = build_evidence(
        analysis
    )

    # -----------------------------------------------------
    # 6. Threat assessment
    # -----------------------------------------------------

    threat = build_threat_assessment(
        signals,
        analysis,
    )

    # -----------------------------------------------------
    # 7. Vulnerability profile
    # -----------------------------------------------------

    vulnerability_profile = (
        build_vulnerability_profile(
            signals
        )
    )

    # -----------------------------------------------------
    # 8. Confidence
    # -----------------------------------------------------

    confidence = calculate_confidence(
        signals,
        len(evidence),
    )

    # -----------------------------------------------------
    # 9. Explanation
    # -----------------------------------------------------

    explanation = build_explanation(
        signals,
        risk_level,
        threat.detected,
    )

    context_lines = build_context_explanation(
        narrative_context,
        context_adjustment,
    )
    explanation.extend(context_lines)

    # -----------------------------------------------------
    # 10. Recommendations
    # -----------------------------------------------------

    recommendations = (
        generate_recommendations(
            signals,
            risk_level,
            threat.detected,
        )
    )

    # -----------------------------------------------------
    # 11. Human review
    # -----------------------------------------------------

    human_review_required = True

    # -----------------------------------------------------
    # 12. Final response
    # -----------------------------------------------------

    return AssessmentResponse(

        case_id=case_id,

        svi_score=svi_score,

        risk_level=risk_level,

        confidence=confidence,

        signals=signal_scores,

        vulnerability_profile=(
            VulnerabilityProfile(
                **vulnerability_profile
            )
        ),

        explanation=explanation,

        evidence=evidence,

        immediate_threat=threat,

        recommendations=recommendations,

        human_review_required=(
            human_review_required
        ),

        language=detected_language,

        narrative_context=NarrativeContext(
            available=bool(narrative_context.get("available", False)),
            engine=str(narrative_context.get("engine", "none")),
            indicator=float(narrative_context.get("indicator", 0.0) or 0.0),
            adjustment=context_adjustment,
            sub_scores={
                k: float(v)
                for k, v in (narrative_context.get("sub_scores") or {}).items()
            },
            cues=list(narrative_context.get("cues") or []),
            signals=dict(narrative_context.get("signals") or {}),
            discourse=dict(narrative_context.get("discourse") or {}),
        ) if narrative_context else None,
    )