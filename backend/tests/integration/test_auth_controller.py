import asyncio
import os
from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.bootstrap.create_app import create_app
from app.config.auth import AuthSettings
from app.interfaces.services.auth_repository_interface import \
    AuthRepositoryInterface
from app.libraries.password_hasher import hash_password
from app.libraries.session_tokens import hash_token
from app.models.auth_event_type import AuthEventType
from app.models.user import User

pytestmark = pytest.mark.integration


def test_auth_cookie_security_uses_startup_settings(monkeypatch):
    test_database_url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("ENVIRONMENT", "local")
    app = create_app()

    with TestClient(app) as client:
        startup_settings = client.app.state.injector.get(AuthSettings)
        assert startup_settings.ENVIRONMENT == "local"
        monkeypatch.setenv("ENVIRONMENT", "production")

        response = client.get("/api/auth/csrf")

        csrf_cookie = SimpleCookie(response.headers["set-cookie"])
        assert csrf_cookie["csrf_token"]["secure"] == ""
        assert client.app.state.injector.get(AuthSettings) is startup_settings


def test_get_me_returns_401_without_session(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_auth_get_responses_disable_caching(client):
    csrf_response = client.get("/api/auth/csrf")
    client.post(
        "/api/auth/register",
        json={
            "email": "no-store@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_response.json()["csrfToken"]},
    )
    me_response = client.get("/api/auth/me")

    assert csrf_response.headers["Cache-Control"] == "no-store"
    assert me_response.headers["Cache-Control"] == "no-store"


def test_register_then_me_returns_current_user(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    register_response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert register_response.status_code == 201
    assert register_response.cookies.get("session_token")

    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_register_persists_only_session_and_csrf_token_hashes(
    client,
    async_session,
):
    initial_csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "token-storage@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": initial_csrf_token},
    )
    session_token = client.cookies.get("session_token")
    csrf_token = client.cookies.get("csrf_token")

    session_row = (await async_session.execute(
        text("SELECT session_token_hash, csrf_token_hash "
             "FROM auth_sessions"))).one()
    audit_rows = (await async_session.execute(
        text("SELECT row_to_json(audit)::text "
             "FROM auth_audit_logs AS audit"))).scalars().all()

    assert session_row.session_token_hash == hash_token(session_token)
    assert session_row.csrf_token_hash == hash_token(csrf_token)
    assert audit_rows
    assert all("Password123!" not in audit_row for audit_row in audit_rows)
    assert all(session_token not in audit_row for audit_row in audit_rows)
    assert all(csrf_token not in audit_row for audit_row in audit_rows)


@pytest.mark.asyncio
async def test_random_session_tokens_do_not_create_audit_rows(
    client,
    async_session,
):
    for index in range(3):
        client.cookies.set(
            "session_token",
            f"random-session-{index}",
            domain="testserver.local",
            path="/",
        )
        client.cookies.set(
            "csrf_token",
            f"random-csrf-{index}",
            domain="testserver.local",
            path="/",
        )
        client.get("/api/auth/csrf")
        client.get("/api/auth/me")

    audit_count = await async_session.scalar(
        text("SELECT count(*) FROM auth_audit_logs"))

    assert audit_count == 0


def test_get_csrf_is_idempotent_when_cookie_exists(client):
    first_response = client.get("/api/auth/csrf")
    second_response = client.get("/api/auth/csrf")

    assert second_response.json()["csrfToken"] == first_response.json(
    )["csrfToken"]
    assert second_response.cookies.get("csrf_token") is None


def test_register_duplicate_email_returns_409(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    first_response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert first_response.status_code == 201

    duplicate_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    duplicate_response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": duplicate_csrf},
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Email already registered"


def test_register_with_weak_password_returns_422(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    response = client.post(
        "/api/auth/register",
        json={
            "email": "weak@example.com",
            "password": "short",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_login_with_invalid_password_returns_generic_401(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    login_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    response = client.post(
        "/api/auth/login",
        json={
            "email": "user@example.com",
            "password": "wrong-password",
        },
        headers={"X-CSRF-Token": login_csrf},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_login_with_unregistered_email_returns_same_generic_401(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    response = client.post(
        "/api/auth/login",
        json={
            "email": "missing@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


@pytest.mark.asyncio
async def test_login_finds_case_insensitive_email(
    client,
    async_session,
):
    async_session.add(
        User(
            email="MixedCase@example.com",
            password_hash=hash_password("Password123!"),
        ))
    await async_session.commit()
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    response = client.post(
        "/api/auth/login",
        json={
            "email": "mixedcase@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 200
    assert response.json()["email"] == "MixedCase@example.com"


def test_login_rotates_existing_session_and_revokes_previous_one(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    original_session_token = client.cookies.get("session_token")

    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert login_response.status_code == 200
    assert client.cookies.get("session_token") != original_session_token

    old_session_response = client.get(
        "/api/auth/me",
        cookies={"session_token": original_session_token},
    )
    assert old_session_response.status_code == 401


def test_logout_clears_cookie_and_rejects_subsequent_me(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    logout_response = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert logout_response.status_code == 204
    set_cookie_headers = logout_response.headers.get_list("set-cookie")
    assert any("session_token=" in header and "Max-Age=0" in header
               for header in set_cookie_headers)

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401


def test_logout_rejects_csrf_token_not_bound_to_current_session(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )

    response = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": "attacker-token"},
        cookies={
            "session_token": client.cookies.get("session_token"),
            "csrf_token": "attacker-token",
        },
    )

    assert response.status_code == 403


def test_register_requires_matching_csrf_header(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": f"{csrf_token}-wrong"},
    )

    assert response.status_code == 403


def test_register_requires_csrf_cookie_and_header(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    missing_header_response = client.post(
        "/api/auth/register",
        json={
            "email": "missing-header@example.com",
            "password": "Password123!",
        },
    )
    missing_cookie_response = client.post(
        "/api/auth/register",
        json={
            "email": "missing-cookie@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
        cookies={"csrf_token": ""},
    )

    assert missing_header_response.status_code == 403
    assert missing_cookie_response.status_code == 403


def test_register_rate_limit_returns_429(client):
    for _ in range(5):
        csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
        client.post(
            "/api/auth/register",
            json={
                "email": "limited@example.com",
                "password": "Password123!",
            },
            headers={"X-CSRF-Token": csrf_token},
        )

    blocked_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    blocked_response = client.post(
        "/api/auth/register",
        json={
            "email": "limited@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": blocked_csrf},
    )

    assert blocked_response.status_code == 429


def test_register_and_login_share_rate_limit_bucket(client):
    for _ in range(5):
        csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
        client.post(
            "/api/auth/register",
            json={
                "email": "shared@example.com",
                "password": "Password123!",
            },
            headers={"X-CSRF-Token": csrf_token},
        )

    blocked_response = client.post(
        "/api/auth/login",
        json={
            "email": "shared@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert blocked_response.status_code == 429


def test_login_rate_limit_returns_429(client):
    for _ in range(5):
        csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
        client.post(
            "/api/auth/login",
            json={
                "email": "user@example.com",
                "password": "wrong-password",
            },
            headers={"X-CSRF-Token": csrf_token},
        )

    blocked_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    blocked_response = client.post(
        "/api/auth/login",
        json={
            "email": "user@example.com",
            "password": "wrong-password",
        },
        headers={"X-CSRF-Token": blocked_csrf},
    )

    assert blocked_response.status_code == 429


@pytest.mark.asyncio
async def test_me_rejects_expired_session(client, async_session):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    await async_session.execute(
        text("""
            UPDATE auth_sessions
            SET expires_at = now() - interval '1 second'
            WHERE session_token_hash = :session_token_hash
        """),
        {
            "session_token_hash": hash_token(
                client.cookies.get("session_token"))
        },
    )
    await async_session.commit()

    response = client.get("/api/auth/me")
    rejected_audit_count = await async_session.scalar(
        text("""
            SELECT count(*)
            FROM auth_audit_logs AS audit
            JOIN auth_sessions AS session
              ON audit.session_id = session.id
             AND audit.user_id = session.user_id
            WHERE audit.event_type = 'session_rejected'
        """))

    assert response.status_code == 401
    assert rejected_audit_count == 1


@pytest.mark.asyncio
async def test_me_rejects_revoked_session(client, async_session):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    await async_session.execute(
        text("""
            UPDATE auth_sessions
            SET revoked_at = now()
            WHERE session_token_hash = :session_token_hash
        """),
        {
            "session_token_hash": hash_token(
                client.cookies.get("session_token"))
        },
    )
    await async_session.commit()

    response = client.get("/api/auth/me")
    rejected_audit_count = await async_session.scalar(
        text("""
            SELECT count(*)
            FROM auth_audit_logs AS audit
            JOIN auth_sessions AS session
              ON audit.session_id = session.id
             AND audit.user_id = session.user_id
            WHERE audit.event_type = 'session_rejected'
        """))

    assert response.status_code == 401
    assert rejected_audit_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("session_state", ["expired", "revoked"])
async def test_login_recovers_from_inactive_session_cookie(
    client,
    async_session,
    session_state,
):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "recovery@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    session_token = client.cookies.get("session_token")
    assignment = ("expires_at = now() - interval '1 second'"
                  if session_state == "expired" else "revoked_at = now()")
    await async_session.execute(
        text(f"""
            UPDATE auth_sessions
            SET {assignment}
            WHERE session_token_hash = :session_token_hash
        """),
        {"session_token_hash": hash_token(session_token)},
    )
    await async_session.commit()

    response = client.post(
        "/api/auth/login",
        json={
            "email": "recovery@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert response.status_code == 200
    assert client.cookies.get("session_token") != session_token


@pytest.mark.asyncio
@pytest.mark.parametrize("session_state", ["expired", "revoked"])
async def test_register_recovers_from_inactive_session_cookie(
    client,
    async_session,
    session_state,
):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "original@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assignment = ("expires_at = now() - interval '1 second'"
                  if session_state == "expired" else "revoked_at = now()")
    await async_session.execute(
        text(f"""
            UPDATE auth_sessions
            SET {assignment}
            WHERE session_token_hash = :session_token_hash
        """),
        {
            "session_token_hash": hash_token(
                client.cookies.get("session_token"))
        },
    )
    await async_session.commit()

    response = client.post(
        "/api/auth/register",
        json={
            "email": "replacement@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert response.status_code == 201


def test_csrf_endpoint_repairs_active_session_cookie_desynchronization(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "csrf-recovery@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    client.cookies.set(
        "csrf_token",
        "desynchronized-token",
        domain="testserver.local",
        path="/",
    )

    csrf_response = client.get("/api/auth/csrf")
    repaired_token = csrf_response.json()["csrfToken"]
    login_response = client.post(
        "/api/auth/login",
        json={
            "email": "csrf-recovery@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": repaired_token},
    )

    assert repaired_token != "desynchronized-token"
    assert login_response.status_code == 200


@pytest.mark.asyncio
async def test_register_rolls_back_when_success_audit_fails(
    client,
    async_session,
    monkeypatch,
):
    repository = client.app.state.injector.get(AuthRepositoryInterface)
    original_create_audit_log = repository.create_audit_log

    async def fail_success_audit(audit_log):
        if audit_log.event_type == AuthEventType.REGISTER_SUCCESS:
            raise RuntimeError("audit write failed")
        await original_create_audit_log(audit_log)

    monkeypatch.setattr(repository, "create_audit_log", fail_success_audit)
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    with pytest.raises(RuntimeError, match="audit write failed"):
        client.post(
            "/api/auth/register",
            json={
                "email": "rollback@example.com",
                "password": "Password123!",
            },
            headers={"X-CSRF-Token": csrf_token},
        )

    user_count = await async_session.scalar(
        text("SELECT count(*) FROM users WHERE email = 'rollback@example.com'")
    )
    session_count = await async_session.scalar(
        text("SELECT count(*) FROM auth_sessions"))

    assert user_count == 0
    assert session_count == 0


@pytest.mark.asyncio
async def test_login_rolls_back_session_rotation_when_success_audit_fails(
    client,
    async_session,
    monkeypatch,
):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "login-rollback@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    original_session_token = client.cookies.get("session_token")
    original_login_at = await async_session.scalar(
        text("SELECT last_login_at FROM users "
             "WHERE email = 'login-rollback@example.com'"))
    repository = client.app.state.injector.get(AuthRepositoryInterface)
    original_create_audit_log = repository.create_audit_log

    async def fail_success_audit(audit_log):
        if audit_log.event_type == AuthEventType.LOGIN_SUCCESS:
            raise RuntimeError("audit write failed")
        await original_create_audit_log(audit_log)

    monkeypatch.setattr(repository, "create_audit_log", fail_success_audit)

    with pytest.raises(RuntimeError, match="audit write failed"):
        client.post(
            "/api/auth/login",
            json={
                "email": "login-rollback@example.com",
                "password": "Password123!",
            },
            headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
        )

    session_rows = (await async_session.execute(
        text("SELECT session_token_hash, revoked_at FROM auth_sessions "
             "ORDER BY created_at"))).all()
    persisted_login_at = await async_session.scalar(
        text("SELECT last_login_at FROM users "
             "WHERE email = 'login-rollback@example.com'"))

    assert session_rows == [(hash_token(original_session_token), None)]
    assert persisted_login_at == original_login_at


@pytest.mark.asyncio
async def test_concurrent_repository_transactions_are_isolated(
    client,
    async_session,
):
    repository = client.app.state.injector.get(AuthRepositoryInterface)

    async def create_committed_user():
        async with repository.transaction():
            await repository.create_user(
                "committed@example.com",
                "committed-password-hash",
            )

    async def create_rolled_back_user():
        async with repository.transaction():
            await repository.create_user(
                "rolled-back@example.com",
                "rolled-back-password-hash",
            )
            raise RuntimeError("rollback this transaction")

    results = await asyncio.gather(
        create_committed_user(),
        create_rolled_back_user(),
        return_exceptions=True,
    )
    emails = (await async_session.execute(
        text("SELECT email FROM users ORDER BY email"))).scalars().all()

    assert results[0] is None
    assert isinstance(results[1], RuntimeError)
    assert emails == ["committed@example.com"]
