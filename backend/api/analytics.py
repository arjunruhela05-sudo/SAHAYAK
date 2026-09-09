from fastapi import APIRouter

from models.analytics import (
    AnalyticsOverview,
    RiskDistribution,
    SVIStatistics,
    SignalFrequency,
)
from services.analytics_service import (
    get_overview,
    get_risk_distribution,
    get_svi_statistics,
    get_signal_frequency,
)

router = APIRouter(
    prefix="/api/analytics",
    tags=["Analytics"],
)


@router.get(
    "/overview",
    response_model=AnalyticsOverview,
)
def analytics_overview():
    return get_overview()


@router.get(
    "/risk-distribution",
    response_model=RiskDistribution,
)
def analytics_risk_distribution():
    return get_risk_distribution()


@router.get(
    "/svi",
    response_model=SVIStatistics,
)
def analytics_svi():
    return get_svi_statistics()


@router.get(
    "/signals",
    response_model=SignalFrequency,
)
def analytics_signals():
    return get_signal_frequency()