"""
Tests for the whole-passage narrative context engine.

The real multilingual sentence-transformer is replaced by a tiny
deterministic bag-of-words encoder so the cross-sentence window logic,
negation handling, discourse features and score plumbing can be tested
offline.
"""

import math
import re
from unittest.mock import patch

import numpy as np
import pytest

from services import context_engine
from services.context_engine import analyze_narrative_context, discourse_features
from services.semantic_engine import SIGNAL_PROTOTYPES, split_sentences
from services.text_engine import analyze_text


class FakeEncoder:
    """Hashed bag-of-words embedding; similar wording -> similar vectors."""

    DIM = 256

    def encode(self, texts, normalize_embeddings=True, convert_to_numpy=True, show_progress_bar=False):
        out = []
        for text in texts:
            vec = np.zeros(self.DIM, dtype=np.float64)
            for word in re.findall(r"\w+", text.lower()):
                vec[hash(word) % self.DIM] += 1.0
            norm = math.sqrt(float((vec ** 2).sum())) or 1.0
            out.append(vec / norm)
        return np.asarray(out)


@pytest.fixture
def fake_model():
    model = FakeEncoder()
    grouped = {}
    for signal, protos in SIGNAL_PROTOTYPES.items():
        grouped[signal] = [(p, e) for p, e in zip(protos, model.encode(protos))]
    with patch.object(context_engine, "load_semantic_model", return_value=model), \
         patch.object(context_engine, "prototype_embeddings", return_value=grouped), \
         patch.object(context_engine, "SEMANTIC_THRESHOLD", 0.30):
        yield model


def test_windows_cover_two_and_three_sentences():
    sentences = ["a.", "b.", "c.", "d."]
    windows = context_engine._windows(sentences)
    sizes = sorted(e - s for s, e, _ in windows)
    assert sizes == [2, 2, 2, 3, 3]


def test_discourse_features_lexical_only():
    text = ("I cannot do anything about it. He always comes back and nobody will help me. "
            "I'm fine, but he will be here tonight. Right now I am hiding.")
    d = discourse_features(text, split_sentences(text))
    assert d["helplessness_count"] >= 1
    assert d["absolutist_count"] >= 2
    assert d["immediacy_ratio"] > 0.3
    assert d["hedged_safety"] is True
    assert d["first_person_ratio"] > 0.1


def test_hindi_and_hinglish_discourse_markers():
    text = "Mujhe samajh nahi aa raha main kya karun. Koi rasta nahi hai. Woh hamesha aisa karta hai. अभी वह घर पर है।"
    d = discourse_features(text, split_sentences(text))
    assert d["helplessness_count"] >= 1
    assert d["absolutist_count"] >= 1
    assert d["immediacy_ratio"] > 0


def test_context_without_model_is_discourse_only():
    with patch.object(context_engine, "load_semantic_model", side_effect=RuntimeError("no model")):
        result = analyze_narrative_context("There is nothing I can do. Nobody will help me. I'm fine, but he comes back every night.")
    assert result["available"] is False
    assert result["engine"] == "discourse_only"
    assert result["indicator"] > 0
    assert result["signals"] == {}
    assert any("helplessness" in c.lower() for c in result["cues"])


def test_cross_sentence_window_raises_signal(fake_model):
    # Each sentence alone shares little with a prototype; the 2-3 sentence
    # window combines "threatening", "kill", "family", "danger".
    text = ("Someone is threatening. He said he would kill. It is my family and the victim. "
            "There is danger now because another person threatened them.")
    result = analyze_narrative_context(text)
    assert result["available"] is True
    assert result["engine"] == "context"
    assert "immediate_threat" in result["signals"]
    hit = result["signals"]["immediate_threat"]
    assert hit["level"].startswith("window") or hit["level"] == "passage"
    assert hit["score"] >= 40
    assert any("as a whole" in c for c in result["cues"])

    signals = analyze_text(text)
    assert signals["immediate_threat"]["score"] >= hit["score"] or signals["immediate_threat"]["score"] >= 80
    assert "context" in signals["immediate_threat"]["engine"] or signals["immediate_threat"]["score"] >= 80


def test_negated_window_is_skipped(fake_model):
    text = "There is no threat and no danger. Nobody threatened to kill the victim or their family. We are not in danger."
    result = analyze_narrative_context(text)
    assert "immediate_threat" not in result["signals"]


def test_escalation_and_rumination_are_detected(fake_model):
    calm = "The office opens at nine. The forms are on the second floor. Parking is available nearby."
    tense = "The victim is afraid and unsafe. The victim is fearful for their safety. The victim is afraid and unsafe again."
    result = analyze_narrative_context(f"{calm} {tense}")
    d = result["discourse"]
    assert d["trajectory"] in ("escalating", "volatile")
    assert d["peak_position"] is not None and d["peak_position"] >= 0.5
    # the three near-identical fearful sentences count as rumination
    assert d["rumination"] is not None and d["rumination"] > 0
    assert result["sub_scores"]["escalation"] > 0 or result["sub_scores"]["rumination"] > 0


def test_short_or_empty_text_is_safe(fake_model):
    empty = analyze_narrative_context("   ")
    assert empty["available"] is False and empty["indicator"] == 0.0
    short = analyze_narrative_context("Help.")
    assert 0 <= short["indicator"] <= 100
