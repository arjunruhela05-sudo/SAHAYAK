import re


CASE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}$"
)


def validate_case_id(case_id: str) -> str:
    """Validate and normalize a case ID."""

    normalized = case_id.strip()

    if not normalized:
        raise ValueError(
            "case_id is required."
        )

    if not CASE_ID_PATTERN.fullmatch(
        normalized
    ):
        raise ValueError(
            "case_id may contain only letters, "
            "numbers, hyphens, and underscores."
        )

    return normalized