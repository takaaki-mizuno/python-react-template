import tomllib
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

import manage


def test_serve_accepts_runtime_options(monkeypatch):
    calls = []

    def run_stub(**kwargs):
        calls.append(kwargs)

    monkeypatch.setitem(__import__("sys").modules, "uvicorn", SimpleNamespace(run=run_stub))

    result = CliRunner().invoke(
        manage.app,
        [
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            "9000",
            "--no-reload",
            "--workers",
            "2",
        ],
    )

    assert result.exit_code == 0
    assert calls == [{
        "app": "app.main:app",
        "host": "127.0.0.1",
        "port": 9000,
        "reload": False,
        "workers": 2,
        "log_level": "info",
    }]


def test_serve_rejects_reload_with_multiple_workers():
    result = CliRunner().invoke(manage.app, ["serve", "--reload", "--workers", "2"])

    assert result.exit_code == 2
    assert "reload" in result.stderr
    assert "workers" in result.stderr


def test_serve_rejects_invalid_port():
    result = CliRunner().invoke(manage.app, ["serve", "--port", "not-a-number"])

    assert result.exit_code == 2
    assert "not-a-number" in result.stderr


def test_serve_accepts_log_level(monkeypatch):
    calls = []

    def run_stub(**kwargs):
        calls.append(kwargs)

    monkeypatch.setitem(__import__("sys").modules, "uvicorn", SimpleNamespace(run=run_stub))

    result = CliRunner().invoke(manage.app, ["serve", "--no-reload", "--log-level", "debug"])

    assert result.exit_code == 0
    assert calls[0]["log_level"] == "debug"


def test_serve_defaults_to_no_reload_in_production(monkeypatch):
    calls = []

    def run_stub(**kwargs):
        calls.append(kwargs)

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", SimpleNamespace(run=run_stub))

    result = CliRunner().invoke(manage.app, ["serve"])

    assert result.exit_code == 0
    assert calls[0]["reload"] is False


def test_serve_defaults_to_reload_in_local(monkeypatch):
    calls = []

    def run_stub(**kwargs):
        calls.append(kwargs)

    monkeypatch.setenv("ENVIRONMENT", "local")
    monkeypatch.setitem(__import__("sys").modules, "uvicorn", SimpleNamespace(run=run_stub))

    result = CliRunner().invoke(manage.app, ["serve"])

    assert result.exit_code == 0
    assert calls[0]["reload"] is True


