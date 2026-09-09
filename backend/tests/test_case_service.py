import json

from services import case_service


def test_create_case(tmp_path, monkeypatch):
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

    case = case_service.create_case(
        case_id="SAH-001",
        svi_score=72.5,
        risk_level="HIGH",
        human_review_required=True,
        language="en",
        signals={
            "fear": 80,
            "immediate_threat": 50,
        },
    )

    assert case["case_id"] == "SAH-001"
    assert case["svi_score"] == 72.5
    assert case["risk_level"] == "HIGH"
    assert case["status"] == "NEW"
    assert len(case["timeline"]) == 1

    assert cases_file.exists()


def test_get_case(tmp_path, monkeypatch):
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

    case_service.create_case(
        case_id="SAH-002",
        svi_score=30,
        risk_level="MODERATE",
        human_review_required=True,
    )

    result = case_service.get_case("SAH-002")

    assert result is not None
    assert result["case_id"] == "SAH-002"


def test_missing_case_returns_none(tmp_path, monkeypatch):
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

    result = case_service.get_case("DOES-NOT-EXIST")

    assert result is None


def test_list_cases(tmp_path, monkeypatch):
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

    case_service.create_case(
        case_id="SAH-003",
        svi_score=20,
        risk_level="LOW",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="SAH-004",
        svi_score=80,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    cases = case_service.list_cases()

    assert len(cases) == 2


def test_update_status(tmp_path, monkeypatch):
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

    case_service.create_case(
        case_id="SAH-005",
        svi_score=60,
        risk_level="HIGH",
        human_review_required=True,
    )

    updated = case_service.update_case_status(
        "SAH-005",
        "UNDER_REVIEW",
    )

    assert updated is not None
    assert updated["status"] == "UNDER_REVIEW"
    assert len(updated["timeline"]) == 2


def test_add_timeline_event(tmp_path, monkeypatch):
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

    case_service.create_case(
        case_id="SAH-006",
        svi_score=40,
        risk_level="MODERATE",
        human_review_required=True,
    )

    updated = case_service.add_timeline_event(
        "SAH-006",
        "HUMAN_REVIEW_STARTED",
        "Case assigned for human review.",
    )

    assert updated is not None
    assert len(updated["timeline"]) == 2
    assert (
        updated["timeline"][-1]["event"]
        == "HUMAN_REVIEW_STARTED"
    )


def test_search_by_case_id(tmp_path, monkeypatch):
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

    case_service.create_case(
        case_id="SAH-100",
        svi_score=80,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="SAH-200",
        svi_score=20,
        risk_level="LOW",
        human_review_required=True,
    )

    results = case_service.search_cases(
        query="100"
    )

    assert len(results) == 1
    assert results[0]["case_id"] == "SAH-100"


def test_filter_by_risk(tmp_path, monkeypatch):
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

    case_service.create_case(
        case_id="SAH-101",
        svi_score=80,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="SAH-102",
        svi_score=20,
        risk_level="LOW",
        human_review_required=True,
    )

    results = case_service.search_cases(
        risk_level="CRITICAL"
    )

    assert len(results) == 1
    assert results[0]["risk_level"] == "CRITICAL"

def test_invalid_status_rejected(
    tmp_path,
    monkeypatch,
):
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

    case_service.create_case(
        case_id="SAH-STATUS-001",
        svi_score=40,
        risk_level="MODERATE",
        human_review_required=True,
    )

    import pytest

    with pytest.raises(ValueError):
        case_service.update_case_status(
            "SAH-STATUS-001",
            "INVALID_STATUS",
        )


def test_invalid_status_transition_rejected(
    tmp_path,
    monkeypatch,
):
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

    case_service.create_case(
        case_id="SAH-STATUS-002",
        svi_score=80,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    case_service.update_case_status(
        "SAH-STATUS-002",
        "UNDER_REVIEW",
    )

    case_service.update_case_status(
        "SAH-STATUS-002",
        "RESOLVED",
    )

    import pytest

    with pytest.raises(ValueError):
        case_service.update_case_status(
            "SAH-STATUS-002",
            "NEW",
        )


def test_closed_case_cannot_change_status(
    tmp_path,
    monkeypatch,
):
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

    case_service.create_case(
        case_id="SAH-STATUS-003",
        svi_score=20,
        risk_level="LOW",
        human_review_required=True,
    )

    case_service.update_case_status(
        "SAH-STATUS-003",
        "CLOSED",
    )

    import pytest

    with pytest.raises(ValueError):
        case_service.update_case_status(
            "SAH-STATUS-003",
            "UNDER_REVIEW",
        )    

def test_cases_are_prioritized_by_risk(
    tmp_path,
    monkeypatch,
):
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

    case_service.create_case(
        case_id="SAH-PRIORITY-LOW",
        svi_score=90,
        risk_level="LOW",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="SAH-PRIORITY-CRITICAL",
        svi_score=75,
        risk_level="CRITICAL",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="SAH-PRIORITY-HIGH",
        svi_score=80,
        risk_level="HIGH",
        human_review_required=True,
    )

    cases = case_service.search_cases()

    assert cases[0]["case_id"] == (
        "SAH-PRIORITY-CRITICAL"
    )

    assert cases[1]["case_id"] == (
        "SAH-PRIORITY-HIGH"
    )

    assert cases[2]["case_id"] == (
        "SAH-PRIORITY-LOW"
    )


def test_cases_same_risk_sorted_by_svi(
    tmp_path,
    monkeypatch,
):
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

    case_service.create_case(
        case_id="SAH-SVI-LOW",
        svi_score=55,
        risk_level="HIGH",
        human_review_required=True,
    )

    case_service.create_case(
        case_id="SAH-SVI-HIGH",
        svi_score=85,
        risk_level="HIGH",
        human_review_required=True,
    )

    cases = case_service.search_cases()

    assert cases[0]["case_id"] == "SAH-SVI-HIGH"
    assert cases[1]["case_id"] == "SAH-SVI-LOW"        