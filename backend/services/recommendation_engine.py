from typing import Dict, List


def generate_recommendations(
    signals: Dict[str, float],
    risk_level: str,
    immediate_threat_detected: bool,
) -> List[str]:

    recommendations = []

    # Immediate safety concern.
    if immediate_threat_detected:
        recommendations.append(
            "Prioritize immediate human safety review."
        )

        recommendations.append(
            "Follow the authorized responder's "
            "established escalation protocol."
        )

    # Self-harm indicator.
    if signals.get("self_harm", 0) >= 25:
        recommendations.append(
            "Conduct an appropriate human-led safety "
            "assessment for potential self-harm concerns."
        )

    # High/critical overall risk.
    if risk_level in {"HIGH", "CRITICAL"}:
        recommendations.append(
            "Prioritize the case for human review."
        )

    # Isolation.
    if signals.get("isolation", 0) >= 50:
        recommendations.append(
            "Assess available family, community, or "
            "support-network options."
        )

    # Intimidation.
    if signals.get("intimidation", 0) >= 50:
        recommendations.append(
            "Review potential coercion or intimidation "
            "indicators with an authorized responder."
        )

    # Distress.
    if signals.get("distress", 0) >= 50:
        recommendations.append(
            "Consider appropriate psychosocial support "
            "or referral based on human assessment."
        )

    # Always provide a human-review recommendation
    # for the prototype.
    if not recommendations:
        recommendations.append(
            "Complete standard human review of the assessment."
        )

    return list(dict.fromkeys(recommendations))