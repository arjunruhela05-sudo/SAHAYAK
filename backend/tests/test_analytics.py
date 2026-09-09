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


def test_overview_endpoint(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    response = client.get(
        "/api/analytics/overview"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["total_cases"] == 0
    assert data["average_svi"] == 0.0
    assert data["human_review_required"] == 0


def test_risk_distribution_endpoint(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="API-ANALYTICS-001",
        svi_score=90,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    response = client.get(
        "/api/analytics/risk-distribution"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["CRITICAL"] == 1
    assert data["HIGH"] == 0
    assert data["MODERATE"] == 0
    assert data["LOW"] == 0


def test_svi_endpoint(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="API-ANALYTICS-002",
        svi_score=80,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    response = client.get(
        "/api/analytics/svi"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["average"] == 80.0
    assert data["minimum"] == 80.0
    assert data["maximum"] == 80.0


def test_signals_endpoint(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="API-ANALYTICS-003",
        svi_score=70,
        risk_level="HIGH",
        human_review_required=True,
        signals={
            "fear": 80,
            "immediate_threat": 60,
            "distress": 10,
            "isolation": 40,
            "intimidation": 0,
            "self_harm": 0,
        },
    )

    response = client.get(
        "/api/analytics/signals"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["fear"] == 1
    assert data["immediate_threat"] == 1
    assert data["isolation"] == 1
    assert data["distress"] == 0

def test_empty_risk_distribution(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    response = client.get(
        "/api/analytics/risk-distribution"
    )

    assert response.status_code == 200

    data = response.json()

    assert data == {
        "CRITICAL": 0,
        "HIGH": 0,
        "MODERATE": 0,
        "LOW": 0,
    }


def test_empty_svi_endpoint(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    response = client.get(
        "/api/analytics/svi"
    )

    assert response.status_code == 200

    assert response.json() == {
        "average": 0.0,
        "minimum": 0.0,
        "maximum": 0.0,
    }


def test_empty_signals_endpoint(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    response = client.get(
        "/api/analytics/signals"
    )

    assert response.status_code == 200

    assert response.json() == {
        "fear": 0,
        "immediate_threat": 0,
        "distress": 0,
        "isolation": 0,
        "intimidation": 0,
        "self_harm": 0,
    }    