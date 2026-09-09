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


def test_complete_case_lifecycle():
    case_id = "E2E-001"

    # -------------------------------------------------
    # 1. Create assessment
    # -------------------------------------------------
    assessment_response = client.post(
        "/api/assess",
        json={
            "case_id": case_id,
            "narrative": (
                "I am afraid because the person "
                "threatened me and I feel unsafe. "
                "I have been isolated from my family."
            ),
            "language": "en",
            "consent": True,
        },
    )

    assert assessment_response.status_code == 200

    assessment = assessment_response.json()

    assert assessment["case_id"] == case_id
    assert 0 <= assessment["svi_score"] <= 100
    assert assessment["risk_level"] in {
        "LOW",
        "MODERATE",
        "HIGH",
        "CRITICAL",
    }
    assert assessment["human_review_required"] is True

    # -------------------------------------------------
    # 2. Verify case was persisted
    # -------------------------------------------------
    cases_response = client.get(
        "/api/cases"
    )

    assert cases_response.status_code == 200

    cases = cases_response.json()

    assert len(cases) == 1
    assert cases[0]["case_id"] == case_id
    assert cases[0]["svi_score"] == assessment["svi_score"]

    # -------------------------------------------------
    # 3. Get case details
    # -------------------------------------------------
    details_response = client.get(
        f"/api/cases/{case_id}"
    )

    assert details_response.status_code == 200

    case = details_response.json()

    assert case["case_id"] == case_id
    assert case["risk_level"] == assessment["risk_level"]
    assert case["status"] == "NEW"
    assert case["human_review_required"] is True

    assert len(case["timeline"]) == 1
    assert case["timeline"][0]["event"] == "CASE_CREATED"

    # -------------------------------------------------
    # 4. Move case into review
    # -------------------------------------------------
    status_response = client.patch(
        f"/api/cases/{case_id}/status",
        json={
            "status": "UNDER_REVIEW",
        },
    )

    assert status_response.status_code == 200

    updated_case = status_response.json()

    assert updated_case["status"] == "UNDER_REVIEW"
    assert len(updated_case["timeline"]) == 2

    # -------------------------------------------------
    # 5. Add timeline event
    # -------------------------------------------------
    timeline_response = client.post(
        f"/api/cases/{case_id}/timeline",
        json={
            "event": "HUMAN_REVIEW_STARTED",
            "description": (
                "Authorized responder started "
                "case review."
            ),
        },
    )

    assert timeline_response.status_code == 200

    timeline_case = timeline_response.json()

    assert len(timeline_case["timeline"]) == 3

    assert (
        timeline_case["timeline"][-1]["event"]
        == "HUMAN_REVIEW_STARTED"
    )

    # -------------------------------------------------
    # 6. Verify analytics
    # -------------------------------------------------
    overview_response = client.get(
        "/api/analytics/overview"
    )

    assert overview_response.status_code == 200

    overview = overview_response.json()

    assert overview["total_cases"] == 1
    assert (
        overview["average_svi"]
        == round(assessment["svi_score"], 1)
    )
    assert overview["human_review_required"] == 1

    # -------------------------------------------------
    # 7. Verify risk distribution
    # -------------------------------------------------
    risk_response = client.get(
        "/api/analytics/risk-distribution"
    )

    assert risk_response.status_code == 200

    risk_distribution = risk_response.json()

    assert (
        risk_distribution[
            assessment["risk_level"]
        ]
        == 1
    )

    # -------------------------------------------------
    # 8. Verify SVI statistics
    # -------------------------------------------------
    svi_response = client.get(
        "/api/analytics/svi"
    )

    assert svi_response.status_code == 200

    svi = svi_response.json()

    expected_svi = round(
        assessment["svi_score"],
        1,
    )

    assert svi["average"] == expected_svi
    assert svi["minimum"] == expected_svi
    assert svi["maximum"] == expected_svi

    # -------------------------------------------------
    # 9. Verify signal analytics
    # -------------------------------------------------
    signals_response = client.get(
        "/api/analytics/signals"
    )

    assert signals_response.status_code == 200

    signals = signals_response.json()

    assert isinstance(signals, dict)
    assert "fear" in signals
    assert "immediate_threat" in signals
    assert "isolation" in signals