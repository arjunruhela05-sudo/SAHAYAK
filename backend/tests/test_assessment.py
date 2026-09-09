import pytest
from fastapi.testclient import TestClient

from main import app
from services import case_service


client = TestClient(app)
@pytest.fixture(autouse=True)
def isolated_case_storage(tmp_path, monkeypatch):
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


def test_assessment_success():

    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-AUTO-001",
            "narrative": (
                "I am scared to go home "
                "and I have nobody to help me."
            ),
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["case_id"] == "SAH-AUTO-001"
    assert 0 <= data["svi_score"] <= 100

    assert data["risk_level"] in [
        "LOW",
        "MODERATE",
        "HIGH",
        "CRITICAL",
    ]

    assert "signals" in data
    assert "explanation" in data
    assert "evidence" in data
    assert "recommendations" in data


def test_assessment_requires_consent():

    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-AUTO-002",
            "narrative": "I am scared.",
            "language": "en",
            "consent": False,
        },
    )

    assert response.status_code == 400


def test_assessment_detects_threat():

    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-AUTO-003",
            "narrative": (
                "He threatened to hurt me "
                "and he is outside my home."
            ),
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["immediate_threat"]["detected"] is True

    assert data["signals"]["immediate_threat"] > 0


def test_assessment_requires_human_review():

    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-AUTO-004",
            "narrative": "I am scared.",
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["human_review_required"] is True

def test_assessment_rejects_invalid_case_id():
    response = client.post(
        "/api/assess",
        json={
            "case_id": "CASE 001",
            "narrative": "I feel afraid.",
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "case_id may contain only letters, "
        "numbers, hyphens, and underscores."
    )    

def test_assessment_rejects_whitespace_narrative():
    response = client.post(
        "/api/assess",
        json={
            "case_id": "SECURITY-001",
            "narrative": "     ",
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 400

    assert response.json()["detail"] == (
        "narrative is required."
    )    

def test_assessment_calibrates_near_term_lethal_threat():
    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-AI-V21-LETHAL-001",
            "narrative": "they have said that they will kill me tomorrow",
            "language": "en",
            "consent": True,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["signals"]["immediate_threat"] >= 95
    assert data["svi_score"] >= 95
    assert data["risk_level"] == "CRITICAL"
    assert data["immediate_threat"]["detected"] is True
    assert data["human_review_required"] is True


def test_assessment_hindi_lethal_threat_is_critical():
    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-AI-V22-HI-001",
            "narrative": "उन्होंने मुझे और मेरे परिवार को जान से मारने की धमकी दी है",
            "language": "hi",
            "consent": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signals"]["immediate_threat"] >= 90
    assert data["svi_score"] >= 90
    assert data["risk_level"] == "CRITICAL"
    assert data["immediate_threat"]["severity"] == "CRITICAL"


def test_assessment_negated_lethal_threat_is_not_critical():
    response = client.post(
        "/api/assess",
        json={
            "case_id": "SAH-AI-V22-NEG-001",
            "narrative": "They did not threaten to kill me and I feel safe.",
            "language": "en",
            "consent": True,
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["signals"]["immediate_threat"] == 0
    assert data["immediate_threat"]["detected"] is False
    assert data["risk_level"] in ["LOW", "MODERATE"]
    assert data["risk_level"] != "CRITICAL"
