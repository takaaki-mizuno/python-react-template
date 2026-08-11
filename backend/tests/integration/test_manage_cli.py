import asyncio
from collections.abc import Awaitable, Callable

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool
from sqlmodel.ext.asyncio.session import AsyncSession
from typer.testing import CliRunner

import manage
from app.libraries.password_hasher import hash_password
from app.models.auth_event_type import AuthEventType
from app.models.user import User
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
            "--oidc-states-before",
            "2026-08-01T00:00:00+00:00",
        ],
    )

    assert result.exit_code == 0
    assert "Deleted audit logs:" in result.stdout
    assert "Deleted expired sessions:" in result.stdout
    assert "Deleted OIDC authorization states:" in result.stdout


def test_authz_check_config_runs_without_database(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)

    result = CliRunner().invoke(manage.app, ["authz-check-config"])

    assert result.exit_code == 0
    assert "Authorization config is valid." in result.stdout


def test_authz_grant_role_grants_inactive_user_and_records_audit(monkeypatch, ):
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())
    user = _create_inactive_user("inactive-cli@example.com")

    result = CliRunner().invoke(
        manage.app,
        ["authz-grant-role", "--email", "Inactive-CLI@Example.com", "--role", "admin"],
    )

    assert result.exit_code == 0
    assigned_roles = _fetch_scalars(
        "SELECT role_code FROM user_roles "
        "WHERE user_roles.user_id = :user_id",
        {"user_id": user.id},
    )
    audit_detail = _fetch_scalar(
        "SELECT detail_json FROM auth_audit_logs WHERE event_type = :event_type",
        {"event_type": AuthEventType.ROLE_GRANTED},
    )
    assert assigned_roles == ["admin"]
    assert audit_detail["source"] == "cli"
    assert audit_detail["targetUserId"] == str(user.id)
    assert audit_detail["roleCode"] == "admin"


def test_authz_check_assignments_reports_unknown_roles(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())
    user = _create_inactive_user("unknown-assignment@example.com")
    _insert_role_assignment(user.id, "deleted-role")

    result = CliRunner().invoke(manage.app, ["authz-check-assignments"])

    assert result.exit_code == 1
    assert "Unknown role assignments found." in result.stderr
    assert "deleted-role" in result.stderr


def test_authz_prune_unknown_role_assignments_requires_yes_and_preserves_rows(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())
    user = _create_inactive_user("prune-requires-yes@example.com")
    _insert_role_assignment(user.id, "deleted-role")

    result = CliRunner().invoke(manage.app, ["authz-prune-unknown-role-assignments"])
    assigned_roles = _fetch_scalars(
        "SELECT role_code FROM user_roles WHERE user_id = :user_id",
        {"user_id": user.id},
    )

    assert result.exit_code == 1
    assert "Pass --yes" in result.stderr
    assert assigned_roles == ["deleted-role"]


def test_authz_prune_unknown_role_assignments_deletes_unknown_and_audits(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())
    known_user = _create_inactive_user("known-prune@example.com")
    unknown_user = _create_inactive_user("unknown-prune@example.com")
    _insert_role_assignment(known_user.id, "admin")
    _insert_role_assignment(unknown_user.id, "deleted-role")

    result = CliRunner().invoke(manage.app, ["authz-prune-unknown-role-assignments", "--yes"])

    known_roles = _fetch_scalars(
        "SELECT role_code FROM user_roles WHERE user_id = :user_id",
        {"user_id": known_user.id},
    )
    unknown_roles = _fetch_scalars(
        "SELECT role_code FROM user_roles WHERE user_id = :user_id",
        {"user_id": unknown_user.id},
    )
    audit_detail = _fetch_scalar(
        "SELECT detail_json FROM auth_audit_logs WHERE event_type = :event_type",
        {"event_type": AuthEventType.ROLE_REVOKED},
    )
    assert result.exit_code == 0
    assert "Deleted 1 unknown role assignment(s)." in result.stdout
    assert known_roles == ["admin"]
    assert unknown_roles == []
    assert audit_detail["source"] == "cli-prune"
    assert audit_detail["targetUserId"] == str(unknown_user.id)
    assert audit_detail["roleCode"] == "deleted-role"


def test_seed_admin_creates_admin_user_and_is_idempotent(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())
    monkeypatch.setenv("ENVIRONMENT", "local")

    first_result = CliRunner().invoke(manage.app, ["seed-admin"])
    second_result = CliRunner().invoke(manage.app, ["seed-admin"])

    user_rows = _fetch_scalars(
        "SELECT email FROM users WHERE lower(email) = 'admin@example.com' "
        "AND deleted_at IS NULL", )
    role_rows = _fetch_scalars(
        "SELECT role_code FROM user_roles "
        "JOIN users ON users.id = user_roles.user_id "
        "WHERE lower(users.email) = 'admin@example.com'", )
    audit_count = _fetch_scalar(
        "SELECT count(*) FROM auth_audit_logs WHERE event_type = :event_type",
        {"event_type": AuthEventType.ROLE_GRANTED},
    )
    assert first_result.exit_code == 0
    assert second_result.exit_code == 0
    assert user_rows == ["admin@example.com"]
    assert role_rows == ["admin"]
    assert audit_count == 1


def _fetch_scalars(statement: str, params: dict | None = None):

    async def operation(session: AsyncSession):
        return (await session.execute(text(statement), params or {})).scalars().all()

    return asyncio.run(_run_db(operation))


def _fetch_scalar(statement: str, params: dict | None = None):

    async def operation(session: AsyncSession):
        return await session.scalar(text(statement), params or {})

    return asyncio.run(_run_db(operation))


def _create_inactive_user(email: str) -> User:

    async def operation(session: AsyncSession):
        user = User(
            email=email,
            password_hash=hash_password("Password123!"),
            is_active=False,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user

    return asyncio.run(_run_db(operation))


def _insert_role_assignment(user_id, role_code: str) -> None:

    async def operation(session: AsyncSession):
        await session.execute(
            text("""
                INSERT INTO user_roles (user_id, role_code, assigned_at, assigned_by_user_id)
                VALUES (:user_id, :role_code, now(), NULL)
            """),
            {
                "user_id": user_id,
                "role_code": role_code,
            },
        )
        await session.commit()

    asyncio.run(_run_db(operation))


async def _run_db(operation: Callable[[AsyncSession], Awaitable]):
    engine = create_async_engine(require_test_database_url(), poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return await operation(session)
    finally:
        await engine.dispose()
