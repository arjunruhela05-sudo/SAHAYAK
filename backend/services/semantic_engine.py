"""Semantic NLP layer for SAHAYAK.

Uses a multilingual Sentence Transformer to compare narrative sentences
against signal descriptions. This is a decision-support prototype, not a
clinical classifier or diagnosis engine.
"""

from __future__ import annotations

import os
import re
from functools import lru_cache
from typing import Dict, List, Tuple

MODEL_NAME = os.getenv(
    "SAHAYAK_SEMANTIC_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)
SEMANTIC_ENABLED = os.getenv(
    "SAHAYAK_SEMANTIC_ENABLED",
    "true",
).strip().lower() in {"1", "true", "yes", "on"}

# Thresholds are engineering thresholds for this prototype. They must be
# validated on representative, consented data before any real deployment.
SEMANTIC_THRESHOLD = float(
    os.getenv("SAHAYAK_SEMANTIC_THRESHOLD", "0.55")
)

SIGNAL_PROTOTYPES: Dict[str, List[str]] = {
    "fear": [
        "The person feels afraid, frightened, scared, or unsafe.",
        "The victim is fearful for their own safety.",
        "मुझे डर लग रहा है और मैं अपनी सुरक्षा को लेकर डरी हुई हूँ।",
        "मुझे अपनी safety को लेकर डर लग रहा है।",
        "Mujhe bahut darr lag raha hai aur main safe feel nahi kar raha hoon.",
        "Mujhe ghar jaane mein darr lagta hai.",
    ],
    "immediate_threat": [
        "Someone is threatening to kill or seriously hurt the victim or their family.",
        "The victim is currently in danger because another person has threatened them.",
        "A person who threatened the victim is nearby or may attack them now.",
        "The victim has received a death threat or threat of serious violence.",
        "कोई व्यक्ति मुझे या मेरे परिवार को जान से मारने की धमकी दे रहा है।",
        "मुझे जान से मारने की धमकी मिल रही है और मुझे अभी खतरा है।",
        "Mujhe jaan se maarne ki dhamki mil rahi hai.",
        "Woh mujhe aur meri family ko maarne ki dhamki de raha hai.",
        "Jo aadmi mujhe dhamki de raha hai woh abhi mere paas hai.",
    ],
    "distress": [
        "The victim feels helpless, overwhelmed, hopeless, panicked, or unable to cope.",
        "The person is experiencing severe emotional distress because of what happened.",
        "मुझे बहुत परेशानी, घबराहट या बेबसी महसूस हो रही है।",
        "मैं बहुत परेशान हूँ और समझ नहीं आ रहा क्या करूँ।",
        "Main bahut pareshan hoon aur mujhe samajh nahi aa raha kya karun.",
        "Main bilkul helpless feel kar raha hoon.",
    ],
    "isolation": [
        "The victim is isolated, alone, cut off from family or friends, or has nobody to turn to.",
        "The person has no social or family support and feels alone.",
        "मुझे मेरे परिवार से अलग कर दिया गया है और मेरा कोई सहारा नहीं है।",
        "मेरी मदद करने वाला कोई नहीं है।",
        "Mujhe meri family se alag kar diya gaya hai.",
        "Mera support karne wala koi nahi hai.",
    ],
    "intimidation": [
        "Another person is intimidating, coercing, controlling, blackmailing, or pressuring the victim.",
        "The victim is being forced or warned not to complain or speak up.",
        "कोई मुझे डरा धमका कर चुप रहने के लिए मजबूर कर रहा है।",
        "मुझ पर शिकायत वापस लेने का दबाव बनाया जा रहा है।",
        "Mujhe complaint wapas lene ke liye pressure kiya ja raha hai.",
        "Woh mujhe dara dhamka kar chup rehne ko keh rahe hain.",
    ],
    "self_harm": [
        "The victim is thinking about suicide, dying, or hurting themselves.",
        "The person says they want to die or no longer want to live.",
        "मुझे मरने या खुद को नुकसान पहुंचाने के विचार आ रहे हैं।",
        "मेरा जीने का मन नहीं कर रहा है।",
        "Mujhe marne ka mann kar raha hai ya main khud ko hurt karna chahta hoon.",
    ],
}

SIGNAL_NEGATION_PATTERNS = {
    "fear": [
        r"\bnot afraid\b", r"\bnot scared\b", r"\bnot frightened\b",
        r"\bdo not fear\b", r"\bdon['’]?t fear\b",
        r"\bnot unsafe\b", r"\bfeel safe\b",
        r"\bdarr nahi\b", r"\bdar nahi\b", r"\bkhauf nahi\b",
    ],
    "immediate_threat": [
        r"\bnot threatened\b", r"\bno threat\b", r"\bno immediate threat\b",
        r"\bno immediate danger\b", r"\bnot in danger\b",
        r"\bno danger\b", r"\bnot being threatened\b",
        r"\bkoi dhamki nahi\b", r"\bkoi khatra nahi\b", r"\bkoi danger nahi\b",
    ],
    "distress": [
        r"\bnot helpless\b", r"\bnot hopeless\b", r"\bnot overwhelmed\b",
        r"\bnot distressed\b", r"\bnot anxious\b",
        r"\bpareshan nahi\b", r"\bghabrahat nahi\b", r"\bbehal nahi\b",
    ],
    "isolation": [
        r"\bnot alone\b", r"\bnot isolated\b", r"\bnot cut off\b",
        r"\bnot separated\b", r"\bnot without support\b",
        r"\bakela nahi\b", r"\bakeli nahi\b", r"\bakela nahin\b",
    ],
    "intimidation": [
        r"\bnot intimidated\b", r"\bnot being forced\b",
        r"\bnot being pressured\b", r"\bnot controlled\b",
        r"\bdhamkaya nahi\b", r"\bpressure nahi\b",
    ],
    "self_harm": [
        r"\bdo not want to die\b", r"\bdon['’]?t want to die\b",
        r"\bdo not want to hurt myself\b", r"\bdon['’]?t want to hurt myself\b",
        r"\bnot suicidal\b", r"\bnot thinking about suicide\b",
        r"\bjeena nahi chhodna\b",
    ],
}


def split_sentences(text: str) -> List[str]:
    """Split English/Hindi/Hinglish narratives into short evidence units."""
    normalized = re.sub(r"\s+", " ", text.strip())
    if not normalized:
        return []
    parts = re.split(r"(?<=[.!?।])\s+|\n+|;\s*", normalized)
    return [part.strip(" \t\"'") for part in parts if part.strip()]


def is_signal_negated(sentence: str, signal: str) -> bool:
    """Check negation against the specific signal, not any word like ``not``."""
    lowered = sentence.lower().replace("’", "'")
    return any(
        re.search(pattern, lowered)
        for pattern in SIGNAL_NEGATION_PATTERNS.get(signal, [])
    )


def detect_language(text: str) -> str:
    """Lightweight language routing for English, Hindi and Hinglish."""
    if re.search(r"[\u0900-\u097F]", text):
        # Mixed Devanagari + Latin is treated as Hindi for this prototype.
        latin_words = re.findall(r"\b[a-zA-Z]{2,}\b", text)
        devanagari_chars = len(re.findall(r"[\u0900-\u097F]", text))
        if latin_words and devanagari_chars:
            return "hi"
        return "hi"

    lowered = text.lower()
    hinglish_markers = {
        "mujhe", "mujh", "mera", "meri", "mere", "hum", "ham",
        "hai", "hain", "hoon", "hu", "nahi", "nahin", "darr",
        "dar", "maar", "marna", "maarne", "dhamki", "ghar", "family",
        "log", "raha", "rahi", "rahe", "bahut", "pareshan", "akela",
        "akeli", "madad", "sahara", "complaint", "kar", "karne",
    }
    words = set(re.findall(r"\b[a-zA-Z]+\b", lowered))
    marker_hits = len(words & hinglish_markers)

    if marker_hits >= 2:
        return "hinglish"

    return "en"


@lru_cache(maxsize=1)
def load_semantic_model():
    """Load the multilingual embedding model once per backend process."""
    if not SEMANTIC_ENABLED:
        return None

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise RuntimeError(
            "Semantic NLP requires sentence-transformers. "
            "Run: pip install -U sentence-transformers"
        ) from exc

    return SentenceTransformer(MODEL_NAME)


@lru_cache(maxsize=1)
def prototype_embeddings():
    model = load_semantic_model()
    if model is None:
        return None

    flat = []
    for signal, prototypes in SIGNAL_PROTOTYPES.items():
        for prototype in prototypes:
            flat.append((signal, prototype))

    texts = [item[1] for item in flat]
    embeddings = model.encode(
        texts,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    grouped: Dict[str, List[Tuple[str, object]]] = {}
    for (signal, prototype), embedding in zip(flat, embeddings):
        grouped.setdefault(signal, []).append((prototype, embedding))
    return grouped


def semantic_detect(text: str) -> Dict[str, dict]:
    """Run multilingual semantic similarity over sentence-level evidence."""
    model = load_semantic_model()
    grouped = prototype_embeddings()
    if model is None or grouped is None:
        return {}

    sentences = split_sentences(text)
    if not sentences:
        return {}

    sentence_embeddings = model.encode(
        sentences,
        normalize_embeddings=True,
        convert_to_numpy=True,
        show_progress_bar=False,
    )

    results: Dict[str, dict] = {}

    for signal, prototypes in grouped.items():
        evidence: List[Tuple[str, float]] = []

        for sentence, sentence_embedding in zip(sentences, sentence_embeddings):
            if is_signal_negated(sentence, signal):
                continue

            best_similarity = max(
                float(sentence_embedding @ prototype_embedding)
                for _, prototype_embedding in prototypes
            )

            if best_similarity >= SEMANTIC_THRESHOLD:
                evidence.append((sentence, best_similarity))

        evidence.sort(key=lambda item: item[1], reverse=True)

        unique_evidence = []
        seen = set()
        for sentence, similarity in evidence:
            key = sentence.lower()
            if key not in seen:
                seen.add(key)
                unique_evidence.append((sentence, similarity))

        if unique_evidence:
            best = unique_evidence[0][1]
            if best >= 0.78:
                score = 90.0
            elif best >= 0.70:
                score = 80.0
            elif best >= 0.62:
                score = 65.0
            else:
                score = 40.0

            score += min(20.0, max(0, len(unique_evidence) - 1) * 10.0)
            score = min(score, 90.0)

            results[signal] = {
                "matches": [item[0] for item in unique_evidence[:3]],
                "match_count": len(unique_evidence),
                "semantic_score": round(score, 1),
                "semantic_similarity": round(best, 3),
                "engine": "semantic",
            }

    return results
