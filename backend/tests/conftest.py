import pytest

from services import case_service


@pytest.fixture(autouse=True)
def reset_case_store():
    case_service.clear_cases()
    yield
    case_service.clear_cases()