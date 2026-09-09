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


def test_create_case_api(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)

    response = client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-001",
            "svi_score": 72.5,
            "risk_level": "HIGH",
            "human_review_required": True,
            "language": "en",
        },
    )

    assert response.status_code == 201

    data = response.json()

    assert data["case_id"] == "SAH-API-001"
    assert data["svi_score"] == 72.5
    assert data["risk_level"] == "HIGH"
    assert data["status"] == "NEW"


def test_duplicate_case_rejected(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)

    payload = {
        "case_id": "SAH-API-002",
        "svi_score": 50,
        "risk_level": "HIGH",
        "human_review_required": True,
    }

    first = client.post(
        "/api/cases",
        json=payload,
    )

    second = client.post(
        "/api/cases",
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 409


def test_get_case_details_api(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-003",
            "svi_score": 80,
            "risk_level": "CRITICAL",
            "human_review_required": True,
        },
    )

    response = client.get(
        "/api/cases/SAH-API-003"
    )

    assert response.status_code == 200

    data = response.json()

    assert data["case_id"] == "SAH-API-003"
    assert data["risk_level"] == "CRITICAL"


def test_missing_case_api(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)

    response = client.get(
        "/api/cases/DOES-NOT-EXIST"
    )

    assert response.status_code == 404


def test_list_cases_api(tmp_path, monkeypatch):
    configure_storage(tmp_path, monkeypatch)

    for case_id in ["SAH-API-004", "SAH-API-005"]:
        client.post(
            "/api/cases",
            json={
                "case_id": case_id,
                "svi_score": 30,
                "risk_level": "MODERATE",
                "human_review_required": True,
            },
        )

    response = client.get("/api/cases")

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 2
    assert data[0]["case_id"] == "SAH-API-004"


def test_filter_cases_by_risk(
    tmp_path,
    monkeypatch,
):
    configure_storage(tmp_path, monkeypatch)

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-006",
            "svi_score": 85,
            "risk_level": "CRITICAL",
            "human_review_required": True,
        },
    )

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-007",
            "svi_score": 20,
            "risk_level": "LOW",
            "human_review_required": True,
        },
    )

    response = client.get(
        "/api/cases?risk_level=CRITICAL"
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data) == 1
    assert data[0]["case_id"] == "SAH-API-006"


def test_update_status_api(
    tmp_path,
    monkeypatch,
):
    configure_storage(tmp_path, monkeypatch)

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-008",
            "svi_score": 60,
            "risk_level": "HIGH",
            "human_review_required": True,
        },
    )

    response = client.patch(
        "/api/cases/SAH-API-008/status",
        json={
            "status": "UNDER_REVIEW"
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["status"] == "UNDER_REVIEW"
    assert len(data["timeline"]) == 2


def test_add_timeline_event_api(
    tmp_path,
    monkeypatch,
):
    configure_storage(tmp_path, monkeypatch)

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-009",
            "svi_score": 40,
            "risk_level": "MODERATE",
            "human_review_required": True,
        },
    )

    response = client.post(
        "/api/cases/SAH-API-009/timeline",
        json={
            "event": "HUMAN_REVIEW_STARTED",
            "description": "Case assigned for review.",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert len(data["timeline"]) == 2

    assert (
        data["timeline"][-1]["event"]
        == "HUMAN_REVIEW_STARTED"
    )
def test_invalid_status_api(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-STATUS-001",
            "svi_score": 60,
            "risk_level": "HIGH",
            "human_review_required": True,
        },
    )

    response = client.patch(
        "/api/cases/SAH-API-STATUS-001/status",
        json={
            "status": "INVALID_STATUS",
        },
    )

    assert response.status_code == 400


def test_invalid_transition_api(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-STATUS-002",
            "svi_score": 60,
            "risk_level": "HIGH",
            "human_review_required": True,
        },
    )

    client.patch(
        "/api/cases/SAH-API-STATUS-002/status",
        json={
            "status": "UNDER_REVIEW",
        },
    )

    client.patch(
        "/api/cases/SAH-API-STATUS-002/status",
        json={
            "status": "RESOLVED",
        },
    )

    response = client.patch(
        "/api/cases/SAH-API-STATUS-002/status",
        json={
            "status": "NEW",
        },
    )

    assert response.status_code == 400   


def test_cases_api_returns_priority_order(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-LOW",
            "svi_score": 90,
            "risk_level": "LOW",
            "human_review_required": True,
        },
    )

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-CRITICAL",
            "svi_score": 70,
            "risk_level": "CRITICAL",
            "human_review_required": True,
        },
    )

    client.post(
        "/api/cases",
        json={
            "case_id": "SAH-API-HIGH",
            "svi_score": 80,
            "risk_level": "HIGH",
            "human_review_required": True,
        },
    )

    response = client.get("/api/cases")

    assert response.status_code == 200

    data = response.json()

    assert data[0]["case_id"] == (
        "SAH-API-CRITICAL"
    )

    assert data[1]["case_id"] == (
        "SAH-API-HIGH"
    )

    assert data[2]["case_id"] == (
        "SAH-API-LOW"
    )     

def test_case_creation_rejects_invalid_case_id():
    response = client.post(
        "/api/cases",
        json={
            "case_id": "CASE@001",
            "svi_score": 40,
            "risk_level": "MODERATE",
            "human_review_required": True,
        },
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "case_id may contain only letters, "
        "numbers, hyphens, and underscores."
    )