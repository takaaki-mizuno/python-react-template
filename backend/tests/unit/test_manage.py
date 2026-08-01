from pathlib import Path

from typer.testing import CliRunner

import manage


def test_db_check_invokes_alembic_check(monkeypatch):
    calls = []
    monkeypatch.setenv("ALEMBIC_DATABASE_URL",
                       "postgresql://app:app@localhost:5432/app_test")

    class ConfigStub:

        def __init__(self, path):
            calls.append(("config", path))

    class CommandStub:

        @staticmethod
        def check(config):
            calls.append(("check", config))

    monkeypatch.setattr(manage, "AlembicConfig", ConfigStub)
    monkeypatch.setattr(manage, "alembic_command", CommandStub)

    result = CliRunner().invoke(manage.app, ["db-check"])

    assert result.exit_code == 0
    assert calls[0] == (
        "config",
        str(Path(manage.__file__).resolve().parent / "alembic.ini"),
    )
    assert calls[1][0] == "check"


def test_db_check_rejects_default_alembic_database_url(monkeypatch):
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)

    result = CliRunner().invoke(manage.app, ["db-check"])

    assert result.exit_code == 2
    assert "ALEMBIC_DATABASE_URL" in result.stderr
    assert "configured explicitly" in result.stderr


def test_db_check_accepts_alembic_database_url_from_dotenv(
    monkeypatch,
    tmp_path,
):
    calls = []
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ALEMBIC_DATABASE_URL=postgresql://app:secret@db.example:6543/app_test\n",
        encoding="utf-8",
    )

    class CommandStub:

        @staticmethod
        def check(config):
            calls.append(("check", config))

    monkeypatch.setattr(manage, "alembic_command", CommandStub)

    result = CliRunner().invoke(manage.app, ["db-check"])

    assert result.exit_code == 0
    assert calls[0][0] == "check"
    assert "db.example:6543/app_test" in result.stderr
    assert "secret" not in result.stderr


def test_db_check_accepts_default_value_when_it_is_set_in_dotenv(
    monkeypatch,
    tmp_path,
):
    calls = []
    monkeypatch.delenv("ALEMBIC_DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app\n",
        encoding="utf-8",
    )

    class CommandStub:

        @staticmethod
        def check(config):
            calls.append(("check", config))

    monkeypatch.setattr(manage, "alembic_command", CommandStub)

    result = CliRunner().invoke(manage.app, ["db-check"])

    assert result.exit_code == 0
    assert calls[0][0] == "check"
    assert "postgresql://localhost:5432/app" in result.stderr


def test_db_downgrade_requires_explicit_revision():
    result = CliRunner().invoke(manage.app, ["db-downgrade"])

    assert result.exit_code == 2
    assert "Missing argument" in result.stderr


def test_db_upgrade_and_downgrade_use_explicit_command_names():
    command_names = {
        command.name
        for command in manage.app.registered_commands
        if command.callback in {manage.db_upgrade, manage.db_downgrade}
    }

    assert command_names == {"db-upgrade", "db-downgrade"}
