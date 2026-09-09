from __future__ import annotations

from typing import Any

from services.case_service import list_cases


RISK_LEVELS = [
    "CRITICAL",
    "HIGH",
    "MODERATE",
    "LOW",
]


STATUSES = [
    "NEW",
    "UNDER_REVIEW",
    "ACTION_REQUIRED",
    "RESOLVED",
    "CLOSED",
]


SIGNALS = [
    "fear",
    "immediate_threat",
    "distress",
    "isolation",
    "intimidation",
    "self_harm",
]


def get_overview() -> dict[str, Any]:
    """Return high-level case statistics."""

    cases = list_cases()

    total_cases = len(cases)

    if total_cases:
        average_svi = round(
            sum(
                float(case.get("svi_score", 0))
                for case in cases
            )
            / total_cases,
            1,
        )
    else:
        average_svi = 0.0

    human_review_count = sum(
        1
        for case in cases
        if case.get(
            "human_review_required",
            False,
        )
    )

    return {
        "total_cases": total_cases,
        "average_svi": average_svi,
        "human_review_required": human_review_count,
    }


def get_risk_distribution() -> dict[str, int]:
    """Return the number of cases for each risk level."""

    cases = list_cases()

    distribution = {
        level: 0
        for level in RISK_LEVELS
    }

    for case in cases:
        risk_level = str(
            case.get(
                "risk_level",
                "",
            )
        ).upper()

        if risk_level in distribution:
            distribution[risk_level] += 1

    return distribution


def get_status_distribution() -> dict[str, int]:
    """Return the number of cases for each status."""

    cases = list_cases()

    distribution = {
        status: 0
        for status in STATUSES
    }

    for case in cases:
        status = str(
            case.get(
                "status",
                "",
            )
        ).upper()

        if status in distribution:
            distribution[status] += 1

    return distribution


def get_signal_frequency() -> dict[str, int]:
    """Return how frequently each signal is elevated."""

    cases = list_cases()

    frequency = {
        signal: 0
        for signal in SIGNALS
    }

    for case in cases:
        signals = case.get(
            "signals",
            {},
        ) or {}

        for signal in SIGNALS:
            score = float(
                signals.get(
                    signal,
                    0,
                )
            )

            if score >= 25:
                frequency[signal] += 1

    return frequency


def get_svi_statistics() -> dict[str, float]:
    """Return basic SVI statistics."""

    cases = list_cases()

    if not cases:
        return {
            "average": 0.0,
            "minimum": 0.0,
            "maximum": 0.0,
        }

    scores = [
        float(
            case.get(
                "svi_score",
                0,
            )
        )
        for case in cases
    ]

    return {
        "average": round(
            sum(scores) / len(scores),
            1,
        ),
        "minimum": round(
            min(scores),
            1,
        ),
        "maximum": round(
            max(scores),
            1,
        ),
    }


def get_all_analytics() -> dict[str, Any]:
    """Return the complete analytics summary."""

    return {
        "overview": get_overview(),
        "risk_distribution": (
            get_risk_distribution()
        ),
        "status_distribution": (
            get_status_distribution()
        ),
        "signal_frequency": (
            get_signal_frequency()
        ),
        "svi": get_svi_statistics(),
    }