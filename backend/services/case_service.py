from __future__ import annotations
import uuid
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from functools import cmp_to_key

# =========================================================
# STORAGE
# =========================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
CASES_FILE = DATA_DIR / "cases.json"
MEDIA_DIR = DATA_DIR / "media"
EVIDENCE_DIR = DATA_DIR / "evidence"


# =========================================================
# STATUS VALUES
# =========================================================

ALLOWED_STATUSES = {
    "NEW",
    "UNDER_REVIEW",
    "ACTION_REQUIRED",
    "RESOLVED",
    "CLOSED",
}

# Valid workflow transitions.
#
# CLOSED is terminal.
# A case can move forward/back into review where operationally
# appropriate, but once RESOLVED it must be CLOSED.
ALLOWED_TRANSITIONS = {
    "NEW": {
        "UNDER_REVIEW",
        "ACTION_REQUIRED",
        "CLOSED",
    },
    "UNDER_REVIEW": {
        "ACTION_REQUIRED",
        "RESOLVED",
        "CLOSED",
    },
    "ACTION_REQUIRED": {
        "UNDER_REVIEW",
        "RESOLVED",
        "CLOSED",
    },
    "RESOLVED": {
        "CLOSED",
    },
    "CLOSED": set(),
}


# Risk priority used by the case queue.
RISK_PRIORITY = {
    "CRITICAL": 0,
    "HIGH": 1,
    "MODERATE": 2,
    "LOW": 3,
}


# =========================================================
# HELPERS
# =========================================================

def utc_now() -> str:
    """
    Return current UTC timestamp in ISO-8601 format.
    """
    return datetime.now(timezone.utc).isoformat()


def ensure_storage() -> None:
    """
    Make sure the data directory and cases file exist.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

    if not CASES_FILE.exists():
        CASES_FILE.write_text(
            "[]",
            encoding="utf-8",
        )


def load_cases() -> List[Dict[str, Any]]:
    """
    Load all persisted cases from cases.json.
    """
    ensure_storage()

    try:
        raw = CASES_FILE.read_text(
            encoding="utf-8"
        ).strip()

        if not raw:
            return []

        data = json.loads(raw)

        if not isinstance(data, list):
            return []

        return data

    except (
        json.JSONDecodeError,
        OSError,
    ):
        return []


def save_cases(
    cases: List[Dict[str, Any]],
) -> None:
    """
    Persist all cases to cases.json.
    """
    ensure_storage()

    CASES_FILE.write_text(
        json.dumps(
            cases,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# =========================================================
# IN-MEMORY CASE COLLECTION
# =========================================================

CASES: List[Dict[str, Any]] = load_cases()


# =========================================================
# CASE LOOKUP
# =========================================================

def find_case(
    case_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Find a case by case ID.
    """
    normalized = str(case_id).strip()

    for case in CASES:
        if case.get("case_id") == normalized:
            return case

    return None


