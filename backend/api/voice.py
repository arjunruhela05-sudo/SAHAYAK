from __future__ import annotations

from typing import Union

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.assessment import AssessmentReceipt, AssessmentResponse
from services.participant_view import to_receipt

from services.case_service import attach_case_media, get_case

from services.multimodal_service import build_multimodal_assessment

from services.prosody_engine import extract_prosody_features

from services.validation_service import validate_case_id

from services.voice_engine import (
    cleanup_audio,
    extract_acoustic_features,
    save_uploaded_audio,
    transcribe_audio,
    validate_audio,
)


router = APIRouter(
    prefix="/api",
    tags=["Voice"],
)


# =========================================================
# TRANSCRIPTION
# =========================================================

@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
):
    """
    Transcribe an uploaded audio file using Whisper.

    This endpoint only performs speech-to-text.
    It does not create or persist a case.
    """

    file_bytes = await file.read()

    try:
        validate_audio(
            filename=file.filename,
            content_type=file.content_type,
            file_size=len(file_bytes),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    audio_path = None

    try:
        audio_path = save_uploaded_audio(
            file_bytes=file_bytes,
            filename=file.filename,
        )

        result = transcribe_audio(audio_path)

        if not result.get("available"):
            raise HTTPException(
                status_code=503,
                detail=result.get(
                    "error",
                    "Transcription service unavailable.",
                ),
            )

        return {
            "transcript": result.get("text", ""),
            "language": result.get("language", "unknown"),
            "segments": result.get("segments", []),
        }

    finally:
        cleanup_audio(audio_path)


# =========================================================
# AUDIO ASSESSMENT
# =========================================================

@router.post(
    "/assess-audio",
    response_model=Union[AssessmentReceipt, AssessmentResponse],
)
async def assess_audio(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    consent: bool = Form(...),
    language: str = Form("auto"),
    participant_view: bool = Form(False),
):
    """
    Complete multimodal voice assessment pipeline.

    Pipeline:

        Audio
          ↓
        Validation
          ↓
        Whisper transcription
          ↓
        Existing text AI engine          (primary)
          ↓
        Acoustic statistics              (supplementary)
        Prosody: pauses, pitch, breathing,
                 tremor, voice depth     (supplementary)
        Disfluency: fillers, repetition,
                 restarts, hedging       (supplementary)
          ↓
        Multimodal fusion
          ↓
        Final SVI + risk
          ↓
        Persistent case storage
          ↓
        Assessment response
    """

    # 1. Consent
    if not consent:
        raise HTTPException(
            status_code=400,
            detail="Consent is required for audio assessment.",
        )

    # 2. Case ID
    try:
        normalized_case_id = validate_case_id(case_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # 3. Duplicate protection
    if get_case(normalized_case_id) is not None:
        raise HTTPException(
            status_code=409,
            detail=f"Case '{normalized_case_id}' already exists.",
        )

    # 4. Read audio
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Audio file is empty.",
        )

    # 5. Validate
    try:
        validate_audio(
            filename=file.filename,
            content_type=file.content_type,
            file_size=len(file_bytes),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    audio_path = None

    try:
        # 6. Save temp audio
        audio_path = save_uploaded_audio(
            file_bytes=file_bytes,
            filename=file.filename,
        )

        # 7. Transcription
        transcription = transcribe_audio(audio_path)

        if not transcription.get("available"):
            raise HTTPException(
                status_code=503,
                detail=transcription.get(
                    "error",
                    "Transcription service unavailable.",
                ),
            )

        transcript = transcription.get("text", "").strip()

        if not transcript:
            raise HTTPException(
                status_code=422,
                detail="No speech could be transcribed from the audio.",
            )

        detected_language = (
            transcription.get("language")
            or language
            or "unknown"
        )

        # 8. Supplementary voice features
        acoustic_features = extract_acoustic_features(audio_path)
        prosody_features = extract_prosody_features(audio_path)

        # 9. Text engine + fusion + persistence
        assessment = build_multimodal_assessment(
            case_id=normalized_case_id,
            transcript=transcript,
            language=detected_language,
            acoustic_features=acoustic_features,
            prosody_features=prosody_features,
            transcription_segments=transcription.get("segments") or [],
            behavior_payload=None,
            capture_mode="voice",
        )

        attach_case_media(
            normalized_case_id,
            file_bytes,
            file.filename or "recording.webm",
            file.content_type,
        )

        # The assessed person only ever receives a receipt.
        if participant_view:
            return to_receipt(assessment, capture_mode="voice")
        return assessment

    finally:
        cleanup_audio(audio_path)
