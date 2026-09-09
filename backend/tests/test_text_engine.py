from services.text_engine import (
    normalize_text,
    analyze_text,
)


def test_normalize_text():
    text = "  I   AM   SCARED.  "

    result = normalize_text(text)

    assert result == "i am scared."


def test_fear_detection():
    result = analyze_text(
        "I am scared to go home."
    )

    assert result["fear"]["score"] > 0
    assert result["fear"]["match_count"] > 0


def test_isolation_detection():
    result = analyze_text(
        "I have nobody to help me."
    )

    assert result["isolation"]["score"] > 0


def test_distress_detection():
    result = analyze_text(
        "I feel completely overwhelmed."
    )

    assert result["distress"]["score"] > 0


def test_intimidation_detection():
    result = analyze_text(
        "He keeps threatening me."
    )

    assert result["intimidation"]["score"] > 0


def test_immediate_threat_detection():
    result = analyze_text(
        "He threatened to hurt me."
    )

    assert result["immediate_threat"]["score"] > 0


def test_self_harm_detection():
    result = analyze_text(
        "I want to hurt myself."
    )

    assert result["self_harm"]["score"] > 0


def test_negated_fear():
    result = analyze_text(
        "I am not afraid."
    )

    assert result["fear"]["score"] == 0


def test_no_signal_text():
    result = analyze_text(
        "I need information about my case."
    )

    for signal in result.values():
        assert signal["score"] == 0

def test_language_detection_english():
    from services.text_engine import detect_language

    assert detect_language("I am afraid and I do not feel safe.") == "en"


def test_language_detection_hindi_script():
    from services.text_engine import detect_language

    assert detect_language("मुझे बहुत डर लग रहा है।") == "hi"


def test_language_detection_hinglish():
    from services.text_engine import detect_language

    assert detect_language("Mujhe bahut darr lag raha hai aur ghar jaana hai.") == "hinglish"


def test_threat_paraphrase_baseline():
    result = analyze_text(
        "They are giving me threat to kill me and my whole family."
    )

    # This sentence is also semantically suitable for the multilingual model.
    # The baseline assertion guarantees a useful result even before the model
    # is downloaded in a fresh development environment.
    assert result["immediate_threat"]["score"] > 0
