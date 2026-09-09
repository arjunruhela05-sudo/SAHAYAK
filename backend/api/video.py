from __future__ import annotations

import json
from typing import Union

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from models.assessment import AssessmentReceipt, AssessmentResponse
from models.behavior import BehaviorFeatures

from services.behavior_engine import (
    calculate_behavior_indicator,
    parse_behavior_features,
)

from services.case_service import attach_case_media, get_case

from services.multimodal_service import build_multimodal_assessment

from services.participant_view import to_receipt

from services.prosody_engine import extract_prosody_features

from services.validation_service import validate_case_id

from services.video_behavior_engine import (
    analyze_video_file,
    video_analysis_available,
)

from services.voice_engine import (
    cleanup_audio,
    extract_acoustic_features,
    extract_audio_track,
    save_uploaded_media,
    transcribe_audio,
    validate_media,
)


router = APIRouter(
    prefix="/api",
    tags=["Video"],
)


def _parse_behavior_json(raw: str) -> dict:
    """Decode the behaviour-feature JSON string sent by the browser."""
    try:
        payload = json.loads(raw) if raw else {}
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=400,
            detail="behavior must be a valid JSON object.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=400,
            detail="behavior must be a JSON object.",
        )

    try:
        parse_behavior_features(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid behaviour features: {exc}",
        ) from exc

    return payload


def _behavior_present(payload: dict) -> bool:
    """True when the browser actually tracked something."""
    return bool(payload) and bool(payload.get("available", True)) and int(payload.get("frames_analyzed", 0) or 0) > 0


# =========================================================
# BEHAVIOUR-ONLY SCORING (no case created)
# =========================================================

@router.post("/behavior-score")
async def behavior_score(features: BehaviorFeatures):
    """
    Score body-language features without creating a case.

    Used by the responder-side live view.  Nothing is persisted, and the
    participant-facing recorder never calls this.
    """
    return calculate_behavior_indicator(features)


@router.get("/video-capabilities")
def video_capabilities():
    """Whether uploaded video files can be analysed for body language on the server."""
    return {
        "server_footage_analysis": video_analysis_available(),
        "browser_tracking": True,
        "tracker": "v6",
    }


# =========================================================
# VIDEO ASSESSMENT
# =========================================================

@router.post(
    "/assess-video",
    response_model=Union[AssessmentReceipt, AssessmentResponse],
)
async def assess_video(
    file: UploadFile = File(...),
    case_id: str = Form(...),
    consent: bool = Form(...),
    behavior: str = Form("{}"),
    language: str = Form("auto"),
    analyze_footage: str = Form("auto"),
    participant_view: bool = Form(False),
):
    """
    Complete audio + body-language assessment pipeline.

    Two ways in:

    * **Live capture** — the browser records the microphone and runs the
      MediaPipe trackers on the camera feed.  It uploads the audio plus
      ``behavior`` (aggregated cues).  The video never leaves the device.
    * **Video file** — a recorded video is uploaded.  The audio track is
      extracted and the *footage* is analysed on the server for the same
      cues (blinking, eye contact, self-soothing gestures, muscle
      tension, swallowing, posture …).  Frames are processed in memory
      and never stored.

    ``analyze_footage``: ``auto`` (default) analyses the footage when the
    upload is a video and no browser cues were supplied; ``always`` /
    ``never`` force it.

    ``participant_view``: when true (request from the assessed person's
    own screen) the response is a receipt with no score, risk level, cue
    or tracking data.

    Pipeline:

        Media ──► validation ──► audio track (+ footage)
                                    ↓
                           Whisper transcription
                                    ↓
                Text AI engine + whole-passage context (primary)
                                    ↓
          Acoustic + prosody + tone + disfluency (voice, supplementary)
          Behaviour engine                        (video, supplementary)
                                    ↓
                           Multimodal fusion
                                    ↓
                     Final SVI + risk + explanation
                                    ↓
                             Case persistence
    """

    # 1. Consent
    if not consent:
        raise HTTPException(
            status_code=400,
            detail="Consent is required for video assessment.",
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

    # 4. Behaviour features from the browser (may be empty)
    behavior_payload = _parse_behavior_json(behavior)

    # 5. Read media
    file_bytes = await file.read()

    if not file_bytes:
        raise HTTPException(
            status_code=400,
            detail="Media file is empty.",
        )

    try:
        media_kind = validate_media(
            filename=file.filename,
            content_type=file.content_type,
            file_size=len(file_bytes),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    footage_mode = (analyze_footage or "auto").strip().lower()
    if footage_mode not in {"auto", "always", "never"}:
        raise HTTPException(status_code=400, detail="analyze_footage must be auto, always or never.")

    media_path = None
    audio_path = None

    try:
        # 6. Save + (if video) extract the audio track
        media_path = save_uploaded_media(
            file_bytes=file_bytes,
            filename=file.filename,
        )

        audio_path = (
            extract_audio_track(media_path)
            if media_kind == "video"
            else media_path
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
                detail="No speech could be transcribed from the recording.",
            )

        detected_language = (
            transcription.get("language")
            or language
            or "unknown"
        )

        # 8. Supplementary voice features (whole recording)
        acoustic_features = extract_acoustic_features(audio_path)
        prosody_features = extract_prosody_features(audio_path)

        # 9. Body language from the footage (server side) when the
        #    browser did not track it — or when explicitly requested.
        want_footage = media_kind == "video" and (
            footage_mode == "always"
            or (footage_mode == "auto" and not _behavior_present(behavior_payload))
        )
        if want_footage:
            footage = analyze_video_file(media_path)
            if footage.get("available"):
                behavior_payload = footage
            elif not _behavior_present(behavior_payload):
                behavior_payload = {
                    "available": False,
                    "extras": {"footage_error": footage.get("error", "unavailable")},
                }

        # 10. Text engine + behaviour + fusion + persistence
        assessment = build_multimodal_assessment(
            case_id=normalized_case_id,
            transcript=transcript,
            language=detected_language,
            acoustic_features=acoustic_features,
            prosody_features=prosody_features,
            transcription_segments=transcription.get("segments") or [],
            behavior_payload=behavior_payload,
            capture_mode="video",
        )

        attach_case_media(
            normalized_case_id,
            file_bytes,
            file.filename or "recording.webm",
            file.content_type,
        )

        # The assessed person only ever receives a receipt.
        if participant_view:
            return to_receipt(assessment, capture_mode="video")
        return assessment

    finally:
        if audio_path and audio_path != media_path:
            cleanup_audio(audio_path)
        cleanup_audio(media_path)
