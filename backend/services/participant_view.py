"""
Participant view
================

The person being assessed must never see the stress / vulnerability
index, the risk level, the detected cues or the body-movement tracking.
These helpers reduce a full assessment or case record to a receipt that
is safe to show on the participant's own screen.
"""

from __future__ import annotations

from typing import Any, Dict, List

from models.assessment import AssessmentReceipt, AssessmentResponse
from models.case import ParticipantCaseSummary


PARTICIPANT_NEXT_STEPS: List[str] = [
    "An authorised responder will review your statement.",
    "You may be contacted for a follow-up conversation.",
    "If you are in immediate danger, contact local emergency services now.",
]


def to_receipt(assessment: AssessmentResponse, capture_mode: str = "text") -> AssessmentReceipt:
    return AssessmentReceipt(
        case_id=assessment.case_id,
        status="RECEIVED",
        capture_mode=capture_mode,
        language=assessment.language or "unknown",
        human_review_required=True,
        next_steps=list(PARTICIPANT_NEXT_STEPS),
    )


def case_to_participant_summary(case: Dict[str, Any]) -> ParticipantCaseSummary:
    status = str(case.get("status") or "NEW")
    messages = {
        "NEW": "Your statement has been received and is waiting for a reviewer.",
        "UNDER_REVIEW": "Your statement is being reviewed by an authorised responder.",
        "ACTION_REQUIRED": "A responder is acting on your case and may contact you.",
        "RESOLVED": "Your case has been resolved. Thank you for reaching out.",
        "CLOSED": "This case is closed.",
    }
    return ParticipantCaseSummary(
        case_id=str(case.get("case_id")),
        status=status,
        created_at=str(case.get("created_at") or ""),
        updated_at=case.get("updated_at"),
        capture_mode=str(case.get("capture_mode") or "text"),
        human_review_required=bool(case.get("human_review_required", True)),
        message=messages.get(status, messages["NEW"]),
    )


__all__ = ["to_receipt", "case_to_participant_summary", "PARTICIPANT_NEXT_STEPS"]
