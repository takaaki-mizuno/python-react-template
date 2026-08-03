from pathlib import Path

import pytest
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.util import CommandError

import manage


def test_bare_alembic_current_requires_explicit_database_url(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    config = AlembicConfig(str(Path(manage.__file__).resolve().parent / "alembic.ini"))

    with pytest.raises(CommandError, match="DATABASE_URL must be configured explicitly"):
        alembic_command.current(config)
