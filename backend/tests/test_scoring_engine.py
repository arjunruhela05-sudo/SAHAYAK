from services.scoring_engine import (
    calculate_svi,
    classify_risk,
    severity_from_score,
    build_vulnerability_profile,
)


def test_svi_range():

    signals = {
        "fear": 100,
        "immediate_threat": 100,
        "distress": 100,
        "isolation": 100,
        "intimidation": 100,
        "self_harm": 100,
    }

    svi = calculate_svi(signals)

    assert 0 <= svi <= 100


def test_zero_svi():

    signals = {
        "fear": 0,
        "immediate_threat": 0,
        "distress": 0,
        "isolation": 0,
        "intimidation": 0,
        "self_harm": 0,
    }

    assert calculate_svi(signals) == 0


def test_risk_levels():

    assert classify_risk(0) == "LOW"
    assert classify_risk(25) == "MODERATE"
    assert classify_risk(50) == "HIGH"
    assert classify_risk(75) == "CRITICAL"


def test_signal_severity():

    assert severity_from_score(0) == "NOT_DETECTED"
    assert severity_from_score(40) == "LOW"
    assert severity_from_score(65) == "MODERATE"
    assert severity_from_score(80) == "HIGH"


def test_vulnerability_profile():

    signals = {
        "fear": 80,
        "immediate_threat": 0,
        "distress": 65,
        "isolation": 40,
        "intimidation": 0,
        "self_harm": 0,
    }

    profile = build_vulnerability_profile(
        signals
    )

    assert profile["fear"] == "HIGH"
    assert profile["distress"] == "MODERATE"
    assert profile["isolation"] == "LOW"
    assert profile["self_harm"] == "NOT_DETECTED"

def test_near_term_lethal_threat_gets_critical_safety_floor():
    from services.scoring_engine import extract_threat_context

    context = extract_threat_context("they have said that they will kill me tomorrow")
    assert context["near_term_lethal"] is True
    assert context["score"] == 96.0

    signals = {
        "fear": 0,
        "immediate_threat": 40,
        "distress": 0,
        "isolation": 0,
        "intimidation": 0,
        "self_harm": 0,
    }
    svi = calculate_svi(signals, context)
    assert svi >= 95
    assert classify_risk(svi, context) == "CRITICAL"


def test_non_threat_use_of_kill_does_not_trigger_context_floor():
    from services.scoring_engine import extract_threat_context

    context = extract_threat_context("I watched a movie where the villain killed someone.")
    assert context["score"] == 0.0
    assert context["direct_lethal"] is False


def test_hindi_lethal_threat_gets_critical_safety_floor():
    from services.scoring_engine import extract_threat_context

    text = "उन्होंने मुझे और मेरे परिवार को जान से मारने की धमकी दी है"
    context = extract_threat_context(text)
    assert context["direct_lethal"] is True
    assert context["score"] == 92.0

    signals = {
        "fear": 0,
        "immediate_threat": 90,
        "distress": 0,
        "isolation": 0,
        "intimidation": 65,
        "self_harm": 0,
    }
    assert calculate_svi(signals, context) >= 92
    assert classify_risk(92, context) == "CRITICAL"


def test_negated_english_lethal_threat_does_not_trigger_context_floor():
    from services.scoring_engine import extract_threat_context

    context = extract_threat_context(
        "They did not threaten to kill me and I feel safe."
    )
    assert context["threat_negated"] is True
    assert context["direct_lethal"] is False
    assert context["score"] == 0.0


def test_negated_hindi_lethal_threat_does_not_trigger_context_floor():
    from services.scoring_engine import extract_threat_context

    context = extract_threat_context(
        "उन्होंने मुझे जान से मारने की धमकी नहीं दी और मैं सुरक्षित हूँ।"
    )
    assert context["threat_negated"] is True
    assert context["direct_lethal"] is False
    assert context["score"] == 0.0
