import tomllib
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

from typer.testing import CliRunner

import manage
from app.interfaces.services.admin_user_repository_interface import AdminUserRepositoryInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.auth_event_type import AuthEventType
from app.models.authorization import UnknownRoleAssignment, UserRoleReplacementResult
from app.models.user import User


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

        async def delete_oidc_states_expired_before(self, expired_before):
            calls.append(("oidc_states", expired_before))
            return 7

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

        async def delete_oidc_states_expired_before(self, expired_before):
            calls.append(("oidc_states", expired_before))
            return 7

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

        async def delete_oidc_states_expired_before(self, expired_before):
            calls.append(("oidc_states", expired_before))
            return 7

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


def test_db_prune_auth_prunes_oidc_states(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class RepositoryStub:

        async def delete_sessions_expired_before(self, expired_before):
            calls.append(("sessions", expired_before))
            return 3

        async def delete_audit_logs_created_before(self, created_before):
            calls.append(("audit", created_before))
            return 5

        async def delete_oidc_states_expired_before(self, expired_before):
            calls.append(("oidc_states", expired_before))
            return 7

    class InjectorStub:

        def get(self, _interface):
            return RepositoryStub()

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(
        manage.app,
        ["db-prune-auth", "--oidc-states-before", "2026-08-01T00:00:00+00:00"],
    )

    assert result.exit_code == 0
    assert [call[0] for call in calls] == ["oidc_states"]
    assert "Deleted OIDC authorization states: 7" in result.stdout


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


def test_authz_check_config_passes_for_default_definitions():
    result = CliRunner().invoke(manage.app, ["authz-check-config"])

    assert result.exit_code == 0
    assert "Authorization config is valid." in result.stdout


def test_authz_check_config_reports_invalid_config(monkeypatch):
    monkeypatch.setattr(manage, "authorization_config_errors", lambda: ["broken config"])

    result = CliRunner().invoke(manage.app, ["authz-check-config"])

    assert result.exit_code == 1
    assert "Authorization config is invalid." in result.stderr
    assert "broken config" in result.stderr


def test_authz_check_assignments_reports_unknown_role_assignments(monkeypatch):
    user_id = uuid4()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class AuthorizationRepositoryStub:

        async def list_unknown_role_assignments(self, known_role_codes):
            assert known_role_codes == frozenset({"admin"})
            return (UnknownRoleAssignment(user_id=user_id, role_code="deleted-role"), )

    class InjectorStub:

        def get(self, interface):
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            raise AssertionError(interface)

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(manage.app, ["authz-check-assignments"])

    assert result.exit_code == 1
    assert "Unknown role assignments found." in result.stderr
    assert f"user_id={user_id} role_code=deleted-role" in result.stderr


def test_authz_check_assignments_rejects_invalid_config_before_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(manage, "authorization_config_errors", lambda: ["broken config"])

    result = CliRunner().invoke(manage.app, ["authz-check-assignments"])

    assert result.exit_code == 1
    assert "Authorization config is invalid." in result.stderr
    assert "broken config" in result.stderr
    assert "DATABASE_URL" not in result.stderr


def test_authz_check_assignments_passes_when_assignments_are_known(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class AuthorizationRepositoryStub:

        async def list_unknown_role_assignments(self, _known_role_codes):
            return ()

    class InjectorStub:

        def get(self, interface):
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            raise AssertionError(interface)

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(manage.app, ["authz-check-assignments"])

    assert result.exit_code == 0
    assert "Authorization assignments are valid." in result.stdout


def test_authz_prune_unknown_role_assignments_requires_yes_before_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(manage.app, ["authz-prune-unknown-role-assignments"])

    assert result.exit_code == 1
    assert "Pass --yes" in result.stderr
    assert "DATABASE_URL" not in result.stderr


def test_authz_prune_unknown_role_assignments_rejects_invalid_config_before_database_url(
    monkeypatch, ):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(manage, "authorization_config_errors", lambda: ["broken config"])

    result = CliRunner().invoke(manage.app, ["authz-prune-unknown-role-assignments", "--yes"])

    assert result.exit_code == 1
    assert "Authorization config is invalid." in result.stderr
    assert "broken config" in result.stderr
    assert "DATABASE_URL" not in result.stderr


def test_authz_prune_unknown_role_assignments_deletes_and_audits(monkeypatch):
    user_id = uuid4()
    audit_logs = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class UnitOfWorkStub:

        @asynccontextmanager
        async def transaction(self):
            yield

    class AuthRepositoryStub:

        async def create_audit_log(self, audit_log):
            audit_logs.append(audit_log)

    class AuthorizationRepositoryStub:

        async def list_unknown_role_assignments(self, known_role_codes):
            assert known_role_codes == frozenset({"admin"})
            return (UnknownRoleAssignment(user_id=user_id, role_code="deleted-role"), )

        async def delete_unknown_role_assignments(self, known_role_codes):
            assert known_role_codes == frozenset({"admin"})
            return 1

    class InjectorStub:

        def get(self, interface):
            if interface is UnitOfWorkInterface:
                return UnitOfWorkStub()
            if interface is AuthRepositoryInterface:
                return AuthRepositoryStub()
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            raise AssertionError(interface)

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(manage.app, ["authz-prune-unknown-role-assignments", "--yes"])

    assert result.exit_code == 0
    assert "Deleted 1 unknown role assignment(s)." in result.stdout
    assert len(audit_logs) == 1
    assert audit_logs[0].event_type == AuthEventType.ROLE_REVOKED
    assert audit_logs[0].detail_json == {
        "source": "cli-prune",
        "actorUserId": None,
        "targetUserId": str(user_id),
        "roleCode": "deleted-role",
    }


def test_authz_grant_role_records_cli_audit(monkeypatch):
    user = User(id=uuid4(), email="admin@example.com", password_hash="hash")
    audit_logs = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class UnitOfWorkStub:

        @asynccontextmanager
        async def transaction(self):
            yield

    class AuthRepositoryStub:

        async def find_user_by_email(self, email):
            assert email == "admin@example.com"
            return user

        async def create_audit_log(self, audit_log):
            audit_logs.append(audit_log)

    class AuthorizationRepositoryStub:

        async def get_user_role_codes(self, user_id):
            assert user_id == user.id
            return ()

        async def replace_user_roles(self, user_id, role_codes, assigned_by_user_id):
            assert user_id == user.id
            assert role_codes == ("admin", )
            assert assigned_by_user_id is None
            return UserRoleReplacementResult(
                user_id=user_id,
                granted_role_codes=("admin", ),
                revoked_role_codes=(),
                current_role_codes=("admin", ),
            )

    class InjectorStub:

        def get(self, interface):
            if interface is UnitOfWorkInterface:
                return UnitOfWorkStub()
            if interface is AuthRepositoryInterface:
                return AuthRepositoryStub()
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            raise AssertionError(interface)

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(
        manage.app,
        ["authz-grant-role", "--email", "Admin@Example.com", "--role", "admin"],
    )

    assert result.exit_code == 0
    assert len(audit_logs) == 1
    assert audit_logs[0].user_id is None
    assert audit_logs[0].session_id is None
    assert audit_logs[0].event_type == AuthEventType.ROLE_GRANTED
    assert audit_logs[0].detail_json == {
        "source": "cli",
        "actorUserId": None,
        "targetUserId": str(user.id),
        "roleCode": "admin",
        "resultingRoles": ["admin"],
    }


def test_authz_grant_role_exits_when_user_is_not_found(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class UnitOfWorkStub:

        @asynccontextmanager
        async def transaction(self):
            yield

    class AuthRepositoryStub:

        async def find_user_by_email(self, email):
            assert email == "missing@example.com"
            return None

    class AuthorizationRepositoryStub:
        pass

    class InjectorStub:

        def get(self, interface):
            if interface is UnitOfWorkInterface:
                return UnitOfWorkStub()
            if interface is AuthRepositoryInterface:
                return AuthRepositoryStub()
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            raise AssertionError(interface)

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(
        manage.app,
        ["authz-grant-role", "--email", "Missing@Example.com", "--role", "admin"],
    )

    assert result.exit_code == 1
    assert "User not found." in result.stderr


def test_authz_grant_role_exits_when_role_is_not_found_before_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(
        manage.app,
        ["authz-grant-role", "--email", "Admin@Example.com", "--role", "missing"],
    )

    assert result.exit_code == 1
    assert "Role not found: missing" in result.stderr
    assert "DATABASE_URL" not in result.stderr


def test_seed_admin_rejects_production_before_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(manage, "get_config", lambda: SimpleNamespace(ENVIRONMENT="production"))

    result = CliRunner().invoke(manage.app, ["seed-admin"])

    assert result.exit_code == 1
    assert "local/development only" in result.stderr
    assert "DATABASE_URL" not in result.stderr


def test_seed_admin_requires_database_url_in_local(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr(manage, "get_config", lambda: SimpleNamespace(ENVIRONMENT="local"))

    result = CliRunner().invoke(manage.app, ["seed-admin"])

    assert result.exit_code == 2
    assert "DATABASE_URL must be configured explicitly for seed-admin" in result.stderr


def test_seed_admin_creates_user_assigns_role_and_audits(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")
    monkeypatch.setattr(manage, "get_config", lambda: SimpleNamespace(ENVIRONMENT="local"))
    audit_logs = []
    created_users = []

    class UnitOfWorkStub:

        @asynccontextmanager
        async def transaction(self):
            yield

    class PasswordHashExecutorStub:

        async def hash(self, raw_password):
            assert raw_password == "Password@123!"
            return "hashed-password"

    class AuthRepositoryStub:

        async def find_user_by_email(self, email):
            assert email == "admin@example.com"
            return None

        async def create_audit_log(self, audit_log):
            audit_logs.append(audit_log)

    class AdminUserRepositoryStub:

        async def create_user(self, email, password_hash, is_active):
            assert email == "admin@example.com"
            assert password_hash == "hashed-password"
            assert is_active is True
            user = User(id=uuid4(), email=email, password_hash=password_hash, is_active=True)
            created_users.append(user)
            return user

    class AuthorizationRepositoryStub:

        async def get_user_role_codes(self, user_id):
            assert user_id == created_users[0].id
            return ()

        async def replace_user_roles(self, user_id, role_codes, assigned_by_user_id):
            assert user_id == created_users[0].id
            assert role_codes == ("admin", )
            assert assigned_by_user_id is None
            return UserRoleReplacementResult(
                user_id=user_id,
                granted_role_codes=("admin", ),
                revoked_role_codes=(),
                current_role_codes=("admin", ),
            )

    class InjectorStub:

        def get(self, interface):
            if interface is UnitOfWorkInterface:
                return UnitOfWorkStub()
            if interface is AuthRepositoryInterface:
                return AuthRepositoryStub()
            if interface is AdminUserRepositoryInterface:
                return AdminUserRepositoryStub()
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            if interface is manage.PasswordHashExecutor:
                return PasswordHashExecutorStub()
            raise AssertionError(interface)

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(manage.app, ["seed-admin"])

    assert result.exit_code == 0
    assert "Seeded admin user admin@example.com." in result.stdout
    assert "Password@123!" not in result.stdout
    assert audit_logs[0].event_type == AuthEventType.ROLE_GRANTED
    assert audit_logs[0].detail_json == {
        "source": "cli-seed-admin",
        "actorUserId": None,
        "targetUserId": str(created_users[0].id),
        "roleCode": "admin",
        "resultingRoles": ["admin"],
    }


def test_seed_admin_updates_existing_user_and_is_idempotent_when_role_exists(monkeypatch):
    user = User(id=uuid4(), email="admin@example.com", password_hash="old", is_active=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")
    monkeypatch.setattr(manage, "get_config", lambda: SimpleNamespace(ENVIRONMENT="development"))
    audit_logs = []
    updates = []

    class UnitOfWorkStub:

        @asynccontextmanager
        async def transaction(self):
            yield

    class PasswordHashExecutorStub:

        async def hash(self, raw_password):
            assert raw_password == "Password@123!"
            return "new-hash"

    class AuthRepositoryStub:

        async def find_user_by_email(self, email):
            assert email == "admin@example.com"
            return user

        async def create_audit_log(self, audit_log):
            audit_logs.append(audit_log)

    class AdminUserRepositoryStub:

        async def update_user(self, user_id, changes, password_hash):
            updates.append((user_id, changes, password_hash))
            user.password_hash = password_hash
            user.is_active = changes.is_active
            return user

    class AuthorizationRepositoryStub:

        async def get_user_role_codes(self, user_id):
            assert user_id == user.id
            return ("admin", )

        async def replace_user_roles(self, user_id, role_codes, assigned_by_user_id):
            assert user_id == user.id
            assert role_codes == ("admin", )
            assert assigned_by_user_id is None
            return UserRoleReplacementResult(
                user_id=user_id,
                granted_role_codes=(),
                revoked_role_codes=(),
                current_role_codes=("admin", ),
            )

    class InjectorStub:

        def get(self, interface):
            if interface is UnitOfWorkInterface:
                return UnitOfWorkStub()
            if interface is AuthRepositoryInterface:
                return AuthRepositoryStub()
            if interface is AdminUserRepositoryInterface:
                return AdminUserRepositoryStub()
            if interface is AuthorizationRepositoryInterface:
                return AuthorizationRepositoryStub()
            if interface is manage.PasswordHashExecutor:
                return PasswordHashExecutorStub()
            raise AssertionError(interface)

    async def run_with_container_stub(operation):
        return await operation(InjectorStub())

    monkeypatch.setattr(manage, "run_with_container", run_with_container_stub)

    result = CliRunner().invoke(manage.app, ["seed-admin"])

    assert result.exit_code == 0
    assert updates[0][2] == "new-hash"
    assert updates[0][1].is_active is True
    assert audit_logs == []
