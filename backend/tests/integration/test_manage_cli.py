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


def test_authz_sync_creates_default_authorization_definitions(monkeypatch, ):
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())

    result = CliRunner().invoke(manage.app, ["authz-sync"])

    assert result.exit_code == 0
    assert "Authorization definitions synced." in result.stdout
    role_codes = _fetch_scalars("SELECT code FROM roles ORDER BY code")
    permission_codes = _fetch_scalars("SELECT code FROM permissions ORDER BY code")
    role_permission_count = _fetch_scalar("SELECT count(*) FROM role_permissions")
    assert role_codes == ["admin"]
    assert permission_codes == ["admin:access"]
    assert role_permission_count == 1


def test_authz_grant_role_grants_inactive_user_and_records_audit(monkeypatch, ):
    monkeypatch.setenv("DATABASE_URL", require_test_database_url())
    sync_result = CliRunner().invoke(manage.app, ["authz-sync"])
    assert sync_result.exit_code == 0
    user = _create_inactive_user("inactive-cli@example.com")

    result = CliRunner().invoke(
        manage.app,
        ["authz-grant-role", "--email", "Inactive-CLI@Example.com", "--role", "admin"],
    )

    assert result.exit_code == 0
    assigned_roles = _fetch_scalars(
        "SELECT roles.code FROM user_roles "
        "JOIN roles ON roles.id = user_roles.role_id "
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


async def _run_db(operation: Callable[[AsyncSession], Awaitable]):
    engine = create_async_engine(require_test_database_url(), poolclass=NullPool)
    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    try:
        async with session_factory() as session:
            return await operation(session)
    finally:
        await engine.dispose()
