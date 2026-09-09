from fastapi import APIRouter, HTTPException

from typing import Union

from models.assessment import (
    AssessmentReceipt,
    AssessmentRequest,
    AssessmentResponse,
)
from services.participant_view import to_receipt

from services.assessment_service import assess_text
from services.case_service import (
    create_case,
    get_case,
)
from services.validation_service import (
    validate_case_id,
)


router = APIRouter(
    prefix="/api",
    tags=["Assessment"],
)


@router.post(
    "/assess",
    response_model=Union[AssessmentReceipt, AssessmentResponse],
)
def assess(request: AssessmentRequest):

    if not request.consent:
        raise HTTPException(
            status_code=400,
            detail="Consent is required for assessment.",
        )

    try:
     case_id = validate_case_id(
        request.case_id
    )
    except ValueError as exc:
     raise HTTPException(
        status_code=400,
        detail=str(exc),
    ) from exc

    existing_case = get_case(case_id)

    if existing_case is not None:
        raise HTTPException(
            status_code=409,
            detail="Case already exists.",
        )

    assessment = assess_text(
        case_id=case_id,
        narrative=request.narrative,
        language=request.language,
    )

    create_case(
        case_id=assessment.case_id,
        svi_score=assessment.svi_score,
        risk_level=assessment.risk_level,
        human_review_required=(
            assessment.human_review_required
        ),
        language=assessment.language,
        signals=assessment.signals.model_dump(),
        vulnerability_profile=(
            assessment.vulnerability_profile.model_dump()
        ),
        explanation=assessment.explanation,
        evidence=[
            item.model_dump()
            for item in assessment.evidence
        ],
        recommendations=assessment.recommendations,
        narrative_context=(
            assessment.narrative_context.model_dump()
            if assessment.narrative_context
            else None
        ),
    )
    if not request.narrative.strip():
     raise HTTPException(
        status_code=400,
        detail="narrative is required.",
    )

    # The assessed person only ever receives a receipt.
    if request.participant_view:
        return to_receipt(assessment, capture_mode="text")

    return assessment