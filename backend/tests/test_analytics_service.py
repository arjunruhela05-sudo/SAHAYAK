from services import analytics_service
from services import case_service


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


def test_empty_overview(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    result = analytics_service.get_overview()

    assert result["total_cases"] == 0
    assert result["average_svi"] == 0.0
    assert result["human_review_required"] == 0


def test_risk_distribution(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="ANALYTICS-001",
        svi_score=90,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="ANALYTICS-002",
        svi_score=60,
        risk_level="HIGH",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="ANALYTICS-003",
        svi_score=20,
        risk_level="LOW",
        human_review_required=True,
    )

    result = (
        analytics_service
        .get_risk_distribution()
    )

    assert result["CRITICAL"] == 1
    assert result["HIGH"] == 1
    assert result["MODERATE"] == 0
    assert result["LOW"] == 1


def test_status_distribution(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="ANALYTICS-004",
        svi_score=50,
        risk_level="HIGH",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="ANALYTICS-005",
        svi_score=30,
        risk_level="MODERATE",
        human_review_required=True,
    )

    case_service.update_case_status(
        "ANALYTICS-005",
        "UNDER_REVIEW",
    )

    result = (
        analytics_service
        .get_status_distribution()
    )

    assert result["NEW"] == 1
    assert result["UNDER_REVIEW"] == 1


def test_signal_frequency(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="ANALYTICS-006",
        svi_score=70,
        risk_level="HIGH",
        human_review_required=True,
        signals={
            "fear": 80,
            "immediate_threat": 50,
            "distress": 10,
            "isolation": 60,
            "intimidation": 0,
            "self_harm": 0,
        },
    )

    result = (
        analytics_service
        .get_signal_frequency()
    )

    assert result["fear"] == 1
    assert result["immediate_threat"] == 1
    assert result["isolation"] == 1
    assert result["distress"] == 0


def test_svi_statistics(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="ANALYTICS-007",
        svi_score=20,
        risk_level="LOW",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="ANALYTICS-008",
        svi_score=80,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    result = (
        analytics_service
        .get_svi_statistics()
    )

    assert result["average"] == 50.0
    assert result["minimum"] == 20.0
    assert result["maximum"] == 80.0


def test_all_analytics(
    tmp_path,
    monkeypatch,
):
    configure_storage(
        tmp_path,
        monkeypatch,
    )

    case_service.create_case(
        case_id="ANALYTICS-009",
        svi_score=75,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    result = (
        analytics_service
        .get_all_analytics()
    )

    assert "overview" in result
    assert "risk_distribution" in result
    assert "status_distribution" in result
    assert "signal_frequency" in result
    assert "svi" in result

    assert (
        result["overview"]["total_cases"]
        == 1
    )