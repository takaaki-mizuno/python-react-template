import pytest
from typer.testing import CliRunner

import manage
from tests.integration.helpers import require_test_database_url

pytestmark = pytest.mark.integration


def test_db_prune_auth_runs_with_application_container_and_unit_of_work(
    monkeypatch,
    async_engine,
):
    assert async_engine is not None
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())

    result = CliRunner().invoke(
        manage.app,
        [
            "db-prune-auth",
            "--audit-logs-before",
            "2026-08-01T00:00:00+00:00",
            "--expired-sessions-before",
            "2026-08-01T00:00:00+00:00",
        ],
    )

    assert result.exit_code == 0
    assert "Deleted audit logs:" in result.stdout
    assert "Deleted expired sessions:" in result.stdout
