import pytest

from tests.integration import helpers


def test_require_test_database_url_fails_when_missing(monkeypatch):
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)

    def skip_stub(message: str) -> None:
        raise AssertionError(f"unexpected skip: {message}")

    monkeypatch.setattr(helpers.pytest, "skip", skip_stub)

    with pytest.raises(pytest.fail.Exception) as excinfo:
        helpers.require_test_database_url()

    assert "TEST_DATABASE_URL is required for integration tests" in str(excinfo.value)
    assert "uv run pytest tests/unit" in str(excinfo.value)


def test_require_test_database_url_returns_configured_value(monkeypatch):
    monkeypatch.setenv("TEST_DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    assert helpers.require_test_database_url(
    ) == "postgresql+asyncpg://app:app@localhost:5432/app_test"
