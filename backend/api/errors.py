from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


def _validation_details(
    exc: RequestValidationError,
) -> list[dict[str, Any]]:
    details = []

    for error in exc.errors():
        location = [
            str(item)
            for item in error.get("loc", [])
        ]

        details.append(
            {
                "field": ".".join(location),
                "message": error.get(
                    "msg",
                    "Invalid value.",
                ),
                "type": error.get(
                    "type",
                    "validation_error",
                ),
            }
        )

    return details


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
):
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed.",
            "details": _validation_details(exc),
        },
    )


async def unexpected_exception_handler(
    request: Request,
    exc: Exception,
):
    return JSONResponse(
        status_code=500,
        content={
            "error": "INTERNAL_SERVER_ERROR",
            "message": (
                "An unexpected server error occurred."
            ),
        },
    )