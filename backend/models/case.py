from typing import List, Optional

from pydantic import BaseModel, Field


class TimelineEvent(BaseModel):
    event: str = Field(..., min_length=1, max_length=100)
    timestamp: str
    description: Optional[str] = None


class CaseSummary(BaseModel):
    case_id: str
    svi_score: float
    risk_level: str
    status: str
    human_review_required: bool
    created_at: str


class Case(BaseModel):
    case_id: str
    svi_score: float
    risk_level: str
    status: str
    human_review_required: bool
    created_at: str
    language: Optional[str] = None
    signals: Optional[dict] = None
    vulnerability_profile: Optional[dict] = None
    explanation: List[str] = Field(default_factory=list)
    evidence: List[dict] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    timeline: List[TimelineEvent] = Field(
        default_factory=list
    )

    # Multimodal capture metadata (text / voice / video)
    capture_mode: str = "text"
    modalities: Optional[dict] = None
    voice_analysis: Optional[dict] = None
    behavior_analysis: Optional[dict] = None
    narrative_context: Optional[dict] = None
    transcript: Optional[str] = None


class ParticipantCaseSummary(BaseModel):
    """
    What the *assessed person* is allowed to see about their own
    submission: receipt-level information only.  No score, no risk
    level, no cues, no tracking data.
    """

    case_id: str
    status: str
    created_at: str
    updated_at: Optional[str] = None
    capture_mode: str = "text"
    human_review_required: bool = True
    message: str = "Your statement has been received and is with a human reviewer."


class CreateCaseRequest(BaseModel):
    case_id: str = Field(..., min_length=1, max_length=100)
    svi_score: float = Field(..., ge=0, le=100)
    risk_level: str = Field(..., min_length=1, max_length=20)
    human_review_required: bool = True
    language: Optional[str] = None
    signals: Optional[dict] = None
    vulnerability_profile: Optional[dict] = None
    explanation: List[str] = Field(default_factory=list)
    evidence: List[dict] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)


class UpdateStatusRequest(BaseModel):
    status: str = Field(..., min_length=1, max_length=30)


class AddTimelineEventRequest(BaseModel):
    event: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(
        default=None,
        max_length=500,
    )