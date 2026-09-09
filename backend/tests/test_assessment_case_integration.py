from fastapi.testclient import TestClient

from main import app
from services import case_service


client = TestClient(app)


def configure_storage(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    cases_file = data_dir / "cases.json"

    monkeypatch.setattr(
        case_service,
        "DATA_DIR",
        data_dir,
    )

    monkeypatch.setattr(
        case_service,
        "CASES_FILE",
        cases_file,
    )


def test_assessment_is_saved_as_case(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-INTEGRATION-001",
            "narrative": (
                "I am scared to go home. "
                "I have nobody to help me."
            ),
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 200

    assessment = response.json()

    assert (
        assessment["case_id"]
        == "SAH-INTEGRATION-001"
    )

    saved_case = case_service.get_case(
        "SAH-INTEGRATION-001"
    )

    assert saved_case is not None

    assert (
        saved_case["svi_score"]
        == assessment["svi_score"]
    )

    assert (
        saved_case["risk_level"]
        == assessment["risk_level"]
    )

    assert (
        saved_case["human_review_required"]
        is True
    )


def test_assessment_duplicate_case_rejected(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    payload = {
        "case_id": "SAH-INTEGRATION-002",
        "narrative": "I need help.",
        "language": "en",
        "consent": True,
    }

    first = client.post(
        "/api/assess",
        json=payload,
    )

    second = client.post(
        "/api/assess",
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 409


def test_assessment_without_consent_not_saved(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-INTEGRATION-003",
            "narrative": "I am scared.",
            "language": "en",
            "consent": False,
        },
    )

    assert response.status_code == 400

    assert (
        case_service.get_case(
            "SAH-INTEGRATION-003"
        )
        is None
    )