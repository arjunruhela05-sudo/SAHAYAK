from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.assessment import router as assessment_router
from api.voice import router as voice_router
from api.video import router as video_router
from api.cases import router as cases_router
from api.analytics import router as analytics_router
from fastapi.exceptions import RequestValidationError

from api.errors import (
    unexpected_exception_handler,
    validation_exception_handler,
)

APP_VERSION = "6.0.0"
app = FastAPI(
    title="SAHAYAK API",
    description=(
        "AI-assisted Stress, Trauma and Vulnerability "
        "Assessment & Triage Prototype"
    ),
    version=APP_VERSION,
)

app.add_exception_handler(
    RequestValidationError,
    validation_exception_handler,
)

app.add_exception_handler(
    Exception,
    unexpected_exception_handler,
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# =========================================================
# ROUTERS
# =========================================================

app.include_router(assessment_router)
app.include_router(voice_router)
app.include_router(video_router)
app.include_router(cases_router)
app.include_router(analytics_router)

# =========================================================
# ROOT
# =========================================================

@app.get("/")
def root():
    return {
        "service": "SAHAYAK Backend",
        "version": APP_VERSION,
        "status": "running",
    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "SAHAYAK Backend",
        "version": APP_VERSION,
    }