def test_db_check_invokes_alembic_check(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

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


def test_db_check_rejects_default_database_url(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(manage.app, ["db-check"])

    assert result.exit_code == 2
    assert "DATABASE_URL" in result.stderr
    assert "configured explicitly" in result.stderr


def test_db_check_rejects_alembic_database_url_only(monkeypatch, tmp_path):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("ALEMBIC_DATABASE_URL", "postgresql://app:app@localhost:5432/app_test")
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(manage.app, ["db-check"])

    assert result.exit_code == 2
    assert "DATABASE_URL" in result.stderr


def test_db_check_accepts_database_url_from_dotenv(
    monkeypatch,
    tmp_path,
):
    calls = []
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://app:secret@db.example:6543/app_test\n",
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
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app\n",
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
    assert "postgresql+asyncpg://localhost:5432/app" in result.stderr


def test_db_upgrade_requires_explicit_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(manage.app, ["db-upgrade"])

    assert result.exit_code == 2
    assert "DATABASE_URL" in result.stderr
    assert "configured explicitly" in result.stderr


def test_db_upgrade_invokes_alembic_upgrade_when_database_url_is_explicit(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class CommandStub:

        @staticmethod
        def upgrade(config, revision):
            calls.append(("upgrade", config, revision))

    monkeypatch.setattr(manage, "alembic_command", CommandStub)

    result = CliRunner().invoke(manage.app, ["db-upgrade"])

    assert result.exit_code == 0
    assert calls[0][0] == "upgrade"
    assert calls[0][2] == "head"


def test_db_downgrade_requires_explicit_revision():
    result = CliRunner().invoke(manage.app, ["db-downgrade"])

    assert result.exit_code == 2
    assert "Missing option" in result.stderr
    assert "--revision" in result.stderr


def test_db_downgrade_requires_explicit_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(manage.app, ["db-downgrade", "--revision", "base"])

    assert result.exit_code == 2
    assert "DATABASE_URL" in result.stderr
    assert "configured explicitly" in result.stderr


def test_db_downgrade_accepts_revision_option(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class ConfigStub:

        def __init__(self, path):
            calls.append(("config", path))

    class CommandStub:

        @staticmethod
        def downgrade(config, revision):
            calls.append(("downgrade", revision, config))

    monkeypatch.setattr(manage, "AlembicConfig", ConfigStub)
    monkeypatch.setattr(manage, "alembic_command", CommandStub)

    result = CliRunner().invoke(manage.app, ["db-downgrade", "--revision", "base"])

    assert result.exit_code == 0
    assert calls[1][0] == "downgrade"
    assert calls[1][1] == "base"


def test_db_upgrade_and_downgrade_use_explicit_command_names():
    command_names = {
        command.name
        for command in manage.app.registered_commands
        if command.callback in {manage.db_upgrade, manage.db_downgrade}
    }

    assert command_names == {"db-upgrade", "db-downgrade"}


def test_version_reads_project_version_from_pyproject():
    pyproject = Path(manage.__file__).resolve().parent / "pyproject.toml"
    expected_version = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]

    result = CliRunner().invoke(manage.app, ["version"])

    assert result.exit_code == 0
    assert f"Version: {expected_version}" in result.stdout


def test_db_revision_autogenerate_requires_explicit_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(
        manage.app,
        ["db-revision", "--message", "create sample items", "--autogenerate"],
    )

    assert result.exit_code == 2
    assert "DATABASE_URL" in result.stderr
    assert "configured explicitly" in result.stderr


def test_db_revision_autogenerate_checks_head_before_creating_revision(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class CommandStub:

        @staticmethod
        def revision(config, message, autogenerate, rev_id=None):
            calls.append(("revision", config, message, autogenerate, rev_id))

    monkeypatch.setattr(manage, "alembic_command", CommandStub)
    monkeypatch.setattr(manage, "_ensure_database_is_at_head", lambda config: calls.append(
        ("head", config)))

    result = CliRunner().invoke(
        manage.app,
        ["db-revision", "--message", "create sample items", "--autogenerate"],
    )

    assert result.exit_code == 0
    assert calls[0][0] == "head"
    assert calls[1][0] == "revision"
    assert calls[1][2] == "create sample items"
    assert calls[1][3] is True
    assert calls[1][4] is None


def test_db_revision_accepts_explicit_revision_id(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class CommandStub:

        @staticmethod
        def revision(config, message, autogenerate, rev_id=None):
            calls.append(("revision", config, message, autogenerate, rev_id))

    monkeypatch.setattr(manage, "alembic_command", CommandStub)
    monkeypatch.setattr(manage, "_ensure_database_is_at_head", lambda config: calls.append(
        ("head", config)))

    result = CliRunner().invoke(
        manage.app,
        [
            "db-revision",
            "--message",
            "create sample items",
            "--autogenerate",
            "--rev-id",
            "20260802_0002",
        ],
    )

    assert result.exit_code == 0
    assert calls[1][0] == "revision"
    assert calls[1][2] == "create sample items"
    assert calls[1][3] is True
    assert calls[1][4] == "20260802_0002"


def test_db_revision_requires_message():
    result = CliRunner().invoke(manage.app, ["db-revision", "--autogenerate"])

    assert result.exit_code == 2
    assert "message" in result.stderr


def test_db_prune_auth_requires_at_least_one_threshold():
    result = CliRunner().invoke(manage.app, ["db-prune-auth"])

    assert result.exit_code == 2
    assert "at least one" in result.stderr


def test_db_prune_auth_prunes_expired_sessions_only(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class RepositoryStub:

        async def delete_sessions_expired_before(self, expired_before):
            calls.append(("sessions", expired_before))
            return 3

        async def delete_audit_logs_created_before(self, created_before):
            calls.append(("audit", created_before))
            return 5

    class InjectorStub:

        def get(self, _interface):
            return RepositoryStub()

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(
        manage.app,
        ["db-prune-auth", "--expired-sessions-before", "2026-08-01T00:00:00+00:00"],
    )

    assert result.exit_code == 0
    assert [call[0] for call in calls] == ["sessions"]
    assert "Deleted expired sessions: 3" in result.stdout


def test_db_prune_auth_prunes_audit_logs_only(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class RepositoryStub:

        async def delete_sessions_expired_before(self, expired_before):
            calls.append(("sessions", expired_before))
            return 3

        async def delete_audit_logs_created_before(self, created_before):
            calls.append(("audit", created_before))
            return 5

    class InjectorStub:

        def get(self, _interface):
            return RepositoryStub()

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(
        manage.app,
        ["db-prune-auth", "--audit-logs-before", "2026-08-01T00:00:00+00:00"],
    )

    assert result.exit_code == 0
    assert [call[0] for call in calls] == ["audit"]
    assert "Deleted audit logs: 5" in result.stdout


def test_db_prune_auth_prunes_audit_logs_before_sessions(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class RepositoryStub:

        async def delete_sessions_expired_before(self, expired_before):
            calls.append(("sessions", expired_before))
            return 3

        async def delete_audit_logs_created_before(self, created_before):
            calls.append(("audit", created_before))
            return 5

    class InjectorStub:

        def get(self, _interface):
            return RepositoryStub()

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(
        manage.app,
        [
            "db-prune-auth",
            "--expired-sessions-before",
            "2026-08-01T00:00:00+00:00",
            "--audit-logs-before",
            "2026-08-01T00:00:00+00:00",
        ],
    )

    assert result.exit_code == 0
    assert [call[0] for call in calls] == ["audit", "sessions"]


def test_db_prune_auth_rejects_naive_datetime(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    result = CliRunner().invoke(
        manage.app,
        ["db-prune-auth", "--expired-sessions-before", "2026-08-01T00:00:00"],
    )

    assert result.exit_code == 2
    assert "timezone offset" in result.stderr


def test_db_prune_auth_rejects_invalid_datetime_before_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(
        manage.app,
        ["db-prune-auth", "--expired-sessions-before", "garbage"],
    )

    assert result.exit_code == 2
    assert "ISO 8601 datetime" in result.stderr
    assert "DATABASE_URL" not in result.stderr
