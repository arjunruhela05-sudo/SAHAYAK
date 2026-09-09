from pydantic import BaseModel, Field


class AnalyticsOverview(BaseModel):
    total_cases: int = Field(..., ge=0)
    average_svi: float = Field(..., ge=0, le=100)
    human_review_required: int = Field(..., ge=0)


class RiskDistribution(BaseModel):
    CRITICAL: int = Field(..., ge=0)
    HIGH: int = Field(..., ge=0)
    MODERATE: int = Field(..., ge=0)
    LOW: int = Field(..., ge=0)


class StatusDistribution(BaseModel):
    NEW: int = Field(..., ge=0)
    UNDER_REVIEW: int = Field(..., ge=0)
    ACTION_REQUIRED: int = Field(..., ge=0)
    RESOLVED: int = Field(..., ge=0)
    CLOSED: int = Field(..., ge=0)


class SVIStatistics(BaseModel):
    average: float = Field(..., ge=0, le=100)
    minimum: float = Field(..., ge=0, le=100)
    maximum: float = Field(..., ge=0, le=100)


class SignalFrequency(BaseModel):
    fear: int = Field(..., ge=0)
    immediate_threat: int = Field(..., ge=0)
    distress: int = Field(..., ge=0)
    isolation: int = Field(..., ge=0)
    intimidation: int = Field(..., ge=0)
    self_harm: int = Field(..., ge=0)