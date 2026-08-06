import asyncio
import os
from http.cookies import SimpleCookie

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.bootstrap.create_app import create_app
from app.config.auth import AuthSettings
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.libraries.password_hasher import hash_password
from app.libraries.session_tokens import hash_token
from app.models.auth_event_type import AuthEventType
from app.models.user import User

pytestmark = pytest.mark.integration


def assert_error_code(response, code: str) -> None:
    assert response.json()["error"]["code"] == code


def _csrf(client) -> str:
    return client.cookies.get("csrf_token") or client.get("/api/auth/csrf").json()["csrfToken"]


def _register(client, email: str, password: str = "Password123!"):
    csrf_token = _csrf(client)
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": password,
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 201
    return response


def _login(client, email: str, password: str = "Password123!"):
    csrf_token = _csrf(client)
    response = client.post(
        "/api/auth/login",
        json={
            "email": email,
            "password": password,
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert response.status_code == 200
    return response


def _delete_account(
    client,
    confirm_email: str,
    password: str | None = "Password123!",
    csrf_token: str | None = None,
):
    body = {"confirmEmail": confirm_email}
    if password is not None:
        body["password"] = password
    return client.request(
        "DELETE",
        "/api/auth/me",
        json=body,
        headers={"X-CSRF-Token": csrf_token or _csrf(client)},
    )


def _restore_auth_cookies(client, session_token: str, csrf_token: str) -> None:
    client.cookies.set("session_token", session_token, domain="testserver.local", path="/")
    client.cookies.set("csrf_token", csrf_token, domain="testserver.local", path="/")


def test_auth_cookie_security_uses_startup_settings(monkeypatch):
    test_database_url = os.environ["TEST_DATABASE_URL"]
    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    app = create_app()

    with TestClient(app) as client:
        startup_settings = client.app.state.injector.get(AuthSettings)
        assert startup_settings.AUTH_COOKIE_SECURE is False
        monkeypatch.setenv("AUTH_COOKIE_SECURE", "true")

        response = client.get("/api/auth/csrf")

        csrf_cookie = SimpleCookie(response.headers["set-cookie"])
        assert csrf_cookie["csrf_token"]["secure"] == ""
        assert client.app.state.injector.get(AuthSettings) is startup_settings


def test_get_me_returns_401_without_session(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.headers["Cache-Control"] == "no-store"
    assert_error_code(response, "UNAUTHORIZED")


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

    audit_count = await async_session.scalar(text("SELECT count(*) FROM auth_audit_logs"))

    assert audit_count == 0


def test_get_csrf_is_idempotent_when_cookie_exists(client):
    first_response = client.get("/api/auth/csrf")
    second_response = client.get("/api/auth/csrf")

    assert second_response.json()["csrfToken"] == first_response.json()["csrfToken"]
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
    assert_error_code(duplicate_response, "EMAIL_ALREADY_REGISTERED")


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
    assert_error_code(response, "INVALID_CREDENTIALS")


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
    assert_error_code(response, "INVALID_CREDENTIALS")


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
    assert_error_code(old_session_response, "UNAUTHORIZED")


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
    assert_error_code(me_response, "UNAUTHORIZED")


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
    assert_error_code(response, "CSRF_VALIDATION_FAILED")


@pytest.mark.asyncio
async def test_delete_me_deletes_user_revokes_all_sessions_and_clears_cookies(
    client,
    async_session,
):
    client.get("/api/auth/csrf")
    _register(client, "delete-me@example.com")
    first_session_token = client.cookies.get("session_token")
    first_csrf_token = client.cookies.get("csrf_token")
    assert first_session_token
    assert first_csrf_token

    client.cookies.clear()
    client.get("/api/auth/csrf")
    _login(client, "delete-me@example.com")
    second_session_token = client.cookies.get("session_token")
    second_csrf_token = client.cookies.get("csrf_token")
    assert second_session_token
    assert second_csrf_token
    assert second_session_token != first_session_token

    client.cookies.clear()
    _restore_auth_cookies(client, first_session_token, first_csrf_token)
    assert client.get("/api/auth/me").status_code == 200

    delete_response = _delete_account(
        client,
        "delete-me@example.com",
        csrf_token=first_csrf_token,
    )

    assert delete_response.status_code == 204
    set_cookie_headers = delete_response.headers.get_list("set-cookie")
    assert any("session_token=" in header and "Max-Age=0" in header
               for header in set_cookie_headers)
    assert any("csrf_token=" in header and "Max-Age=0" in header for header in set_cookie_headers)
    assert client.get("/api/auth/me").status_code == 401

    _restore_auth_cookies(client, second_session_token, second_csrf_token)
    assert client.get("/api/auth/me").status_code == 401

    user_row = (await async_session.execute(
        text("SELECT id, deleted_at FROM users WHERE email = :email"),
        {"email": "delete-me@example.com"},
    )).one()
    session_rows = (await async_session.execute(
        text("SELECT session_token_hash, revoked_at FROM auth_sessions WHERE user_id = :user_id"),
        {"user_id": user_row.id},
    )).all()
    audit_count = await async_session.scalar(
        text("SELECT count(*) FROM auth_audit_logs "
             "WHERE user_id = :user_id AND event_type = :event_type"),
        {
            "user_id": user_row.id,
            "event_type": AuthEventType.USER_MARKED_DELETED,
        },
    )

    assert user_row.deleted_at is not None
    assert session_rows
    assert all(row.revoked_at is not None for row in session_rows)
    revoked_by_hash = {row.session_token_hash: row.revoked_at for row in session_rows}
    assert revoked_by_hash[hash_token(first_session_token)] is not None
    assert revoked_by_hash[hash_token(second_session_token)] is not None
    assert audit_count == 1


@pytest.mark.asyncio
async def test_delete_me_requires_valid_csrf_and_keeps_user_active(client, async_session):
    _register(client, "delete-csrf@example.com")

    missing_header_response = client.request(
        "DELETE",
        "/api/auth/me",
        json={
            "confirmEmail": "delete-csrf@example.com",
            "password": "Password123!",
        },
    )
    wrong_session_csrf_response = client.request(
        "DELETE",
        "/api/auth/me",
        json={
            "confirmEmail": "delete-csrf@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": "attacker-token"},
        cookies={
            "session_token": client.cookies.get("session_token"),
            "csrf_token": "attacker-token",
        },
    )
    deleted_at = await async_session.scalar(
        text("SELECT deleted_at FROM users WHERE email = :email"),
        {"email": "delete-csrf@example.com"},
    )

    assert missing_header_response.status_code == 403
    assert_error_code(missing_header_response, "CSRF_VALIDATION_FAILED")
    assert wrong_session_csrf_response.status_code == 403
    assert_error_code(wrong_session_csrf_response, "CSRF_VALIDATION_FAILED")
    assert deleted_at is None


@pytest.mark.asyncio
async def test_delete_me_rejects_mismatched_confirm_email_without_deleting(
    client,
    async_session,
):
    _register(client, "delete-mismatch@example.com")

    response = _delete_account(client, "other@example.com")
    deleted_at = await async_session.scalar(
        text("SELECT deleted_at FROM users WHERE email = :email"),
        {"email": "delete-mismatch@example.com"},
    )

    assert response.status_code == 400
    assert_error_code(response, "ACCOUNT_DELETION_CONFIRMATION_MISMATCH")
    assert deleted_at is None
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.asyncio
async def test_delete_me_requires_correct_password_for_password_users(client, async_session):
    _register(client, "delete-password@example.com")

    missing_password_response = _delete_account(
        client,
        "delete-password@example.com",
        password=None,
    )
    empty_password_response = _delete_account(
        client,
        "delete-password@example.com",
        password="",
    )
    wrong_password_response = _delete_account(
        client,
        "delete-password@example.com",
        password="WrongPassword123!",
    )
    deleted_at_after_failures = await async_session.scalar(
        text("SELECT deleted_at FROM users WHERE email = :email"),
        {"email": "delete-password@example.com"},
    )
    success_response = _delete_account(client, "delete-password@example.com")

    assert missing_password_response.status_code == 400
    assert_error_code(missing_password_response, "ACCOUNT_DELETION_REAUTH_REQUIRED")
    assert empty_password_response.status_code == 400
    assert_error_code(empty_password_response, "ACCOUNT_DELETION_REAUTH_REQUIRED")
    assert wrong_password_response.status_code == 400
    assert_error_code(wrong_password_response, "ACCOUNT_DELETION_INVALID_PASSWORD")
    assert deleted_at_after_failures is None
    assert success_response.status_code == 204


@pytest.mark.asyncio
async def test_deleted_email_can_be_registered_again(client, async_session):
    first_response = _register(client, "reuse-delete@example.com")
    first_user_id = first_response.json()["id"]

    delete_response = _delete_account(client, "reuse-delete@example.com")
    assert delete_response.status_code == 204

    client.get("/api/auth/csrf")
    second_response = _register(client, "reuse-delete@example.com")
    second_user_id = second_response.json()["id"]
    old_user_deleted_at = await async_session.scalar(
        text("SELECT deleted_at FROM users WHERE id = :user_id"),
        {"user_id": first_user_id},
    )

    assert second_user_id != first_user_id
    assert client.get("/api/auth/me").json()["id"] == second_user_id
    assert old_user_deleted_at is not None


@pytest.mark.asyncio
async def test_delete_me_deletes_sample_items_owned_by_user(client, async_session):
    register_response = _register(client, "delete-samples@example.com")
    user_id = register_response.json()["id"]
    create_response = client.post(
        "/api/samples",
        json={
            "title": "Owned sample",
            "description": None,
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert create_response.status_code == 201

    delete_response = _delete_account(client, "delete-samples@example.com")
    remaining_count = await async_session.scalar(
        text("SELECT count(*) FROM sample_items WHERE owner_user_id = :user_id"),
        {"user_id": user_id},
    )

    assert delete_response.status_code == 204
    assert remaining_count == 0


@pytest.mark.asyncio
async def test_delete_me_records_success_audit_with_current_session(client, async_session):
    register_response = _register(client, "delete-audit@example.com")
    user_id = register_response.json()["id"]
    session_token = client.cookies.get("session_token")
    assert session_token

    delete_response = _delete_account(client, "delete-audit@example.com")
    audit_row = (await async_session.execute(
        text("""
            SELECT audit.session_id
            FROM auth_audit_logs AS audit
            JOIN auth_sessions AS session
              ON audit.session_id = session.id
             AND audit.user_id = session.user_id
            WHERE audit.user_id = :user_id
              AND audit.event_type = :event_type
              AND session.session_token_hash = :session_token_hash
        """),
        {
            "user_id": user_id,
            "event_type": AuthEventType.USER_MARKED_DELETED,
            "session_token_hash": hash_token(session_token),
        },
    )).one_or_none()

    assert delete_response.status_code == 204
    assert audit_row is not None


@pytest.mark.asyncio
async def test_delete_me_records_reauth_failure_audit(client, async_session):
    register_response = _register(client, "delete-reauth-audit@example.com")
    user_id = register_response.json()["id"]
    session_token = client.cookies.get("session_token")
    assert session_token

    response = _delete_account(
        client,
        "delete-reauth-audit@example.com",
        password="WrongPassword123!",
    )
    audit_row = (await async_session.execute(
        text("""
            SELECT audit.session_id, audit.user_agent
            FROM auth_audit_logs AS audit
            JOIN auth_sessions AS session
              ON audit.session_id = session.id
             AND audit.user_id = session.user_id
            WHERE audit.user_id = :user_id
              AND audit.event_type = :event_type
              AND session.session_token_hash = :session_token_hash
        """),
        {
            "user_id": user_id,
            "event_type": AuthEventType.ACCOUNT_DELETION_REAUTH_FAILED,
            "session_token_hash": hash_token(session_token),
        },
    )).one_or_none()

    assert response.status_code == 400
    assert_error_code(response, "ACCOUNT_DELETION_INVALID_PASSWORD")
    assert audit_row is not None
    assert audit_row.user_agent == "testclient"


@pytest.mark.asyncio
async def test_delete_me_second_submit_with_old_cookies_is_unauthorized_and_idempotent(
    client,
    async_session,
):
    register_response = _register(client, "delete-twice@example.com")
    user_id = register_response.json()["id"]
    session_token = client.cookies.get("session_token")
    csrf_token = client.cookies.get("csrf_token")
    assert session_token
    assert csrf_token

    first_response = _delete_account(client, "delete-twice@example.com", csrf_token=csrf_token)
    _restore_auth_cookies(client, session_token, csrf_token)
    second_response = _delete_account(client, "delete-twice@example.com", csrf_token=csrf_token)
    audit_count = await async_session.scalar(
        text("SELECT count(*) FROM auth_audit_logs "
             "WHERE user_id = :user_id AND event_type = :event_type"),
        {
            "user_id": user_id,
            "event_type": AuthEventType.USER_MARKED_DELETED,
        },
    )

    assert first_response.status_code == 204
    assert second_response.status_code == 401
    assert_error_code(second_response, "UNAUTHORIZED")
    assert audit_count == 1


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
    assert_error_code(response, "CSRF_VALIDATION_FAILED")


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
    assert_error_code(missing_header_response, "CSRF_VALIDATION_FAILED")
    assert missing_cookie_response.status_code == 403
    assert_error_code(missing_cookie_response, "CSRF_VALIDATION_FAILED")


def test_register_rate_limit_returns_429(client):
    for _ in range(6):
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
    assert blocked_response.headers["Retry-After"] == "900"
    assert_error_code(blocked_response, "REGISTER_RATE_LIMITED")


def test_register_and_login_share_rate_limit_bucket(client):
    for _ in range(6):
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
    assert blocked_response.headers["Retry-After"] == "900"
    assert_error_code(blocked_response, "LOGIN_RATE_LIMITED")


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
    assert blocked_response.headers["Retry-After"] == "900"
    assert_error_code(blocked_response, "LOGIN_RATE_LIMITED")


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
        {"session_token_hash": hash_token(client.cookies.get("session_token"))},
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
    assert_error_code(response, "UNAUTHORIZED")
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
        {"session_token_hash": hash_token(client.cookies.get("session_token"))},
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
    assert_error_code(response, "UNAUTHORIZED")
    assert rejected_audit_count == 1


@pytest.mark.asyncio
async def test_me_rejected_session_replay_is_bounded_with_replay_count(client, async_session):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "bounded-me-replay@example.com",
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
        {"session_token_hash": hash_token(client.cookies.get("session_token"))},
    )
    await async_session.commit()

    responses = [client.get("/api/auth/me") for _ in range(3)]
    audit_summary = (await async_session.execute(
        text("""
            SELECT count(*) AS row_count,
                   max((detail_json->>'replay_count')::int) AS replay_count
            FROM auth_audit_logs AS audit
            JOIN auth_sessions AS session
              ON audit.session_id = session.id
             AND audit.user_id = session.user_id
            WHERE audit.event_type = 'session_rejected'
        """))).one()

    assert [response.status_code for response in responses] == [401, 401, 401]
    assert audit_summary.row_count == 1
    assert audit_summary.replay_count == 3


@pytest.mark.asyncio
async def test_csrf_unknown_path_rejected_session_replay_is_bounded(client, async_session):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={
            "email": "bounded-csrf-replay@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    session_token = client.cookies.get("session_token")
    csrf_token = client.cookies.get("csrf_token")
    await async_session.execute(
        text("""
            UPDATE auth_sessions
            SET revoked_at = now()
            WHERE session_token_hash = :session_token_hash
        """),
        {"session_token_hash": hash_token(session_token)},
    )
    await async_session.commit()

    responses = [
        client.post("/api/unknown", headers={"X-CSRF-Token": csrf_token}) for _ in range(3)
    ]
    audit_summary = (await async_session.execute(
        text("""
            SELECT count(*) AS row_count,
                   max((detail_json->>'replay_count')::int) AS replay_count
            FROM auth_audit_logs AS audit
            JOIN auth_sessions AS session
              ON audit.session_id = session.id
             AND audit.user_id = session.user_id
            WHERE audit.event_type = 'session_rejected'
        """))).one()

    assert [response.status_code for response in responses] == [404, 404, 404]
    assert audit_summary.row_count == 1
    assert audit_summary.replay_count == 3


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
        {"session_token_hash": hash_token(client.cookies.get("session_token"))},
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
        text("SELECT count(*) FROM users WHERE email = 'rollback@example.com'"))
    session_count = await async_session.scalar(text("SELECT count(*) FROM auth_sessions"))

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
    unit_of_work = client.app.state.injector.get(UnitOfWorkInterface)

    async def create_committed_user():
        async with unit_of_work.transaction():
            await repository.create_user(
                "committed@example.com",
                "committed-password-hash",
            )

    async def create_rolled_back_user():
        async with unit_of_work.transaction():
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
    emails = (await async_session.execute(text("SELECT email FROM users ORDER BY email")
                                          )).scalars().all()

    assert results[0] is None
    assert isinstance(results[1], RuntimeError)
    assert emails == ["committed@example.com"]
