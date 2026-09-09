"""
Narrative context engine
========================

Whole-passage understanding for the SAHAYAK text pipeline.

The semantic engine scores one sentence at a time.  That is robust for
explicit statements ("I am scared") but misses meaning that only exists
*across* sentences:

    "He came back last night.  He had a knife.  I locked the children in
     the bedroom and did not sleep."

No single sentence there mentions fear or a threat, yet the passage as a
whole clearly does.  This engine therefore reads the narrative at three
levels and combines them:

    1. sliding windows of 2-3 sentences  (cross-sentence meaning)
    2. the passage as a whole            (accumulated meaning)
    3. discourse features                (HOW the story is told)

Discourse features are language-aware (English / Hindi / Hinglish) and
are known linguistic correlates of acute stress:

    * escalation      distress builds up towards the end of the account
    * fragmentation   the narrative jumps between unrelated ideas
    * rumination      the same distressing content is repeated
    * immediacy       "now / tonight / abhi" - the danger is present tense
    * helplessness    "nothing I can do", "koi rasta nahi"
    * absolutism      "always", "never", "nothing", "hamesha", "kabhi nahi"
    * self-focus      dense first-person pronouns
    * hedged safety   "I think I'm fine... but"

Everything degrades gracefully: without the sentence-transformer model
only the discourse layer runs and the signal boosts are empty.

This is a decision-support prototype.  Thresholds are engineering values
and must be validated on consented data before real deployment.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from services.semantic_engine import (
    SEMANTIC_THRESHOLD,
    SIGNAL_PROTOTYPES,
    is_signal_negated,
    load_semantic_model,
    prototype_embeddings,
    split_sentences,
)


# ---------------------------------------------------------------------
# Lexicons (English + romanised Hindi + Devanagari)
# ---------------------------------------------------------------------

IMMEDIACY_TERMS = [
    r"\bright now\b", r"\bnow\b", r"\btonight\b", r"\btoday\b", r"\bat this moment\b",
    r"\bstill\b", r"\bkeeps?\b", r"\bevery (day|night)\b", r"\bagain\b", r"\bjust now\b",
    r"\babhi\b", r"\baaj\b", r"\baaj raat\b", r"\bab\b", r"\bis waqt\b", r"\bfir se\b", r"\bphir se\b",
    r"\bhar (din|raat)\b", r"\broz\b",
    r"अभी", r"आज", r"आज रात", r"इस वक्त", r"फिर से", r"हर दिन", r"हर रात", r"रोज़", r"रोज",
]

HELPLESSNESS_TERMS = [
    r"\bnothing i can do\b", r"\bnothing i could do\b", r"\bcan'?t do anything\b", r"\bcannot do anything\b",
    r"\bno way out\b", r"\bno choice\b", r"\bno option\b", r"\bnowhere to go\b", r"\bno one (will|can) help\b",
    r"\bcan'?t (stop|escape|leave|get out|get away)\b", r"\btrapped\b", r"\bstuck\b", r"\bpowerless\b",
    r"\bwhat (can|do) i do\b", r"\bgive up\b", r"\bno point\b",
    r"\bkuch nahi kar sak(ta|ti|te)\b", r"\bkuch nahi ho sakta\b", r"\bkoi rasta nahi\b", r"\bkoi option nahi\b",
    r"\bmajboor\b", r"\bmajbur\b", r"\bkahan jau\b", r"\bkahan jaun\b", r"\bkya karu\b", r"\bkya karun\b",
    r"\bbhaag nahi sak(ta|ti)\b", r"\bnikal nahi sak(ta|ti)\b", r"\bphas (gaya|gayi|gai)\b",
    r"कुछ नहीं कर सक", r"कोई रास्ता नहीं", r"मजबूर", r"कहाँ जाऊँ", r"कहां जाऊं", r"क्या करूँ", r"क्या करूं",
    r"फँस", r"फंस", r"निकल नहीं सकत",
]

ABSOLUTIST_TERMS = [
    r"\balways\b", r"\bnever\b", r"\bnothing\b", r"\beverything\b", r"\bcompletely\b", r"\btotally\b",
    r"\bnobody\b", r"\bno one\b", r"\beveryone\b", r"\bforever\b", r"\bconstantly\b", r"\bentirely\b",
    r"\bhamesha\b", r"\bkabhi nahi\b", r"\bkuch nahi\b", r"\bsab kuch\b", r"\bkoi nahi\b", r"\bbilkul\b",
    r"\bpoori tarah\b", r"\bsab log\b", r"\bpura din\b", r"\bpoora din\b",
    r"हमेशा", r"कभी नहीं", r"कुछ नहीं", r"सब कुछ", r"कोई नहीं", r"बिल्कुल", r"पूरी तरह", r"सब लोग",
]

FIRST_PERSON_TERMS = {
    "i", "me", "my", "mine", "myself", "i'm", "i've", "i'll", "i'd",
    "main", "mai", "mujhe", "mujhko", "mera", "meri", "mere", "mujhse", "hum", "humein", "hamein", "hume",
    "मैं", "मुझे", "मुझको", "मेरा", "मेरी", "मेरे", "मुझसे", "हम", "हमें",
}

CONTRAST_TERMS = [
    r"\bbut\b", r"\bhowever\b", r"\bexcept\b", r"\bthough\b", r"\balthough\b",
    r"\blekin\b", r"\bpar\b", r"\bmagar\b", r"\bfir bhi\b", r"\bphir bhi\b",
    r"लेकिन", r"पर", r"मगर", r"फिर भी",
]

SAFETY_CLAIMS = [
    r"\bi'?m (fine|ok|okay|alright|safe)\b", r"\bi am (fine|ok|okay|alright|safe)\b",
    r"\beverything is (fine|ok|okay|normal)\b", r"\bit'?s (fine|ok|okay|nothing)\b", r"\bnot a big deal\b",
    r"\bmain (theek|thik) (hoon|hu)\b", r"\bsab (theek|thik) hai\b", r"\bkoi baat nahi\b", r"\bkuch nahi hua\b",
    r"मैं ठीक हूँ", r"मैं ठीक हूं", r"सब ठीक है", r"कोई बात नहीं", r"कुछ नहीं हुआ",
]

WORD_RE = re.compile(r"[\w'’ऀ-ॿ]+", re.UNICODE)

WINDOW_SIZES = (2, 3)

# Engineering normalisation ranges (value -> 0..100).  Not clinical.
RANGES = {
    "escalation_slope": (0.02, 0.12),      # similarity gain per sentence
    "fragmentation": (0.45, 0.80),         # 1 - adjacent-sentence coherence
    "rumination": (0.30, 0.70),            # share of sentence pairs that repeat the same distressing idea
    "immediacy_ratio": (0.15, 0.60),       # share of sentences with present-tense danger markers
    "helplessness_per_100w": (0.5, 4.0),
    "absolutist_per_100w": (1.5, 8.0),
    "first_person_ratio": (0.10, 0.28),
}

SUB_WEIGHTS = {
    "escalation": 0.18,
    "fragmentation": 0.14,
    "rumination": 0.12,
    "immediacy": 0.18,
    "helplessness": 0.18,
    "absolutism": 0.10,
    "self_focus": 0.10,
}

MAX_EVIDENCE_CHARS = 220


def _scale(value: float, low: float, high: float) -> float:
    if high <= low:
        return 0.0
    return round(max(0.0, min(100.0, (float(value) - low) / (high - low) * 100.0)), 1)


def _count(patterns: Sequence[str], text: str) -> int:
    return sum(len(re.findall(p, text, flags=re.IGNORECASE)) for p in patterns)


def _tier_score(similarity: float) -> float:
    """Same similarity → score tiers as the sentence-level semantic engine."""
    if similarity >= 0.78:
        return 90.0
    if similarity >= 0.70:
        return 80.0
    if similarity >= 0.62:
        return 65.0
    if similarity >= SEMANTIC_THRESHOLD:
        return 40.0
    return 0.0


def _windows(sentences: List[str]) -> List[Tuple[int, int, str]]:
    """(start, end, text) for every 2- and 3-sentence window."""
    out: List[Tuple[int, int, str]] = []
    n = len(sentences)
    for size in WINDOW_SIZES:
        if n < size:
            continue
        for i in range(0, n - size + 1):
            out.append((i, i + size, " ".join(sentences[i : i + size])))
    return out


def _clip(text: str) -> str:
    text = text.strip()
    if len(text) <= MAX_EVIDENCE_CHARS:
        return text
    return text[: MAX_EVIDENCE_CHARS - 1].rstrip() + "…"


# ---------------------------------------------------------------------
# Embedding helpers
# ---------------------------------------------------------------------

def _encode(model, texts: List[str]):
    return model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )


def _best_similarity(embedding, prototypes) -> float:
    return max(float(embedding @ proto_embedding) for _, proto_embedding in prototypes)


# ---------------------------------------------------------------------
# Discourse features
# ---------------------------------------------------------------------

def discourse_features(
    text: str,
    sentences: List[str],
    intensity: Optional[List[float]] = None,
    coherence: Optional[List[float]] = None,
    repeat_pairs: Optional[float] = None,
) -> Dict[str, Any]:
    """
    Lexical + (optionally) embedding-derived description of *how* the
    narrative is told.  ``intensity`` is the per-sentence peak signal
    similarity, ``coherence`` the adjacent-sentence cosine similarities.
    """
    lowered = text.lower().replace("’", "'")
    words = [w.lower() for w in WORD_RE.findall(lowered)]
    word_count = max(len(words), 1)
    per100 = 100.0 / word_count
    n = max(len(sentences), 1)

    immediacy_sentences = sum(
        1 for s in sentences if any(re.search(p, s.lower()) for p in IMMEDIACY_TERMS)
    )
    helplessness = _count(HELPLESSNESS_TERMS, lowered)
    absolutist = _count(ABSOLUTIST_TERMS, lowered)
    first_person = sum(1 for w in words if w in FIRST_PERSON_TERMS)
    contrast = _count(CONTRAST_TERMS, lowered)
    safety_claims = _count(SAFETY_CLAIMS, lowered)

    # --- escalation: linear trend of distress intensity over the account
    slope = 0.0
    peak_position = None
    if intensity and len(intensity) >= 3:
        xs = list(range(len(intensity)))
        mean_x = sum(xs) / len(xs)
        mean_y = sum(intensity) / len(intensity)
        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, intensity))
        den = sum((x - mean_x) ** 2 for x in xs) or 1.0
        slope = num / den
        peak_position = round(intensity.index(max(intensity)) / max(len(intensity) - 1, 1), 2)

    fragmentation = None
    if coherence and len(coherence) >= 2:
        fragmentation = round(1.0 - (sum(coherence) / len(coherence)), 3)

    trajectory = "steady"
    if intensity and len(intensity) >= 3:
        if slope >= RANGES["escalation_slope"][0]:
            trajectory = "escalating"
        elif slope <= -RANGES["escalation_slope"][0]:
            trajectory = "de-escalating"
        elif max(intensity) - min(intensity) >= 0.25:
            trajectory = "volatile"

    return {
        "sentence_count": len(sentences),
        "word_count": word_count,
        "escalation_slope": round(slope, 4),
        "trajectory": trajectory,
        "peak_position": peak_position,
        "fragmentation": fragmentation,
        "rumination": round(repeat_pairs, 3) if repeat_pairs is not None else None,
        "immediacy_ratio": round(immediacy_sentences / n, 3),
        "helplessness_count": helplessness,
        "helplessness_per_100w": round(helplessness * per100, 2),
        "absolutist_count": absolutist,
        "absolutist_per_100w": round(absolutist * per100, 2),
        "first_person_ratio": round(first_person / word_count, 3),
        "contrast_count": contrast,
        "safety_claim_count": safety_claims,
        "hedged_safety": bool(safety_claims and contrast),
    }


# ---------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------

def analyze_narrative_context(text: str) -> Dict[str, Any]:
    """
    Read the whole narrative and return

        {
          "available": bool,               # semantic model was usable
          "signals": {signal: {"score", "similarity", "level", "evidence"}},
          "discourse": {...},              # see discourse_features()
          "indicator": 0-100,              # narrative stress index
          "sub_scores": {...},
          "cues": [...],                   # human readable
          "engine": "context" | "discourse_only"
        }
    """
    sentences = split_sentences(text or "")
    if not sentences:
        return {
            "available": False,
            "signals": {},
            "discourse": {},
            "indicator": 0.0,
            "sub_scores": {},
            "cues": [],
            "engine": "none",
        }

    model = None
    grouped = None
    try:
        model = load_semantic_model()
        grouped = prototype_embeddings()
    except Exception:
        model = None
        grouped = None

    signals: Dict[str, Dict[str, Any]] = {}
    intensity: Optional[List[float]] = None
    coherence: Optional[List[float]] = None
    repeat_pairs: Optional[float] = None
    semantic_available = model is not None and grouped is not None

    if semantic_available:
        try:
            windows = _windows(sentences)
            passage = " ".join(sentences)

            # One batched encode for everything we need.
            texts = list(sentences) + [w[2] for w in windows] + [passage]
            embeddings = _encode(model, texts)
            sent_emb = embeddings[: len(sentences)]
            win_emb = embeddings[len(sentences) : len(sentences) + len(windows)]
            passage_emb = embeddings[-1]

            # --- adjacent-sentence coherence + repetition -------------
            if len(sentences) >= 2:
                coherence = [
                    float(sent_emb[i] @ sent_emb[i + 1]) for i in range(len(sentences) - 1)
                ]
                # Rumination: non-adjacent sentence pairs that say (almost)
                # the same thing while both being distress-relevant.
                pairs = 0
                repeats = 0
                for i in range(len(sentences)):
                    for j in range(i + 2, len(sentences)):
                        pairs += 1
                        if float(sent_emb[i] @ sent_emb[j]) >= 0.75:
                            repeats += 1
                repeat_pairs = repeats / pairs if pairs else 0.0

            # --- per-sentence intensity (for escalation) ---------------
            intensity = []
            for emb in sent_emb:
                intensity.append(
                    max(_best_similarity(emb, protos) for protos in grouped.values())
                )

            # --- per-signal window / passage similarity ----------------
            for signal, protos in grouped.items():
                best_sim = 0.0
                best_text = ""
                best_kind = ""

                for (start, end, wtext), emb in zip(windows, win_emb):
                    if is_signal_negated(wtext, signal):
                        continue
                    sim = _best_similarity(emb, protos)
                    if sim > best_sim:
                        best_sim, best_text, best_kind = sim, wtext, f"window[{start}:{end}]"

                if not is_signal_negated(passage, signal):
                    psim = _best_similarity(passage_emb, protos)
                    # The passage embedding is a blur of everything; it
                    # is only trusted when clearly above threshold.
                    if psim > best_sim and psim >= SEMANTIC_THRESHOLD + 0.05:
                        best_sim, best_text, best_kind = psim, passage, "passage"

                score = _tier_score(best_sim)
                if score > 0:
                    signals[signal] = {
                        "score": score,
                        "similarity": round(best_sim, 3),
                        "level": best_kind,
                        "evidence": _clip(best_text),
                    }
        except Exception:
            semantic_available = False
            signals = {}
            intensity = None
            coherence = None
            repeat_pairs = None

    discourse = discourse_features(text, sentences, intensity, coherence, repeat_pairs)

    # -----------------------------------------------------------------
    # Narrative stress index
    # -----------------------------------------------------------------
    cues: List[str] = []

    escalation_score = _scale(discourse["escalation_slope"], *RANGES["escalation_slope"]) if intensity else 0.0
    if discourse["trajectory"] == "escalating" and escalation_score >= 40:
        cues.append("The account becomes progressively more distressed towards the end.")
    elif discourse["trajectory"] == "volatile":
        cues.append("Distress in the account rises and falls sharply between sentences.")

    fragmentation_score = (
        _scale(discourse["fragmentation"], *RANGES["fragmentation"])
        if discourse.get("fragmentation") is not None
        else 0.0
    )
    if fragmentation_score >= 50:
        cues.append("The narrative jumps between unrelated ideas (fragmented account).")

    rumination_score = (
        _scale(discourse["rumination"], *RANGES["rumination"])
        if discourse.get("rumination") is not None
        else 0.0
    )
    if rumination_score >= 50:
        cues.append("The same distressing point is repeated several times (rumination).")

    immediacy_score = _scale(discourse["immediacy_ratio"], *RANGES["immediacy_ratio"])
    if immediacy_score >= 50 and signals:
        cues.append("The danger is described in the present tense — it is ongoing, not past.")

    helplessness_score = _scale(discourse["helplessness_per_100w"], *RANGES["helplessness_per_100w"])
    if discourse["helplessness_count"] >= 1 and helplessness_score >= 40:
        cues.append("Language of helplessness / no way out.")

    absolutism_score = _scale(discourse["absolutist_per_100w"], *RANGES["absolutist_per_100w"])
    if absolutism_score >= 50:
        cues.append("Absolutist wording (always / never / nothing) typical of acute distress.")

    self_focus_score = _scale(discourse["first_person_ratio"], *RANGES["first_person_ratio"])

    if discourse["hedged_safety"]:
        cues.append("Claims of being fine are immediately contradicted (\"I'm okay, but…\").")

    sub_scores = {
        "escalation": escalation_score,
        "fragmentation": fragmentation_score,
        "rumination": rumination_score,
        "immediacy": immediacy_score,
        "helplessness": helplessness_score,
        "absolutism": absolutism_score,
        "self_focus": self_focus_score,
    }

    weights = dict(SUB_WEIGHTS)
    if not intensity:
        # Without embeddings the trajectory / coherence features are
        # unavailable; redistribute their weight.
        for key in ("escalation", "fragmentation", "rumination"):
            weights.pop(key, None)
        total = sum(weights.values())
        weights = {k: v / total for k, v in weights.items()}

    indicator = sum(sub_scores[k] * w for k, w in weights.items())
    if discourse["hedged_safety"]:
        indicator = min(100.0, indicator + 8.0)

    # Very short statements cannot show discourse structure reliably.
    damp = min(1.0, discourse["word_count"] / 30.0)
    indicator = indicator * damp

    for signal, data in signals.items():
        if data["level"].startswith("window") or data["level"] == "passage":
            pretty = signal.replace("_", " ")
            cues.append(
                f"Reading the passage as a whole indicates {pretty} "
                f"(context similarity {data['similarity']:.2f})."
            )

    return {
        "available": semantic_available,
        "signals": signals,
        "discourse": discourse,
        "indicator": round(max(0.0, min(100.0, indicator)), 1),
        "sub_scores": sub_scores,
        "cues": cues[:8],
        "engine": "context" if semantic_available else "discourse_only",
    }


__all__ = ["analyze_narrative_context", "discourse_features"]
