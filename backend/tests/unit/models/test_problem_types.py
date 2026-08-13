import re

from app.models.problem_types import PROBLEM_TYPES, problem_type_for_code, problem_type_for_status


def test_problem_type_registry_uses_snake_case_codes_and_path_types() -> None:
    assert PROBLEM_TYPES
    for code, problem_type in PROBLEM_TYPES.items():
        assert re.fullmatch(r"[a-z][a-z0-9_]*", code)
        assert problem_type.code == code
        assert problem_type.type == f"/problems/{code}"
        assert problem_type.title
        assert 400 <= problem_type.status <= 599


def test_problem_type_registry_includes_framework_and_future_negotiation_codes() -> None:
    for code in ("method_not_allowed", "not_acceptable", "unsupported_media_type"):
        assert code in PROBLEM_TYPES


def test_problem_type_lookup_normalizes_legacy_uppercase_codes() -> None:
    problem_type = problem_type_for_code("invalid_credentials", fallback_status=401)

    assert problem_type.code == "invalid_credentials"
    assert problem_type.status == 401


def test_problem_type_for_status_preserves_unknown_http_status() -> None:
    problem_type = problem_type_for_status(418)

    assert problem_type.code == "http_error"
    assert problem_type.type == "/problems/http_error"
    assert problem_type.status == 418


def test_problem_type_for_status_preserves_unknown_5xx_http_status() -> None:
    problem_type = problem_type_for_status(503)

    assert problem_type.code == "http_error"
    assert problem_type.type == "/problems/http_error"
    assert problem_type.title == "HTTP error"
    assert problem_type.status == 503
