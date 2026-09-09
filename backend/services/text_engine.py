"""SAHAYAK text analysis engine.

The engine uses a multilingual semantic model when available and retains a
small deterministic baseline as a safety-net for local development/tests.
The semantic layer is the primary detector; keyword matches are evidence
signals, not a requirement for detection.
"""

from __future__ import annotations

import re
from typing import Dict, List

from services.context_engine import analyze_narrative_context
from services.semantic_engine import (
    detect_language,
    semantic_detect,
)
from services.scoring_engine import extract_threat_context


SIGNAL_PATTERNS = {
    "fear": [
        "i am scared", "i'm scared", "i am afraid", "i'm afraid",
        "very afraid", "terrified", "frightened", "i fear",
        "i feel unsafe", "i don't feel safe", "not safe",
        "scared to go home", "afraid to go home", "fear for my safety",
    ],
    "immediate_threat": [
        "he is threatening me", "she is threatening me", "they are threatening me",
        "threatened to kill me", "threatened to hurt me", "threatened me",
        "threatening me", "threatened my family", "threatening my family",
        "threatened my life", "threatening my life", "death threat",
        "threat to kill me", "threat to hurt me", "going to kill me",
        "going to hurt me", "has a weapon", "has a gun", "has a knife",
        "coming after me", "following me", "i am in immediate danger",
        "immediate danger", "danger right now", "he is outside",
        "she is outside", "they are outside", "dangerous person nearby",
        "attacker nearby", "afraid for my life", "fear for my life",
        "unsafe at home", "unsafe going home",
    ],
    "distress": [
        "i can't cope", "i cannot cope", "i feel overwhelmed", "overwhelmed",
        "i am breaking down", "breaking down", "i can't take this",
        "i cannot take this", "i feel helpless", "helpless", "i feel hopeless",
        "hopeless", "i am suffering", "extremely stressed", "very stressed",
        "constant stress", "panic", "panicking",
    ],
    "isolation": [
        "i have nobody", "i have no one", "no one to help me",
        "nobody to help me", "i am alone", "i feel alone", "completely alone",
        "no support", "nobody supports me", "no family support",
        "my family abandoned me", "i cannot tell anyone", "i have nowhere to go",
        "isolated from my family", "isolated from my friends",
        "kept away from my family", "cut off from my family",
        "separated from my family", "no one is helping me",
        "no one to turn to",
    ],
    "intimidation": [
        "he threatens me", "she threatens me", "they threaten me",
        "threatening me", "threatened me", "threatening my family",
        "threatened my family", "blackmail", "blackmailing me", "forced me",
        "forcing me", "pressuring me", "pressured me", "i am being controlled",
        "controls me", "controlling me", "they are forcing me",
        "warned me", "warned me not to complain",
    ],
    "self_harm": [
        "i want to die", "i don't want to live", "i do not want to live",
        "want to kill myself", "thinking of killing myself", "thinking about suicide",
        "suicidal", "end my life", "ending my life", "hurt myself", "harm myself",
        "kill myself", "self harm", "self-harm", "no reason to live",
        "life is not worth living",
    ],
}


def normalize_text(text: str) -> str:
    text = text.lower().strip().replace("’", "'")
    return re.sub(r"\s+", " ", text)


def _is_negated(text: str, phrase_start: int) -> bool:
    context_start = max(0, phrase_start - 35)
    context = text[context_start:phrase_start].strip()
    negation_terms = [
        "not", "no", "never", "don't", "dont", "do not", "didn't",
        "did not", "isn't", "isnt", "is not", "wasn't", "wasnt", "was not",
        "nahi", "nahin", "nahiin", "nhi",
    ]
    return any(
        re.search(rf"\b{re.escape(term)}\s*$", context)
        for term in negation_terms
    )


def _keyword_detect(text: str) -> Dict[str, dict]:
    normalized = normalize_text(text)
    results = {}

    for signal, patterns in SIGNAL_PATTERNS.items():
        matches: List[str] = []
        for phrase in patterns:
            start = normalized.find(phrase)
            while start != -1:
                if not _is_negated(normalized, start):
                    matches.append(phrase)
                start = normalized.find(phrase, start + len(phrase))
        matches = list(dict.fromkeys(matches))
        results[signal] = {
            "matches": matches,
            "match_count": len(matches),
        }
    return results


def calculate_signal_score(match_count: int) -> float:
    if match_count <= 0:
        return 0.0
    if match_count == 1:
        return 40.0
    if match_count == 2:
        return 65.0
    if match_count == 3:
        return 80.0
    return 90.0


