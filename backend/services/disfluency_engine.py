"""
Disfluency engine
=================

Detects *how* something was said from the transcript itself — the
"fumbling" nuances that a plain keyword or semantic pass ignores:

    * filler sounds            um, uh, hmm, matlab, wo-wo, अं ...
    * word / phrase repetition "I I I was", "wo wo aadmi"
    * restarts / self-repair   "he came- no wait, they came"
    * hedging & uncertainty    "I think", "maybe", "shayad", "pata nahi"
    * trailing / broken sentences
    * timing hesitations       long gaps between Whisper segments,
                               very slow segments, low ASR confidence

Works on English, Hinglish (romanised Hindi) and Devanagari Hindi.

Output is a feature dictionary plus a transparent 0-100 indicator with
cues, mirroring the prosody engine.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------
# Lexicons
# ---------------------------------------------------------------------

FILLERS = [
    # English
    r"\bum+\b", r"\buh+\b", r"\ber+m?\b", r"\bah+\b", r"\bhmm+\b", r"\bmm+\b",
    r"\buh[- ]huh\b", r"\byou know\b", r"\bi mean\b", r"\bkind of\b", r"\bsort of\b",
    r"\blike,\b", r"\bbasically\b", r"\bactually\b", r"\bokay so\b",
    # Hinglish / romanised Hindi
    r"\bmatlab\b", r"\bmtlb\b", r"\bwo+h?\b(?=\s+\bwo+h?\b)", r"\bkya bolte\b", r"\bkya kehte\b",
    r"\bhaan\b", r"\bhan\b", r"\bhmm\b", r"\bumm\b", r"\bachha\b", r"\bacha\b", r"\byaani\b", r"\byani\b",
    r"\bbas\b", r"\bwoh kya\b", r"\bkaise bolu\b", r"\bkaise kahu\b",
    # Devanagari
    r"मतलब", r"यानी", r"अं+", r"हम्म+", r"क्या बोलते", r"क्या कहते", r"अच्छा", r"वो\s+वो", r"हाँ",
]

HEDGES = [
    r"\bi think\b", r"\bi guess\b", r"\bmaybe\b", r"\bperhaps\b", r"\bprobably\b",
    r"\bi don'?t know\b", r"\bi'?m not sure\b", r"\bnot sure\b", r"\bi suppose\b",
    r"\bsomething like\b", r"\bor something\b", r"\bi can'?t remember\b", r"\bi can'?t explain\b",
    r"\bit'?s hard to say\b", r"\bi don'?t remember\b",
    r"\bshayad\b", r"\bshayd\b", r"\bpata nahi\b", r"\bpata nahin\b", r"\bpta nahi\b", r"\bmujhe nahi pata\b",
    r"\byaad nahi\b", r"\bsamajh nahi\b", r"\bkuch aisa\b", r"\blagta hai\b", r"\bshayad hi\b",
    r"शायद", r"पता नहीं", r"याद नहीं", r"समझ नहीं", r"लगता है", r"कुछ ऐसा",
]

RESTARTS = [
    r"\bno wait\b", r"\bwait\b", r"\bno no\b", r"\bsorry\b", r"\bi mean\b", r"\blet me\b",
    r"\bwhat i mean\b", r"\bactually no\b", r"\bnot that\b",
    r"\bnahi nahi\b", r"\bnahin nahin\b", r"\bmatlab nahi\b", r"\bruko\b", r"\bek minute\b", r"\bek min\b",
    r"\bsorry sorry\b", r"\bgalat\b",
    r"नहीं नहीं", r"रुको", r"एक मिनट", r"मतलब नहीं", r"माफ़ करना", r"माफ करना",
]

TRAILING_PATTERNS = [
    r"\.\.\.\s*$", r"…\s*$", r"[-–—]\s*$",
    r"\b(and|but|so|because|then|aur|lekin|phir|kyunki|toh|to|ki|और|लेकिन|फिर|क्योंकि|तो|कि)\s*[.!?]?\s*$",
]

WORD_RE = re.compile(r"[\w'’ऀ-ॿ]+", re.UNICODE)

SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?।])\s+|\n+")


# Normalisation ranges (per 100 words unless noted)
RANGES = {
    "filler_per_100w": (2.0, 12.0),
    "repetition_per_100w": (1.0, 8.0),
    "restart_per_100w": (0.5, 5.0),
    "hedge_per_100w": (1.5, 9.0),
    "trailing_ratio": (0.10, 0.50),
    "hesitation_gap_count": (0.0, 5.0),
    "hesitation_gap_ratio": (0.10, 0.40),
    "low_confidence_ratio": (0.15, 0.60),
}

SUB_WEIGHTS = {
    "fillers": 0.22,
    "repetitions": 0.20,
    "restarts": 0.15,
    "hedging": 0.13,
    "fragments": 0.10,
    "timing": 0.20,
}

HESITATION_GAP_SEC = 1.0


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return round(max(0.0, min(100.0, (float(value) - low) / (high - low) * 100.0)), 1)


def _count(patterns: List[str], text: str) -> List[str]:
    """Collect matches, dropping any match nested inside a longer one."""
    spans: List[tuple] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            spans.append((match.start(), match.end(), match.group(0).strip()))

    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    hits: List[str] = []
    last_end = -1
    for start, end, value in spans:
        if start < last_end:
            continue
        hits.append(value)
        last_end = end
    return hits


def _words(text: str) -> List[str]:
    return [w.lower() for w in WORD_RE.findall(text)]


# ---------------------------------------------------------------------
# Repetitions
# ---------------------------------------------------------------------

def find_repetitions(words: List[str]) -> Dict[str, Any]:
    """
    Immediate repetitions of a word ("I I I") or of a two-word phrase
    ("I was I was").  Stutter-like partial repeats ("wh- what") are
    detected on the raw text separately.
    """
    single = 0
    double = 0
    examples: List[str] = []

    i = 0
    while i < len(words) - 1:
        if words[i] == words[i + 1] and (len(words[i]) > 1 or words[i] in {"i", "a"}):
            run = 1
            while i + run < len(words) and words[i + run] == words[i]:
                run += 1
            single += run - 1
            examples.append(" ".join(words[i : i + run]))
            i += run
            continue
        i += 1

    for i in range(len(words) - 3):
        if words[i] == words[i + 2] and words[i + 1] == words[i + 3] and words[i] != words[i + 1]:
            double += 1
            examples.append(" ".join(words[i : i + 4]))

    return {
        "single_word_repeats": single,
        "phrase_repeats": double,
        "examples": examples[:6],
    }


def find_stutters(text: str) -> List[str]:
    """Partial-word repeats such as "wh- what", "m-m-mujhe", "k-kya"."""
    pattern = r"\b(\w{1,3})-\s?(?:\1-\s?)*\1\w*"
    return [m.group(0) for m in re.finditer(pattern, text, flags=re.IGNORECASE)]


# ---------------------------------------------------------------------
# Timing from ASR segments
# ---------------------------------------------------------------------

def analyze_segment_timing(segments: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Whisper segments carry ``start``, ``end``, ``text`` and optionally
    ``avg_logprob`` / ``no_speech_prob``.  Gaps between consecutive
    segments are hesitations the transcript alone cannot show.
    """
    if not segments:
        return {
            "available": False,
            "segment_count": 0,
            "hesitation_gap_count": 0,
            "hesitation_gap_ratio": 0.0,
            "max_gap_sec": 0.0,
            "words_per_sec": 0.0,
            "slow_segment_ratio": 0.0,
            "low_confidence_ratio": 0.0,
        }

    ordered = sorted(
        (s for s in segments if isinstance(s, dict) and "start" in s and "end" in s),
        key=lambda s: float(s.get("start", 0.0)),
    )
    if not ordered:
        return analyze_segment_timing(None)

    gaps: List[float] = []
    for prev, cur in zip(ordered, ordered[1:]):
        gap = float(cur.get("start", 0.0)) - float(prev.get("end", 0.0))
        if gap > 0:
            gaps.append(gap)

    total_speech = sum(max(0.0, float(s.get("end", 0)) - float(s.get("start", 0))) for s in ordered)
    span = float(ordered[-1].get("end", 0.0)) - float(ordered[0].get("start", 0.0))
    word_total = sum(len(_words(str(s.get("text", "")))) for s in ordered)

    slow = 0
    low_conf = 0
    for s in ordered:
        dur = max(0.0, float(s.get("end", 0)) - float(s.get("start", 0)))
        n_words = len(_words(str(s.get("text", ""))))
        if dur > 0 and n_words and n_words / dur < 1.2:
            slow += 1
        if float(s.get("avg_logprob", 0.0)) < -1.0 or float(s.get("no_speech_prob", 0.0)) > 0.5:
            low_conf += 1

    hesitations = [g for g in gaps if g >= HESITATION_GAP_SEC]
    return {
        "available": True,
        "segment_count": len(ordered),
        "hesitation_gap_count": len(hesitations),
        "hesitation_gap_ratio": round(sum(hesitations) / span, 3) if span > 0 else 0.0,
        "max_gap_sec": round(max(gaps), 2) if gaps else 0.0,
        "words_per_sec": round(word_total / total_speech, 2) if total_speech > 0 else 0.0,
        "slow_segment_ratio": round(slow / len(ordered), 3),
        "low_confidence_ratio": round(low_conf / len(ordered), 3),
    }


