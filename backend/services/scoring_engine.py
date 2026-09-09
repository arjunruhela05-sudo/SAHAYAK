from typing import Dict, Iterable, Tuple
import re


# Signal weights remain transparent and interpretable for the baseline SVI.
SIGNAL_WEIGHTS = {
    "fear": 0.18,
    "immediate_threat": 0.25,
    "distress": 0.18,
    "isolation": 0.12,
    "intimidation": 0.17,
    "self_harm": 0.10,
}


# High-stakes context rules. These are not the primary NLP detector; they
# provide a safety-sensitive calibration layer when language expresses a
# concrete threat event (intent + target + time/context).
_LETHAL_TERMS = (
    r"kill", r"murder", r"death", r"die", r"dead",
    r"jaan\s*se\s*maar", r"maar\s*denge", r"ma[a]?r\s*denge",
    r"jaan\s*leni", r"jaan\s*le\s*lenge",
    r"जान से मार", r"जान से मारने", r"मार डाल", r"मार दूंगा",
)
_THREAT_EVENT_TERMS = (
    r"threat", r"threaten", r"threatened", r"warning", r"warned",
    r"said", r"told", r"promised", r"will", r"going\s+to",
    r"dhamki", r"dhamka", r"dara?\s*raha", r"maar\s*dega",
    r"धमकी", r"धमकाया", r"मारने की धमकी", r"जान से मारने की धमकी",
)
_NEAR_TERM_TERMS = (
    r"today", r"tonight", r"tomorrow", r"now", r"right\s+now",
    r"abhi", r"aaj", r"aaj\s+raat", r"kal", r"just\s+now",
    r"soon", r"shortly", r"in\s+the\s+next",
    r"आज", r"आज रात", r"कल", r"अभी", r"अभी तुरंत", r"जल्द",
)
_TARGET_TERMS = (
    r"me", r"myself", r"my\s+family", r"my\s+children", r"my\s+child",
    r"my\s+wife", r"my\s+husband", r"my\s+parents", r"my\s+mother",
    r"my\s+father", r"us", r"family", r"bachche", r"parivaar", r"mujhe",
    r"मुझे", r"मेरे परिवार", r"मेरे बच्चे", r"मेरे माता-पिता", r"मेरे पति",
    r"मेरी पत्नी", r"हम", r"परिवार",
)

_THREAT_NEGATION_PATTERNS = (
    r"\bnot\s+(?:being\s+)?threatened\b",
    r"\bdid\s+not\s+threaten\b",
    r"\bdo\s+not\s+threaten\b",
    r"\bdon['’]?t\s+threaten\b",
    r"\bno\s+(?:death\s+)?threat\b",
    r"\bnot\s+going\s+to\s+kill\b",
    r"\bwill\s+not\s+kill\b",
    r"\bwould\s+not\s+kill\b",
    r"\bnot\s+kill(?:ed)?\b",
    r"\bkoi\s+dhamki\s+nahi\b",
    r"\bkoi\s+khatra\s+nahi\b",
    r"\bdhamki\s+nahi\b",
    r"धमकी नहीं", r"धमकी नहीं दी", r"जान से मारने की धमकी नहीं",
    r"मारने की धमकी नहीं", r"कोई धमकी नहीं", r"कोई खतरा नहीं",
)


