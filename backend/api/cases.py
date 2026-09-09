from typing import Optional, Union

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    UploadFile,
)

from fastapi.responses import FileResponse

from models.case import (
    AddTimelineEventRequest,
    Case,
    CaseSummary,
    CreateCaseRequest,
    ParticipantCaseSummary,
    UpdateStatusRequest,
)

from services.participant_view import case_to_participant_summary

from services.case_service import (
    add_timeline_event,
    create_case,
    get_case,
    get_case_media_path,
    list_cases,
    search_cases,
    update_case_status,
    add_case_evidence,
    get_case_evidence_path,
)

from services.validation_service import (
    validate_case_id,
)


router = APIRouter(
    prefix="/api/cases",
    tags=["Cases"],
)


@router.post(
    "",
    response_model=Case,
    status_code=201,
)
def create_new_case(
    request: CreateCaseRequest,
):
    try:
        case_id = validate_case_id(
        request.case_id
    )
    except ValueError as exc:
     raise HTTPException(
        status_code=400,
        detail=str(exc),
    ) from exc
    existing_case = get_case(request.case_id)

    if existing_case is not None:
        raise HTTPException(
            status_code=409,
            detail="Case already exists.",
        )

    case = create_case(
        case_id=case_id,
        svi_score=request.svi_score,
        risk_level=request.risk_level,
        human_review_required=(
            request.human_review_required
        ),
        language=request.language,
        signals=request.signals,
        vulnerability_profile=(
            request.vulnerability_profile
        ),
        explanation=request.explanation,
        evidence=request.evidence,
        recommendations=request.recommendations,
    )

    return case


@router.get(
    "",
    response_model=None,
    responses={200: {"model": list[CaseSummary]}},
)
def get_cases(
    query: Optional[str] = Query(
        default=None,
        max_length=100,
    ),
    risk_level: Optional[str] = Query(
        default=None,
        max_length=20,
    ),
    status: Optional[str] = Query(
        default=None,
        max_length=30,
    ),
    view: Optional[str] = Query(
        default=None,
        max_length=20,
        description="'participant' returns receipt-level summaries without scores.",
    ),
):
    cases = search_cases(
        query=query,
        risk_level=risk_level,
        status=status,
    )

    if (view or "").lower() == "participant":
        ordered = sorted(cases, key=lambda c: str(c.get("created_at") or ""), reverse=True)
        return [case_to_participant_summary(case) for case in ordered]

    return [
    CaseSummary(
        case_id=case["case_id"],
        svi_score=case["svi_score"],
        risk_level=case["risk_level"],
        status=case["status"],
        human_review_required=(
            case["human_review_required"]
        ),
        created_at=case["created_at"],
        has_evidence=bool(
            case.get("submitted_evidence")
        ),
    )
    for case in cases
]


@router.get(
    "/{case_id}",
    response_model=None,
    responses={200: {"model": Case}},
)
def get_case_details(
    case_id: str,
    view: Optional[str] = Query(
        default=None,
        max_length=20,
        description="'participant' returns a receipt-level summary without scores.",
    ),
):
    case = get_case(case_id)

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    if (view or "").lower() == "participant":
        return case_to_participant_summary(case)

    return Case(**case)


@router.get("/{case_id}/media")
def get_case_media(case_id: str):
    case = get_case(case_id)
    if case is None:
        raise HTTPException(status_code=404, detail="Case not found.")

    media = case.get("media") or {}
    path = get_case_media_path(case_id)
    if not media or path is None:
        raise HTTPException(status_code=404, detail="No original media was submitted for this case.")

    return FileResponse(
        path,
        media_type=media.get("content_type") or "application/octet-stream",
        filename=media.get("filename") or path.name,
    )


@router.post("/{case_id}/evidence")
async def upload_case_evidence(
    case_id: str,
    file: UploadFile = File(...),
):
    """Upload additional evidence supplied by the victim."""

    case = get_case(case_id)

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Evidence file is empty.",
        )

    # Maximum 50 MB per file
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Evidence file must be 50 MB or smaller.",
        )

    try:
        return add_case_evidence(
            case_id=case_id,
            file_bytes=file_bytes,
            filename=file.filename or "evidence.bin",
            content_type=file.content_type,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get("/{case_id}/evidence/{evidence_id}")
def get_case_evidence(
    case_id: str,
    evidence_id: str,
):
    case = get_case(case_id)

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    item = next(
        (
            x
            for x in case.get("submitted_evidence") or []
            if str(x.get("id")) == str(evidence_id)
        ),
        None,
    )

    path = get_case_evidence_path(
        case_id,
        evidence_id,
    )

    if item is None or path is None:
        raise HTTPException(
            status_code=404,
            detail="Evidence not found.",
        )

    return FileResponse(
        path,
        media_type=item.get("content_type")
        or "application/octet-stream",
        filename=item.get("filename")
        or path.name,
    )

@router.post(
    "/{case_id}/evidence"
)
async def upload_case_evidence(
    case_id: str,
    file: UploadFile = File(...),
):

    case = get_case(case_id)

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Evidence file is empty.",
        )

    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(
            status_code=413,
            detail="Evidence file must be 50 MB or smaller.",
        )

    try:

        return add_case_evidence(
            case_id=case_id,
            file_bytes=file_bytes,
            filename=(
                file.filename
                or "evidence.bin"
            ),
            content_type=file.content_type,
        )

    except ValueError as exc:

        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc


@router.get(
    "/{case_id}/evidence/{evidence_id}"
)
def get_case_evidence(
    case_id: str,
    evidence_id: str,
):

    case = get_case(case_id)

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    item = next(
        (
            x
            for x in (
                case.get(
                    "submitted_evidence"
                )
                or []
            )
            if str(
                x.get("id")
            ) == str(evidence_id)
        ),
        None,
    )

    path = get_case_evidence_path(
        case_id,
        evidence_id,
    )

    if item is None or path is None:
        raise HTTPException(
            status_code=404,
            detail="Evidence not found.",
        )

    return FileResponse(
        path=str(path),
        media_type=(
            item.get("content_type")
            or "application/octet-stream"
        ),
        filename=(
            item.get("filename")
            or path.name
        ),
    )    

@router.patch(
    "/{case_id}/status",
    response_model=Case,
)
def change_case_status(
    case_id: str,
    request: UpdateStatusRequest,
):
    try:
        case = update_case_status(
            case_id=case_id,
            status=request.status,
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    return case


@router.post(
    "/{case_id}/timeline",
    response_model=Case,
)
def add_case_timeline_event(
    case_id: str,
    request: AddTimelineEventRequest,
):
    case = add_timeline_event(
        case_id=case_id,
        event=request.event,
        description=request.description,
    )

    if case is None:
        raise HTTPException(
            status_code=404,
            detail="Case not found.",
        )

    return case