# ---------------------------------------------------------------------
# Main extraction
# ---------------------------------------------------------------------

def extract_disfluency_features(
    transcript: str,
    segments: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    text = (transcript or "").strip()
    if not text:
        return {"available": False, "error": "Empty transcript."}

    lowered = text.lower().replace("’", "'")
    words = _words(lowered)
    word_count = max(len(words), 1)
    per100 = 100.0 / word_count

    fillers = _count(FILLERS, lowered)
    hedges = _count(HEDGES, lowered)
    restarts = _count(RESTARTS, lowered)
    stutters = find_stutters(text)
    repetition = find_repetitions(words)

    sentences = [s.strip() for s in SENTENCE_SPLIT_RE.split(text) if s.strip()]
    trailing = [
        s for s in sentences
        if any(re.search(p, s.lower()) for p in TRAILING_PATTERNS)
    ]
    short_fragments = [s for s in sentences if 0 < len(_words(s)) <= 2]

    timing = analyze_segment_timing(segments)

    repeat_count = (
        repetition["single_word_repeats"]
        + 2 * repetition["phrase_repeats"]
        + len(stutters)
    )

    return {
        "available": True,
        "word_count": word_count,
        "sentence_count": len(sentences),
        "fillers": {
            "count": len(fillers),
            "per_100_words": round(len(fillers) * per100, 1),
            "examples": [f for f, _ in Counter(fillers).most_common(5)],
        },
        "repetitions": {
            "count": repeat_count,
            "per_100_words": round(repeat_count * per100, 1),
            "stutters": stutters[:5],
            "examples": repetition["examples"],
        },
        "restarts": {
            "count": len(restarts),
            "per_100_words": round(len(restarts) * per100, 1),
            "examples": [r for r, _ in Counter(restarts).most_common(5)],
        },
        "hedging": {
            "count": len(hedges),
            "per_100_words": round(len(hedges) * per100, 1),
            "examples": [h for h, _ in Counter(hedges).most_common(5)],
        },
        "fragments": {
            "trailing_count": len(trailing),
            "short_fragment_count": len(short_fragments),
            "trailing_ratio": round(len(trailing) / max(len(sentences), 1), 3),
            "examples": trailing[:3],
        },
        "timing": timing,
    }


# ---------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------

def calculate_disfluency_indicator(features: Dict[str, Any]) -> Dict[str, Any]:
    if not features.get("available"):
        return {"available": False, "indicator": 0.0, "sub_scores": {}, "cues": []}

    cues: List[str] = []
    word_count = int(features.get("word_count", 0))

    fillers = features["fillers"]
    reps = features["repetitions"]
    restarts = features["restarts"]
    hedging = features["hedging"]
    fragments = features["fragments"]
    timing = features.get("timing", {})

    # Very short statements make per-100-word rates explode; damp them.
    damp = min(1.0, word_count / 25.0)

    filler_score = _scale(fillers["per_100_words"], *RANGES["filler_per_100w"]) * damp
    rep_score = _scale(reps["per_100_words"], *RANGES["repetition_per_100w"]) * damp
    restart_score = _scale(restarts["per_100_words"], *RANGES["restart_per_100w"]) * damp
    hedge_score = _scale(hedging["per_100_words"], *RANGES["hedge_per_100w"]) * damp
    fragment_score = _scale(fragments["trailing_ratio"], *RANGES["trailing_ratio"]) * damp

    if timing.get("available"):
        timing_score = max(
            _scale(timing.get("hesitation_gap_count", 0), *RANGES["hesitation_gap_count"]),
            _scale(timing.get("hesitation_gap_ratio", 0), *RANGES["hesitation_gap_ratio"]),
            0.6 * _scale(timing.get("low_confidence_ratio", 0), *RANGES["low_confidence_ratio"]),
        )
    else:
        timing_score = 0.0

    if fillers["count"] >= 3 and filler_score >= 40:
        cues.append(
            f"Frequent filler sounds ({fillers['count']} e.g. "
            f"{', '.join(repr(x) for x in fillers['examples'][:3])})."
        )
    if reps["count"] >= 2 and rep_score >= 40:
        example = reps["examples"][0] if reps["examples"] else (reps["stutters"][0] if reps["stutters"] else "")
        cues.append(f"Stuttering / repeated words while speaking (e.g. \"{example}\").")
    if restarts["count"] >= 1 and restart_score >= 40:
        cues.append("The person restarted or corrected themselves mid-sentence.")
    if hedging["count"] >= 2 and hedge_score >= 40:
        cues.append(
            f"Uncertain, hedged phrasing ({', '.join(repr(x) for x in hedging['examples'][:3])})."
        )
    if fragments["trailing_count"] >= 2 and fragment_score >= 40:
        cues.append("Several sentences were left unfinished or trailed off.")
    if timing.get("hesitation_gap_count", 0) >= 2:
        cues.append(
            f"{timing['hesitation_gap_count']} long hesitations between phrases "
            f"(longest {timing.get('max_gap_sec', 0):.1f}s)."
        )

    sub_scores = {
        "fillers": round(filler_score, 1),
        "repetitions": round(rep_score, 1),
        "restarts": round(restart_score, 1),
        "hedging": round(hedge_score, 1),
        "fragments": round(fragment_score, 1),
        "timing": round(timing_score, 1),
    }

    # Timing weight is redistributed when no segment timing exists.
    weights = dict(SUB_WEIGHTS)
    if not timing.get("available"):
        weights.pop("timing")
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

    indicator = sum(sub_scores[k] * w for k, w in weights.items())
    return {
        "available": True,
        "indicator": round(max(0.0, min(100.0, indicator)), 1),
        "sub_scores": sub_scores,
        "cues": cues,
    }


__all__ = [
    "extract_disfluency_features",
    "calculate_disfluency_indicator",
]
