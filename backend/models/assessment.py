from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# =========================================================
# MULTIMODAL BREAKDOWN
# =========================================================

class ModalityIndicator(BaseModel):
    """One supplementary channel (acoustic, prosody, disfluency, behaviour)."""

    available: bool = False
    indicator: float = Field(default=0.0, ge=0, le=100)
    sub_scores: Dict[str, float] = Field(default_factory=dict)
    cues: List[str] = Field(default_factory=list)
    reliability: Optional[float] = Field(default=None, ge=0, le=1)
    # Short human label (e.g. tone: "agitated", "flat / withdrawn").
    label: Optional[str] = None


class ModalityBreakdown(BaseModel):
    """
    Transparent view of how the final SVI was assembled.

    Text is always primary.  Voice and behaviour can only nudge the score
    upward within declared caps; they never decide risk on their own.
    """

    text_svi: float = Field(..., ge=0, le=100)
    fused_svi: float = Field(..., ge=0, le=100)
    fusion_method: str

    voice_indicator: float = Field(default=0.0, ge=0, le=100)
    behavior_indicator: float = Field(default=0.0, ge=0, le=100)

    voice_adjustment: float = 0.0
    behavior_adjustment: float = 0.0

    acoustic: ModalityIndicator = Field(default_factory=ModalityIndicator)
    prosody: ModalityIndicator = Field(default_factory=ModalityIndicator)
    disfluency: ModalityIndicator = Field(default_factory=ModalityIndicator)
    tone: ModalityIndicator = Field(default_factory=ModalityIndicator)
    behavior: ModalityIndicator = Field(default_factory=ModalityIndicator)

    incongruence_flag: bool = False
    modalities_used: List[str] = Field(default_factory=list)


class NarrativeContext(BaseModel):
    """
    Whole-passage reading of the narrative: which signals emerge only when
    sentences are read together, and how the story is told (escalation,
    helplessness, present-tense danger, fragmentation, rumination ...).
    """

    available: bool = False
    engine: str = "none"
    indicator: float = Field(default=0.0, ge=0, le=100)
    adjustment: float = 0.0
    sub_scores: Dict[str, float] = Field(default_factory=dict)
    cues: List[str] = Field(default_factory=list)
    signals: Dict[str, Any] = Field(default_factory=dict)
    discourse: Dict[str, Any] = Field(default_factory=dict)


# =========================================================
# REQUEST
# =========================================================

class AssessmentRequest(BaseModel):
    case_id: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Unique case identifier"
    )

    narrative: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="Victim/complainant narrative"
    )

    language: str = Field(
        default="en",
        min_length=2,
        max_length=10,
        description="Input language code"
    )

    consent: bool = Field(
        ...,
        description="Whether the user has provided consent"
    )

    participant_view: bool = Field(
        default=False,
        description=(
            "True when the request comes from the assessed person's own "
            "device: the response is then a receipt without any score, "
            "risk level or behavioural cue."
        ),
    )


# =========================================================
# SIGNALS
# =========================================================

class SignalScores(BaseModel):
    fear: float = Field(default=0, ge=0, le=100)
    immediate_threat: float = Field(default=0, ge=0, le=100)
    distress: float = Field(default=0, ge=0, le=100)
    isolation: float = Field(default=0, ge=0, le=100)
    intimidation: float = Field(default=0, ge=0, le=100)
    self_harm: float = Field(default=0, ge=0, le=100)


# =========================================================
# VULNERABILITY PROFILE
# =========================================================

class VulnerabilityProfile(BaseModel):
    fear: str = "NOT_DETECTED"
    immediate_threat: str = "NOT_DETECTED"
    distress: str = "NOT_DETECTED"
    isolation: str = "NOT_DETECTED"
    intimidation: str = "NOT_DETECTED"
    self_harm: str = "NOT_DETECTED"


# =========================================================
# IMMEDIATE THREAT
# =========================================================

class ThreatAssessment(BaseModel):
    detected: bool = False
    severity: str = "NONE"
    indicators: List[str] = Field(default_factory=list)


# =========================================================
# EVIDENCE
# =========================================================

class EvidenceItem(BaseModel):
    text: str
    signal: str


# =========================================================
# RESPONSE
# =========================================================

class AssessmentResponse(BaseModel):
    case_id: str

    svi_score: float = Field(
        ...,
        ge=0,
        le=100
    )

    risk_level: str

    confidence: float = Field(
        ...,
        ge=0,
        le=1
    )

    signals: SignalScores

    vulnerability_profile: VulnerabilityProfile

    explanation: List[str] = Field(
        default_factory=list
    )

    evidence: List[EvidenceItem] = Field(
        default_factory=list
    )

    immediate_threat: ThreatAssessment

    recommendations: List[str] = Field(
        default_factory=list
    )

    human_review_required: bool = True

    language: str

    # -----------------------------------------------------
    # Multimodal extras (only populated for voice / video)
    # -----------------------------------------------------

    transcript: Optional[str] = None

    # Whole-passage / discourse reading of the narrative (text, voice, video).
    narrative_context: Optional[NarrativeContext] = None

    modalities: Optional[ModalityBreakdown] = None

    # Raw feature dictionaries for auditability / research export.
    voice_analysis: Optional[Dict[str, Any]] = None

    behavior_analysis: Optional[Dict[str, Any]] = None

# =========================================================
# PARTICIPANT RECEIPT
# =========================================================

class AssessmentReceipt(BaseModel):
    """
    What the assessed person sees after submitting.  Deliberately carries
    no score, risk level, signal, cue or tracking data — those are for
    the authorised human reviewer only.
    """

    case_id: str
    status: str = "RECEIVED"
    capture_mode: str = "text"
    language: str = "unknown"
    human_review_required: bool = True
    participant_view: bool = True
    message: str = (
        "Thank you. Your statement has been received and will be reviewed "
        "by an authorised responder."
    )
    next_steps: List[str] = Field(default_factory=list)
