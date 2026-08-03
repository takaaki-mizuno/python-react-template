from pathlib import Path

from alembic import command
from alembic.config import Config

from tests.integration.helpers import require_test_database_url


def test_alembic_metadata_has_no_pending_schema_changes(monkeypatch):
    test_database_url = require_test_database_url()
    monkeypatch.setenv("DATABASE_URL", test_database_url)

    alembic_config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    command.upgrade(alembic_config, "head")
    command.check(alembic_config)
