from fastapi import APIRouter
from fastapi.testclient import TestClient

from main import app


client = TestClient(
    app,
    raise_server_exceptions=False,
)


test_error_router = APIRouter(
    prefix="/api/test-errors",
)


@test_error_router.get("/unexpected")
def unexpected_test():
    raise RuntimeError("Internal test failure")


app.include_router(test_error_router)


def test_assessment_validation_error_format():
    response = client.post(
        "/api/assess",
        json={
            "case_id": "",
            "narrative": "",
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert data["error"] == (
        "VALIDATION_ERROR"
    )

    assert data["message"] == (
        "Request validation failed."
    )

    assert isinstance(
        data["details"],
        list,
    )


def test_unexpected_error_format():
    response = client.get(
        "/api/test-errors/unexpected"
    )

    assert response.status_code == 500

    data = response.json()

    assert (
        data["error"]
        == "INTERNAL_SERVER_ERROR"
    )

    assert data["message"] == (
        "An unexpected server error occurred."
    )

    assert "Internal test failure" not in str(data)