def _merge_signal(keyword_data: dict, semantic_data: dict | None) -> dict:
    keyword_matches = keyword_data.get("matches", [])
    keyword_score = calculate_signal_score(len(keyword_matches))

    if not semantic_data:
        return {
            **keyword_data,
            "score": keyword_score,
            "engine": "keyword_baseline",
        }

    semantic_matches = semantic_data.get("matches", [])
    all_matches = list(dict.fromkeys(keyword_matches + semantic_matches))

    # Semantic score is primary. Exact keyword evidence can strengthen it,
    # but cannot create an extreme score on its own.
    semantic_score = float(semantic_data.get("semantic_score", 0.0))
    score = max(semantic_score, keyword_score)

    return {
        "matches": all_matches[:5],
        "match_count": len(all_matches),
        "score": round(min(score, 90.0), 1),
        "engine": "semantic+keyword",
        "semantic_similarity": semantic_data.get("semantic_similarity"),
    }


def _empty_context() -> dict:
    return {
        "available": False,
        "signals": {},
        "discourse": {},
        "indicator": 0.0,
        "sub_scores": {},
        "cues": [],
        "engine": "none",
    }


def _apply_context(output: Dict[str, dict], context: dict) -> None:
    """
    Raise a signal when the passage *as a whole* (2-3 sentence windows or
    the full narrative) expresses it more strongly than any single
    sentence did.  Context can strengthen a signal but never creates a
    score above the same 90-point ceiling used by the semantic layer.
    """
    for signal, data in (context.get("signals") or {}).items():
        if signal not in output:
            continue
        ctx_score = float(data.get("score", 0.0) or 0.0)
        current = float(output[signal].get("score", 0.0) or 0.0)
        if ctx_score <= current:
            continue
        output[signal]["score"] = round(min(ctx_score, 90.0), 1)
        output[signal]["engine"] = output[signal].get("engine", "keyword_baseline") + "+context"
        output[signal]["context_similarity"] = data.get("similarity")
        output[signal]["context_level"] = data.get("level")
        evidence = data.get("evidence")
        if evidence:
            output[signal]["matches"] = list(dict.fromkeys(
                list(output[signal].get("matches", [])) + [evidence]
            ))[:5]
            output[signal]["match_count"] = max(
                int(output[signal].get("match_count", 0) or 0), 1
            )


def analyze_text(text: str, return_context: bool = False):
    """
    Analyze text using semantic NLP first, with keyword fallback, then
    whole-passage context.

    Returns the per-signal dictionary; with ``return_context=True`` it
    returns ``(signals, narrative_context)`` so the caller can expose the
    discourse-level reading without running the models twice.
    """
    keyword_results = _keyword_detect(text)

    try:
        semantic_results = semantic_detect(text)
    except Exception:
        # Never make the assessment API unavailable because an optional model
        # cannot load. The deterministic baseline remains available.
        semantic_results = {}

    output = {}
    for signal in SIGNAL_PATTERNS:
        output[signal] = _merge_signal(
            keyword_results.get(signal, {}),
            semantic_results.get(signal),
        )

    # Whole-passage reading: cross-sentence windows, the passage as a
    # whole, and discourse structure (escalation, helplessness, ...).
    try:
        context = analyze_narrative_context(text)
    except Exception:
        context = _empty_context()
    _apply_context(output, context)

    # Safety-sensitive contextual calibration. Semantic NLP remains the
    # detector; this layer recognizes compositional threat events such as
    # "they said they will kill me tomorrow" and prevents dilution of a
    # severe safety signal by unrelated zero-valued categories.
    threat_context = extract_threat_context(text)
    context_score = float(threat_context.get("score", 0) or 0)
    if context_score > 0:
        current = float(output["immediate_threat"].get("score", 0) or 0)
        output["immediate_threat"]["score"] = round(max(current, context_score), 1)
        output["immediate_threat"]["engine"] = (
            output["immediate_threat"].get("engine", "keyword_baseline")
            + "+context"
        )
        output["immediate_threat"]["threat_context"] = threat_context
        output["immediate_threat"]["matches"] = list(dict.fromkeys(
            output["immediate_threat"].get("matches", [])
            + [text.strip()]
        ))[:5]

        # A concrete external threat is also an intimidation/coercion signal.
        if threat_context.get("direct_lethal"):
            intimidation = output["intimidation"]
            intimidation["score"] = max(float(intimidation.get("score", 0) or 0), 65.0)
            intimidation["matches"] = list(dict.fromkeys(
                intimidation.get("matches", []) + [text.strip()]
            ))[:5]

    if return_context:
        return output, context
    return output


__all__ = [
    "analyze_text",
    "calculate_signal_score",
    "detect_language",
    "normalize_text",
]
