from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import text

from app.libraries.password_hasher import hash_password
from app.models.auth_event_type import AuthEventType
from app.models.authorization import UserRole
from app.models.user import User
from tests.integration.timestamp_helpers import unix_timestamp_millis

pytestmark = pytest.mark.integration


def _csrf(client) -> str:
    return client.cookies.get("csrf_token") or client.get("/api/auth/csrf").json()["csrfToken"]


def _register(client, email: str):
    response = client.post(
        "/api/auth/register",
        json={
            "email": email,
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert response.status_code == 201
    return response


def _assert_error_code(response, code: str) -> None:
    assert response.json()["error"]["code"] == code


async def _grant_admin(async_session, user_id: str) -> None:
    async_session.add(UserRole(user_id=UUID(user_id), role_code="admin", assigned_by_user_id=None))
    await async_session.commit()


async def _create_user(async_session, email: str) -> User:
    user = User(email=email, password_hash=hash_password("Password123!"))
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def test_admin_roles_requires_admin_permission(client, async_session):
    _register(client, "regular@example.com")

    response = client.get("/api/admin/roles")

    assert response.status_code == 403
    _assert_error_code(response, "PERMISSION_DENIED")


async def test_admin_roles_returns_roles_and_permission_catalog(client, async_session):
    admin_response = _register(client, "admin@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])

    me_response = client.get("/api/auth/me")
    response = client.get("/api/admin/roles")

    assert me_response.status_code == 200
    assert me_response.json()["roles"] == ["admin"]
    assert me_response.json()["permissions"] == ["admin:access"]
    assert response.status_code == 200
    body = response.json()
    assert {role["code"] for role in body["roles"]} == {"admin"}
    assert {permission["code"] for permission in body["permissions"]} >= {"admin:access"}
    assert body["roles"][0]["permissions"] == ["admin:access"]


async def test_admin_can_replace_user_roles_and_writes_audit(client, async_session):
    admin_response = _register(client, "admin@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    target_user = await _create_user(async_session, "target@example.com")
    original_modified_at = unix_timestamp_millis(datetime(2026, 1, 1, tzinfo=UTC))
    await async_session.execute(
        text("UPDATE users SET modified_at = :modified_at WHERE id = :user_id"),
        {
            "modified_at": original_modified_at,
            "user_id": target_user.id,
        },
    )
    await async_session.commit()

    response = client.put(
        f"/api/admin/users/{target_user.id}/roles",
        json={"roles": ["admin"]},
        headers={"X-CSRF-Token": _csrf(client)},
    )

    assert response.status_code == 200
    assert response.json()["roles"] == ["admin"]
    assert response.json()["permissions"] == ["admin:access"]
    audit_row = (await async_session.execute(
        text("SELECT event_type, detail_json FROM auth_audit_logs "
             "WHERE event_type = :event_type"),
        {"event_type": AuthEventType.ROLE_GRANTED},
    )).one()
    modified_at = await async_session.scalar(
        text("SELECT modified_at FROM users WHERE id = :user_id"),
        {"user_id": target_user.id},
    )
    assert audit_row.event_type == AuthEventType.ROLE_GRANTED
    assert audit_row.detail_json["targetUserId"] == str(target_user.id)
    assert audit_row.detail_json["roleCode"] == "admin"
    assert modified_at != original_modified_at


async def test_admin_replace_user_roles_requires_roles_field(client, async_session):
    admin_response = _register(client, "admin@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    target_user = await _create_user(async_session, "missing-payload@example.com")

    response = client.put(
        f"/api/admin/users/{target_user.id}/roles",
        json={},
        headers={"X-CSRF-Token": _csrf(client)},
    )

    assert response.status_code == 422


async def test_admin_replace_user_roles_requires_csrf_token(client, async_session):
    admin_response = _register(client, "admin@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    target_user = await _create_user(async_session, "missing-csrf@example.com")

    response = client.put(
        f"/api/admin/users/{target_user.id}/roles",
        json={"roles": ["admin"]},
    )

    assert response.status_code == 403
    _assert_error_code(response, "CSRF_VALIDATION_FAILED")


async def test_admin_can_replace_inactive_user_roles(client, async_session):
    admin_response = _register(client, "admin@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    target_user = await _create_user(async_session, "inactive@example.com")
    target_record = await async_session.get(User, target_user.id)
    target_record.is_active = False
    await async_session.commit()

    response = client.put(
        f"/api/admin/users/{target_user.id}/roles",
        json={"roles": ["admin"]},
        headers={"X-CSRF-Token": _csrf(client)},
    )

    assert response.status_code == 200
    assert response.json()["roles"] == ["admin"]


async def test_admin_user_roles_returns_404_for_deleted_user(client, async_session):
    admin_response = _register(client, "admin@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    target_user = await _create_user(async_session, "deleted@example.com")
    target_user.deleted_at = datetime.now(UTC)
    await async_session.commit()

    response = client.get(f"/api/admin/users/{target_user.id}/roles")

    assert response.status_code == 404
    _assert_error_code(response, "USER_NOT_FOUND")
