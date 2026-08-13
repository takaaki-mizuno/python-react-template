from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from sqlalchemy import text

from app.libraries.password_hasher import hash_password
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.authorization import UserRole
from app.models.user import User
from tests.integration.timestamp_helpers import unix_timestamp_millis

pytestmark = pytest.mark.integration


def _csrf(client) -> str:
    return client.cookies.get("csrf_token") or client.get("/api/auth/csrf").json()["csrf_token"]


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
    assert response.json()["code"] == code


async def _grant_admin(async_session, user_id: str) -> None:
    async_session.add(UserRole(user_id=UUID(user_id), role_code="admin", assigned_by_user_id=None))
    await async_session.commit()


async def _create_user(async_session, email: str, *, is_active: bool = True) -> User:
    user = User(email=email, password_hash=hash_password("Password123!"), is_active=is_active)
    async_session.add(user)
    await async_session.commit()
    await async_session.refresh(user)
    return user


async def test_admin_users_requires_admin_permission(client, async_session) -> None:
    _register(client, "regular-admin-crud@example.com")

    response = client.get("/api/admin/users")

    assert response.status_code == 403
    _assert_error_code(response, "permission_denied")


async def test_admin_users_create_list_get_patch_and_delete(client, async_session) -> None:
    admin_response = _register(client, "admin-crud@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    await _create_user(async_session, "inactive-admin-crud@example.com", is_active=False)

    create_response = client.post(
        "/api/admin/users",
        json={
            "email": "Created-Admin-CRUD@Example.com",
            "password": "Password@123!",
            "is_active": True,
            "roles": ["admin"],
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["email"] == "created-admin-crud@example.com"
    assert created["roles"] == ["admin"]
    assert created["permissions"] == ["admin:access"]

    list_response = client.get(
        "/api/admin/users",
        params={
            "query": "created-admin-crud",
            "role": "admin",
            "is_active": "true",
            "offset": "0",
            "limit": "20",
        },
    )
    assert list_response.status_code == 200
    list_body = list_response.json()
    assert list_body["count"] == 1
    assert any(item["id"] == created["id"] for item in list_body["data"])
    assert "permissions" not in list_body["data"][0]

    get_response = client.get(f"/api/admin/users/{created['id']}")
    assert get_response.status_code == 200
    assert get_response.json()["permissions"] == ["admin:access"]

    patch_response = client.patch(
        f"/api/admin/users/{created['id']}",
        json={
            "email": "patched-admin-crud@example.com",
            "is_active": False,
            "roles": [],
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert patch_response.status_code == 200
    assert patch_response.json()["email"] == "patched-admin-crud@example.com"
    assert patch_response.json()["is_active"] is False
    assert patch_response.json()["roles"] == []

    delete_response = client.delete(
        f"/api/admin/users/{created['id']}",
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert delete_response.status_code == 204
    missing_response = client.get(f"/api/admin/users/{created['id']}")
    assert missing_response.status_code == 404
    _assert_error_code(missing_response, "user_not_found")

    deleted_at = (await async_session.execute(
        text("SELECT deleted_at FROM users WHERE id = :user_id"),
        {"user_id": created["id"]},
    )).scalar_one()
    remaining_roles = (await async_session.execute(
        text("SELECT role_code FROM user_roles WHERE user_id = :user_id"),
        {"user_id": created["id"]},
    )).scalars().all()
    assert deleted_at is not None
    assert remaining_roles == []


async def test_admin_users_list_paginates_case_insensitive_search_and_excludes_deleted(
        client, async_session) -> None:
    admin_response = _register(client, "admin-crud-list-owner@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    kept_users = [
        await _create_user(async_session, f"page-filter-{index}@example.com") for index in range(3)
    ]
    deleted_user = await _create_user(async_session, "page-filter-deleted@example.com")
    deleted_at = unix_timestamp_millis(datetime.now(UTC))
    await async_session.execute(
        text("UPDATE users SET deleted_at = :deleted_at WHERE id = :user_id"),
        {
            "deleted_at": deleted_at,
            "user_id": deleted_user.id,
        },
    )
    await async_session.commit()

    first_page_response = client.get(
        "/api/admin/users",
        params={
            "query": "PAGE-FILTER",
            "offset": "0",
            "limit": "1",
        },
    )
    second_page_response = client.get(
        "/api/admin/users",
        params={
            "query": "PAGE-FILTER",
            "offset": "1",
            "limit": "1",
        },
    )

    assert first_page_response.status_code == 200
    assert second_page_response.status_code == 200
    first_page = first_page_response.json()
    second_page = second_page_response.json()
    assert first_page["count"] == 3
    assert second_page["count"] == 3
    assert first_page["offset"] == 0
    assert second_page["offset"] == 1
    assert first_page["limit"] == 1
    assert second_page["limit"] == 1
    assert len(first_page["data"]) == 1
    assert len(second_page["data"]) == 1
    kept_user_ids = {str(user.id) for user in kept_users}
    first_page_ids = {item["id"] for item in first_page["data"]}
    second_page_ids = {item["id"] for item in second_page["data"]}
    assert first_page_ids <= kept_user_ids
    assert second_page_ids <= kept_user_ids
    assert first_page_ids.isdisjoint(second_page_ids)
    assert str(deleted_user.id) not in first_page_ids | second_page_ids


async def test_admin_user_create_duplicate_email_returns_409(client, async_session) -> None:
    admin_response = _register(client, "admin-crud-duplicate-owner@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    await _create_user(async_session, "duplicate-admin-crud@example.com")

    response = client.post(
        "/api/admin/users",
        json={
            "email": "Duplicate-Admin-CRUD@Example.com",
            "password": "Password@123!",
            "roles": [],
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )

    assert response.status_code == 409
    _assert_error_code(response, "email_already_registered")


async def test_admin_user_patch_password_revokes_target_sessions(client, async_session) -> None:
    admin_response = _register(client, "admin-crud-revoke-owner@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    target = await _create_user(async_session, "revoke-admin-crud@example.com")
    session = AuthSession(
        user_id=target.id,
        session_token_hash="target-session-hash",
        csrf_token_hash="target-csrf-hash",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    async_session.add(session)
    await async_session.commit()

    response = client.patch(
        f"/api/admin/users/{target.id}",
        json={"password": "Password@456!"},
        headers={"X-CSRF-Token": _csrf(client)},
    )

    revoked_at = (await async_session.execute(
        text("SELECT revoked_at FROM auth_sessions WHERE id = :session_id"),
        {"session_id": session.id},
    )).scalar_one()
    assert response.status_code == 200
    assert revoked_at is not None


async def test_admin_user_mutations_record_admin_and_deletion_audit_events(client,
                                                                           async_session) -> None:
    admin_response = _register(client, "admin-crud-audit-owner@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])

    create_response = client.post(
        "/api/admin/users",
        json={
            "email": "audit-admin-crud@example.com",
            "password": "Password@123!",
            "roles": [],
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert create_response.status_code == 201
    target_id = create_response.json()["id"]

    patch_response = client.patch(
        f"/api/admin/users/{target_id}",
        json={"email": "audit-updated-admin-crud@example.com"},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert patch_response.status_code == 200

    delete_response = client.delete(
        f"/api/admin/users/{target_id}",
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert delete_response.status_code == 204

    event_types = (await async_session.execute(text("SELECT event_type FROM auth_audit_logs")
                                               )).scalars().all()
    assert AuthEventType.USER_CREATED_BY_ADMIN in event_types
    assert AuthEventType.USER_UPDATED_BY_ADMIN in event_types
    assert AuthEventType.USER_MARKED_DELETED in event_types
    assert AuthEventType.USER_DELETED_BY_ADMIN in event_types


async def test_admin_user_create_requires_csrf(client, async_session) -> None:
    admin_response = _register(client, "admin-crud-csrf@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])

    response = client.post(
        "/api/admin/users",
        json={
            "email": "no-csrf-admin-crud@example.com",
            "password": "Password@123!",
            "roles": [],
        },
    )

    assert response.status_code == 403
    _assert_error_code(response, "csrf_validation_failed")


async def test_admin_user_patch_roles_is_atomic_for_unknown_role(client, async_session) -> None:
    admin_response = _register(client, "admin-crud-atomic@example.com")
    await _grant_admin(async_session, admin_response.json()["id"])
    target = await _create_user(async_session, "atomic-admin-crud@example.com")

    response = client.patch(
        f"/api/admin/users/{target.id}",
        json={
            "email": "should-not-persist@example.com",
            "roles": ["missing"],
        },
        headers={"X-CSRF-Token": _csrf(client)},
    )

    refreshed_email = (await async_session.execute(
        text("SELECT email FROM users WHERE id = :user_id"),
        {"user_id": target.id},
    )).scalar_one()
    assert response.status_code == 422
    _assert_error_code(response, "role_not_found")
    assert refreshed_email == "atomic-admin-crud@example.com"
