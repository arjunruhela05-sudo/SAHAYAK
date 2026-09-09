import pytest

from services.validation_service import (
    validate_case_id,
)


def test_valid_case_id():
    assert (
        validate_case_id(" CASE-001 ")
        == "CASE-001"
    )


@pytest.mark.parametrize(
    "case_id",
    [
        "",
        "   ",
        "CASE 001",
        "CASE@001",
        "../../case",
        "CASE/001",
    ],
)
def test_invalid_case_id(case_id):
    with pytest.raises(ValueError):
        validate_case_id(case_id)


def test_max_length_case_id():
    case_id = "A" * 100

    assert validate_case_id(case_id) == case_id


def test_case_id_over_max_length():
    case_id = "A" * 101

    with pytest.raises(ValueError):
        validate_case_id(case_id)