def _contains_any(text: str, patterns: Iterable[str]) -> bool:
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def extract_threat_context(text: str) -> Dict[str, object]:
    """Extract safety-relevant threat context without replacing semantic NLP.

    Returns transparent context flags and a calibrated threat score. The rules
    intentionally require a relationship between threat language and a lethal
    or serious-harm concept, reducing false positives from isolated words such
    as ``kill`` in unrelated narratives.
    """
    t = re.sub(r"\s+", " ", text.lower().replace("’", "'")).strip()

    lethal = _contains_any(t, _LETHAL_TERMS)
    threat_event = _contains_any(t, _THREAT_EVENT_TERMS)
    near_term = _contains_any(t, _NEAR_TERM_TERMS)
    target = _contains_any(t, _TARGET_TERMS)
    threat_negated = _contains_any(t, _THREAT_NEGATION_PATTERNS)

    # Explicit self-harm statements should not be interpreted as threats from
    # another person by this layer.
    self_harm_context = bool(re.search(
        r"\b(i|i'm|i am|mujhe|main|mai)\b.{0,35}\b(kill myself|hurt myself|harm myself|die|marna|marne)\b",
        t,
    ))

    direct_lethal = (
        lethal
        and threat_event
        and target
        and not self_harm_context
        and not threat_negated
    )
    near_term_lethal = direct_lethal and near_term

    if near_term_lethal:
        score = 96.0
        severity = "CRITICAL"
    elif direct_lethal:
        score = 92.0
        severity = "CRITICAL"
    elif lethal and threat_event and not self_harm_context and not threat_negated:
        score = 82.0
        severity = "HIGH"
    else:
        score = 0.0
        severity = "NONE"

    return {
        "lethal": lethal,
        "threat_event": threat_event,
        "near_term": near_term,
        "target": target,
        "threat_negated": threat_negated,
        "direct_lethal": direct_lethal,
        "near_term_lethal": near_term_lethal,
        "score": score,
        "severity": severity,
    }


def calculate_svi(signals: Dict[str, float], threat_context: Dict[str, object] | None = None) -> float:
    """Calculate the 0-100 Stress & Vulnerability Index.

    The weighted score is the baseline. Safety-sensitive context can impose a
    transparent floor so a severe immediate threat cannot be diluted by
    unrelated zero-valued signals.
    """
    weighted_score = sum(
        float(signals.get(signal, 0)) * weight
        for signal, weight in SIGNAL_WEIGHTS.items()
    )

    svi = min(max(weighted_score, 0), 100)

    if threat_context:
        context_score = float(threat_context.get("score", 0) or 0)
        if context_score >= 96:
            svi = max(svi, 96.0)
        elif context_score >= 92:
            svi = max(svi, 92.0)
        elif context_score >= 82:
            svi = max(svi, 82.0)

    return round(min(max(svi, 0), 100), 1)


# The narrative-context layer (how the story is told: escalation,
# helplessness, present-tense danger, fragmentation ...) can nudge the
# SVI upward within a hard cap, in the same spirit as voice / behaviour.
NARRATIVE_BLEND = 0.10
NARRATIVE_CAP = 6.0


def narrative_adjustment(svi_score: float, narrative_indicator: float | None) -> float:
    """Capped upward nudge from the narrative stress index (0-100)."""
    if narrative_indicator is None:
        return 0.0
    excess = max(0.0, float(narrative_indicator) - float(svi_score))
    return round(min(excess * NARRATIVE_BLEND, NARRATIVE_CAP), 1)


def classify_risk(svi_score: float, threat_context: Dict[str, object] | None = None) -> str:
    """Convert SVI and safety context into transparent four-level risk."""
    if threat_context:
        context_score = float(threat_context.get("score", 0) or 0)
        if context_score >= 92:
            return "CRITICAL"
        if context_score >= 82:
            return "HIGH"

    if svi_score >= 75:
        return "CRITICAL"
    if svi_score >= 50:
        return "HIGH"
    if svi_score >= 25:
        return "MODERATE"
    return "LOW"


def severity_from_score(score: float) -> str:
    if score >= 75:
        return "HIGH"
    if score >= 50:
        return "MODERATE"
    if score >= 25:
        return "LOW"
    return "NOT_DETECTED"


def build_vulnerability_profile(signals: Dict[str, float]) -> Dict[str, str]:
    return {signal: severity_from_score(score) for signal, score in signals.items()}


def calculate_confidence(signals: Dict[str, float], evidence_count: int) -> float:
    active_signals = sum(1 for score in signals.values() if score > 0)
    if active_signals == 0:
        return 0.50
    confidence = 0.55 + min(active_signals * 0.07, 0.28) + min(evidence_count * 0.03, 0.12)
    return round(min(confidence, 0.95), 2)