def get_case(
    case_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Public case lookup function.
    """
    return find_case(case_id)


# =========================================================
# CASE LISTING / SEARCH
# =========================================================

def _sort_cases(
    cases: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Sort cases by SVI score.

    Highest SVI is the main priority.

    If an evidence case is within 3 SVI points
    of a higher-scoring non-evidence case, the
    evidence case is moved above that nearby case.

    Example:
        93  no evidence
        92  evidence
        85  no evidence

    Result:
        92  evidence
        93  no evidence
        85  no evidence
    """

    # First: highest SVI score
    ordered = sorted(
        cases,
        key=lambda case: float(
            case.get("svi_score") or 0
        ),
        reverse=True,
    )

    EVIDENCE_RANGE = 3

    i = 1

    while i < len(ordered):

        current = ordered[i]

        has_evidence = bool(
            current.get("submitted_evidence")
        )

        if not has_evidence:
            i += 1
            continue

        current_svi = float(
            current.get("svi_score") or 0
        )

        # Look upward for the nearest higher-SVI
        # non-evidence case.
        j = i - 1

        while j >= 0:

            previous = ordered[j]

            previous_has_evidence = bool(
                previous.get("submitted_evidence")
            )

            previous_svi = float(
                previous.get("svi_score") or 0
            )

            difference = (
                previous_svi - current_svi
            )

            # Stop if the SVI gap is too large.
            if difference > EVIDENCE_RANGE:
                break

            # Move the evidence case above a nearby
            # non-evidence case.
            if not previous_has_evidence:

                ordered[j], ordered[j + 1] = (
                    ordered[j + 1],
                    ordered[j],
                )

                j -= 1
                continue

            j -= 1

        i += 1

    return ordered
def get_cases(
    risk: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Return persisted cases with optional filtering.

    Results are always ordered by risk priority:
    CRITICAL → HIGH → MODERATE → LOW.
    """

    cases = list(CASES)

    # -----------------------------------------------------
    # Risk filter
    # -----------------------------------------------------

    if risk:
        risk_value = risk.strip().upper()

        cases = [
            case
            for case in cases
            if str(
                case.get(
                    "risk_level",
                    "",
                )
            ).upper() == risk_value
        ]

    # -----------------------------------------------------
    # Status filter
    # -----------------------------------------------------

    if status:
        status_value = status.strip().upper()

        cases = [
            case
            for case in cases
            if str(
                case.get(
                    "status",
                    "",
                )
            ).upper() == status_value
        ]

    # -----------------------------------------------------
    # Search
    # -----------------------------------------------------

    if search:
        query = search.strip().lower()

        cases = [
            case
            for case in cases
            if (
                query
                in str(
                    case.get(
                        "case_id",
                        "",
                    )
                ).lower()
            )
            or (
                query
                in str(
                    case.get(
                        "language",
                        "",
                    )
                ).lower()
            )
            or (
                query
                in str(
                    case.get(
                        "risk_level",
                        "",
                    )
                ).lower()
            )
        ]

    return _sort_cases(cases)


def list_cases(
    risk: Optional[str] = None,
    status: Optional[str] = None,
    search: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Backward-compatible alias used by the API layer.
    """
    return get_cases(
        risk=risk,
        status=status,
        search=search,
    )


def search_cases(
    query: Optional[str] = None,
    risk_level: Optional[str] = None,
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Compatibility wrapper used by the API layer.

    Supports:
    - text search
    - risk-level filtering
    - status filtering
    """

    return get_cases(
        risk=risk_level,
        status=status,
        search=query,
    )


# =========================================================
# TIMELINE
# =========================================================

def add_timeline_event(
    case_id: str,
    event: str,
    description: Optional[str] = None,
    status: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Add an event to a case timeline.

    The function accepts a case ID rather than a case dictionary
    so the service/API contract remains consistent.
    """

    case = find_case(case_id)

    if case is None:
        raise KeyError(
            f"Case '{case_id}' not found."
        )

    timestamp = utc_now()

    timeline_event: Dict[str, Any] = {
        "event": event,
        "timestamp": timestamp,
        "description": description,
    }

    if status is not None:
        timeline_event["status"] = status

    case.setdefault(
        "timeline",
        [],
    ).append(
        timeline_event
    )

    case["updated_at"] = timestamp

    return case


def get_case_timeline(
    case_id: str,
) -> Optional[Dict[str, Any]]:
    """
    Return timeline information for a case.
    """

    case = find_case(case_id)

    if case is None:
        return None

    return {
        "case_id": case_id,
        "timeline": case.get(
            "timeline",
            [],
        ),
    }


# =========================================================
# CASE SUBMISSION MEDIA
# =========================================================

def attach_case_media(
    case_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist the original victim recording and attach safe metadata to the case."""
    case = find_case(case_id)
    if case is None:
        raise KeyError(f"Case '{case_id}' not found.")
    if not file_bytes:
        raise ValueError("Media file is empty.")

    safe_name = Path(filename or "submission.bin").name
    extension = Path(safe_name).suffix.lower()
    stored_name = f"{case_id}{extension}"
    target = MEDIA_DIR / stored_name
    target.write_bytes(file_bytes)

    kind = "video" if (content_type or "").lower().startswith("video/") else "audio"
    case["media"] = {
        "kind": kind,
        "filename": safe_name,
        "stored_name": stored_name,
        "content_type": content_type or ("video/webm" if kind == "video" else "audio/webm"),
        "size": len(file_bytes),
        "url": f"/api/cases/{case_id}/media",
    }
    case["updated_at"] = utc_now()
    save_cases(CASES)
    return case

def add_case_evidence(
    case_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:

    case = find_case(case_id)

    if case is None:
        raise KeyError(
            f"Case '{case_id}' not found."
        )

    if not file_bytes:
        raise ValueError(
            "Evidence file is empty."
        )

    safe_name = Path(
        filename or "evidence.bin"
    ).name

    import uuid

    evidence_id = uuid.uuid4().hex

    extension = Path(
        safe_name
    ).suffix.lower()

    stored_name = (
        f"{case_id}-{evidence_id}{extension}"
    )

    target = EVIDENCE_DIR / stored_name

    target.write_bytes(file_bytes)

    timestamp = utc_now()

    item = {
        "id": evidence_id,
        "filename": safe_name,
        "stored_name": stored_name,
        "content_type": (
            content_type
            or "application/octet-stream"
        ),
        "size": len(file_bytes),
        "created_at": timestamp,
        "url": (
            f"/api/cases/{case_id}/"
            f"evidence/{evidence_id}"
        ),
    }

    case.setdefault(
        "submitted_evidence",
        []
    ).append(item)

    case["updated_at"] = timestamp

    save_cases(CASES)

    return item


def get_case_evidence_path(
    case_id: str,
    evidence_id: str,
) -> Optional[Path]:

    case = find_case(case_id)

    if case is None:
        return None

    for item in (
        case.get("submitted_evidence")
        or []
    ):

        if str(
            item.get("id")
        ) == str(evidence_id):

            stored_name = Path(
                str(
                    item.get(
                        "stored_name",
                        "",
                    )
                )
            ).name

            path = (
                EVIDENCE_DIR /
                stored_name
            )

            if path.exists():
                return path

    return None
def get_case_media_path(case_id: str) -> Optional[Path]:
    case = find_case(case_id)
    if case is None:
        return None
    media = case.get("media") or {}
    stored_name = media.get("stored_name")
    if stored_name:
        path = MEDIA_DIR / Path(stored_name).name
    else:
        extension = Path(str(media.get("filename") or "")).suffix.lower()
        path = MEDIA_DIR / f"{case_id}{extension}"
    return path if path.exists() else None

def add_case_evidence(
    case_id: str,
    file_bytes: bytes,
    filename: str,
    content_type: Optional[str] = None,
) -> Dict[str, Any]:
    """Store an additional victim-supplied evidence file on a case."""

    case = find_case(case_id)

    if case is None:
        raise KeyError(f"Case '{case_id}' not found.")

    if not file_bytes:
        raise ValueError("Evidence file is empty.")

    safe_name = Path(filename or "evidence.bin").name
    evidence_id = uuid.uuid4().hex

    extension = Path(safe_name).suffix.lower()
    stored_name = f"{case_id}-{evidence_id}{extension}"

    target = EVIDENCE_DIR / stored_name
    target.write_bytes(file_bytes)

    timestamp = utc_now()

    item = {
        "id": evidence_id,
        "filename": safe_name,
        "stored_name": stored_name,
        "content_type": content_type or "application/octet-stream",
        "size": len(file_bytes),
        "created_at": timestamp,
        "url": f"/api/cases/{case_id}/evidence/{evidence_id}",
    }

    case.setdefault("submitted_evidence", []).append(item)
    case["updated_at"] = timestamp

    save_cases(CASES)

    return item


def get_case_evidence_path(
    case_id: str,
    evidence_id: str,
) -> Optional[Path]:

    case = find_case(case_id)

    if case is None:
        return None

    for item in case.get("submitted_evidence") or []:

        if str(item.get("id")) == str(evidence_id):

            stored_name = Path(
                str(item.get("stored_name") or "")
            ).name

            path = EVIDENCE_DIR / stored_name

            return path if path.exists() else None

    return None
# =========================================================
# CREATE CASE
# =========================================================

def create_case(
    case_id: str,
    svi_score: float,
    risk_level: str,
    human_review_required: bool,
    language: Optional[str] = None,
    signals: Optional[Dict[str, Any]] = None,
    vulnerability_profile: Optional[Dict[str, Any]] = None,
    explanation: Optional[List[str]] = None,
    evidence: Optional[List[Dict[str, Any]]] = None,
    recommendations: Optional[List[str]] = None,
    capture_mode: str = "text",
    modalities: Optional[Dict[str, Any]] = None,
    voice_analysis: Optional[Dict[str, Any]] = None,
    behavior_analysis: Optional[Dict[str, Any]] = None,
    narrative_context: Optional[Dict[str, Any]] = None,
    transcript: Optional[str] = None,
    narrative: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Create and persist a new SAHAYAK case.

    The case begins with exactly one timeline event:
    "Case received".

    ``capture_mode`` records which channels were captured
    ("text", "voice" or "video"); ``modalities`` keeps the transparent
    fusion breakdown and ``voice_analysis`` / ``behavior_analysis`` the
    numeric feature summaries for audit.  Raw audio/video is never stored.
    """

    normalized_case_id = str(
        case_id
    ).strip()

    if not normalized_case_id:
        raise ValueError(
            "case_id is required."
        )

    # -----------------------------------------------------
    # Duplicate protection
    # -----------------------------------------------------

    existing = find_case(
        normalized_case_id
    )

    if existing is not None:
        raise ValueError(
            f"Case '{normalized_case_id}' already exists."
        )

    # -----------------------------------------------------
    # Normalize SVI score
    # -----------------------------------------------------

    try:
        score = float(svi_score)
    except (
        TypeError,
        ValueError,
    ) as exc:
        raise ValueError(
            "Invalid SVI score."
        ) from exc

    score = max(
        0.0,
        min(
            100.0,
            score,
        ),
    )

    # -----------------------------------------------------
    # Normalize risk
    # -----------------------------------------------------

    normalized_risk = str(
        risk_level
    ).strip().upper()

    if normalized_risk not in {
        "LOW",
        "MODERATE",
        "HIGH",
        "CRITICAL",
    }:
        raise ValueError(
            "Invalid risk level."
        )

    now = utc_now()

    # -----------------------------------------------------
    # Case record
    # -----------------------------------------------------

    record: Dict[str, Any] = {
        "case_id": normalized_case_id,
        "svi_score": round(
            score,
            1,
        ),
        "risk_level": normalized_risk,
        "status": "NEW",
        "human_review_required": bool(
            human_review_required
        ),
        "created_at": now,
        "updated_at": now,
        "language": language,
        "signals": signals or {},
        "vulnerability_profile": (
            vulnerability_profile or {}
        ),
        "explanation": explanation or [],
        "evidence": evidence or [],
        "recommendations": recommendations or [],
        "capture_mode": capture_mode,
        "modalities": modalities,
        "voice_analysis": voice_analysis,
        "behavior_analysis": behavior_analysis,
        "narrative_context": narrative_context,
        "transcript": transcript,
        "narrative": narrative,
        "media": None,
        "submitted_evidence": [],
        "timeline": [],
    }

    # -----------------------------------------------------
    # Initial timeline
    # -----------------------------------------------------

    # IMPORTANT:
    # Only one initial event is created.
    # The tests and frontend expect a newly created case
    # to start with a single "Case received" event.
    record["timeline"].append(
    {
        "event": "CASE_CREATED",
        "timestamp": now,
        "description": (
            "Assessment case created and "
            "stored for authorized human review."
        ),
    }
)

    # -----------------------------------------------------
    # Save newest cases first
    # -----------------------------------------------------

    CASES.insert(
        0,
        record,
    )

    save_cases(CASES)

    return record


# =========================================================
# UPDATE STATUS
# =========================================================

def update_case_status(
    case_id: str,
    status: str,
) -> Dict[str, Any]:
    """
    Update the workflow status of a case.

    Invalid workflow transitions raise ValueError.
    Missing cases raise KeyError.
    """

    case = find_case(case_id)

    if case is None:
        raise KeyError(
            f"Case '{case_id}' not found."
        )

    normalized_status = str(
        status
    ).strip().upper()

    if normalized_status not in ALLOWED_STATUSES:
        raise ValueError(
            "Invalid case status."
        )

    previous_status = str(
        case.get(
            "status",
            "NEW",
        )
    ).strip().upper()

    # -----------------------------------------------------
    # No-op transition
    # -----------------------------------------------------

    if normalized_status == previous_status:
        return case

    # -----------------------------------------------------
    # Validate workflow transition
    # -----------------------------------------------------

    allowed_next_statuses = ALLOWED_TRANSITIONS.get(
        previous_status,
        set(),
    )

    if normalized_status not in allowed_next_statuses:
        raise ValueError(
            f"Invalid status transition: "
            f"{previous_status} -> {normalized_status}."
        )

    # -----------------------------------------------------
    # Update case
    # -----------------------------------------------------

    timestamp = utc_now()

    case["status"] = normalized_status
    case["updated_at"] = timestamp

    case.setdefault(
        "timeline",
        [],
    ).append(
        {
            "event": "Status updated",
            "timestamp": timestamp,
            "description": (
                f"Case status changed from "
                f"{previous_status} to "
                f"{normalized_status}."
            ),
            "status": normalized_status,
        }
    )

    save_cases(CASES)

    return case


# =========================================================
# DELETE / RESET SUPPORT
# =========================================================

def delete_case(
    case_id: str,
) -> bool:
    """
    Delete a case from persistent storage.

    This is kept as a service-level utility.
    The current frontend/API contract does not expose
    a delete endpoint.
    """

    case = find_case(case_id)

    if case is None:
        return False

    CASES.remove(case)

    save_cases(CASES)

    return True


def clear_cases() -> None:
    """
    Clear all persisted cases.

    Intended primarily for development/testing.
    """

    CASES.clear()

    save_cases(CASES)


# =========================================================
# ANALYTICS HELPERS
# =========================================================

def get_case_statistics() -> Dict[str, Any]:
    """
    Return basic case statistics for analytics services.
    """

    total_cases = len(CASES)

    risk_distribution = {
        "CRITICAL": 0,
        "HIGH": 0,
        "MODERATE": 0,
        "LOW": 0,
    }

    status_distribution = {
        "NEW": 0,
        "UNDER_REVIEW": 0,
        "ACTION_REQUIRED": 0,
        "RESOLVED": 0,
        "CLOSED": 0,
    }

    svi_values: List[float] = []
    human_review_required = 0

    for case in CASES:

        # -------------------------------------------------
        # Risk
        # -------------------------------------------------

        risk = str(
            case.get(
                "risk_level",
                "LOW",
            )
        ).upper()

        if risk in risk_distribution:
            risk_distribution[risk] += 1

        # -------------------------------------------------
        # Status
        # -------------------------------------------------

        status = str(
            case.get(
                "status",
                "NEW",
            )
        ).upper()

        if status in status_distribution:
            status_distribution[status] += 1

        # -------------------------------------------------
        # SVI
        # -------------------------------------------------

        try:
            svi_values.append(
                float(
                    case.get(
                        "svi_score",
                        0,
                    )
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            pass

        # -------------------------------------------------
        # Human review
        # -------------------------------------------------

        if case.get(
            "human_review_required",
            False,
        ):
            human_review_required += 1

    # -----------------------------------------------------
    # Average SVI
    # -----------------------------------------------------

    average_svi = (
        round(
            sum(svi_values)
            / len(svi_values),
            1,
        )
        if svi_values
        else 0.0
    )

    return {
        "total_cases": total_cases,
        "average_svi": average_svi,
        "human_review_required": (
            human_review_required
        ),
        "risk_distribution": risk_distribution,
        "status_distribution": status_distribution,
    }