from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from starlette.requests import Request

from app.config.auth import AuthSettings
from app.controllers.admin_user_controller import (create_admin_user, delete_admin_user,
                                                   get_admin_user, list_admin_users,
                                                   update_admin_user)
from app.models.admin_pagination import AdminOffsetPageResult
from app.models.admin_user import AdminUserDetail, AdminUserListQuery, AdminUserRecord
from app.models.admin_user_schemas import AdminUserCreateRequest, AdminUserUpdateRequest
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_errors import EmailAlreadyRegisteredError, UserNotFoundError, WeakPasswordError
from app.models.auth_session import AuthSession
from app.models.authorization_errors import RoleNotFoundError
from app.models.user import User


class AdminUserUsecaseStub:

    def __init__(self) -> None:
        self.user = _user()
        self.list_calls = []
        self.create_calls = []
        self.update_calls = []
        self.delete_calls = []

    async def list_users(self, query, offset, limit):
        self.list_calls.append((query, offset, limit))
        return AdminOffsetPageResult(
            items=[AdminUserRecord(user=self.user, roles=("admin", ))],
            total=1,
            offset=offset,
            limit=limit,
        )

    async def create_user(self, actor_context, email, password, is_active, roles, ip_address,
                          user_agent):
        self.create_calls.append(
            (actor_context, email, password, is_active, roles, ip_address, user_agent))
        if email == "duplicate@example.com":
            raise EmailAlreadyRegisteredError
        if password == "weak-password":
            raise WeakPasswordError("weak")
        if roles == ("missing", ):
            raise RoleNotFoundError(frozenset({"missing"}))
        return AdminUserDetail(user=self.user, roles=roles, permissions=("admin:access", ))

    async def get_user(self, user_id):
        if user_id != self.user.id:
            raise UserNotFoundError(user_id)
        return AdminUserDetail(user=self.user, roles=("admin", ), permissions=("admin:access", ))

    async def update_user(self, actor_context, user_id, changes, ip_address, user_agent):
        self.update_calls.append((actor_context, user_id, changes, ip_address, user_agent))
        if user_id != self.user.id:
            raise UserNotFoundError(user_id)
        return AdminUserDetail(user=self.user, roles=("admin", ), permissions=("admin:access", ))

    async def delete_user(self, actor_context, user_id, ip_address, user_agent):
        self.delete_calls.append((actor_context, user_id, ip_address, user_agent))
        if user_id != self.user.id:
            raise UserNotFoundError(user_id)


@pytest.mark.asyncio
async def test_list_admin_users_passes_filters_and_returns_page() -> None:
    usecase = AdminUserUsecaseStub()

    response = await list_admin_users(
        _request("GET"),
        offset=10,
        limit=20,
        search="  Admin  ",
        role="admin",
        is_active=True,
        _auth_context=_context(),
        usecase=usecase,
    )

    assert usecase.list_calls == [(AdminUserListQuery("Admin", True, "admin"), 10, 20)]
    assert response.total == 1
    assert response.items[0].roles == ["admin"]


@pytest.mark.asyncio
async def test_list_admin_users_rejects_search_over_helper_limit() -> None:
    with pytest.raises(Exception) as error:
        await list_admin_users(
            _request("GET"),
            offset=0,
            limit=20,
            search="x" * 321,
            role=None,
            is_active=None,
            _auth_context=_context(),
            usecase=AdminUserUsecaseStub(),
        )

    assert error.value.status_code == 422
    assert error.value.detail["code"] == "INVALID_ADMIN_USER_QUERY"


@pytest.mark.asyncio
async def test_create_admin_user_maps_duplicate_email_to_409_and_role_to_422() -> None:
    with pytest.raises(Exception) as duplicate:
        await create_admin_user(
            AdminUserCreateRequest(
                email="duplicate@example.com",
                password="Password@123!",
                roles=[],
            ),
            _request("POST"),
            auth_context=_context(),
            auth_settings=AuthSettings(AUTH_COOKIE_SECURE=False),
            usecase=AdminUserUsecaseStub(),
        )
    assert duplicate.value.status_code == 409
    assert duplicate.value.detail["code"] == "EMAIL_ALREADY_REGISTERED"

    with pytest.raises(Exception) as missing_role:
        await create_admin_user(
            AdminUserCreateRequest(
                email="new@example.com",
                password="Password@123!",
                roles=["missing"],
            ),
            _request("POST"),
            auth_context=_context(),
            auth_settings=AuthSettings(AUTH_COOKIE_SECURE=False),
            usecase=AdminUserUsecaseStub(),
        )
    assert missing_role.value.status_code == 422
    assert missing_role.value.detail["code"] == "ROLE_NOT_FOUND"


@pytest.mark.asyncio
async def test_update_admin_user_builds_changes_from_fields_set() -> None:
    usecase = AdminUserUsecaseStub()

    await update_admin_user(
        usecase.user.id,
        AdminUserUpdateRequest.model_validate({
            "email": "changed@example.com",
            "roles": ["admin"]
        }),
        _request("PATCH"),
        auth_context=_context(),
        auth_settings=AuthSettings(AUTH_COOKIE_SECURE=False),
        usecase=usecase,
    )

    changes = usecase.update_calls[0][2]
    assert changes.email == "changed@example.com"
    assert changes.roles == ("admin", )
    assert changes.fields_set == frozenset({"email", "roles"})


@pytest.mark.asyncio
async def test_get_and_delete_map_missing_user_to_404() -> None:
    usecase = AdminUserUsecaseStub()

    with pytest.raises(Exception) as get_error:
        await get_admin_user(uuid4(), _auth_context=_context(), usecase=usecase)
    assert get_error.value.status_code == 404
    assert get_error.value.detail["code"] == "USER_NOT_FOUND"

    with pytest.raises(Exception) as delete_error:
        await delete_admin_user(
            uuid4(),
            _request("DELETE"),
            auth_context=_context(),
            auth_settings=AuthSettings(AUTH_COOKIE_SECURE=False),
            usecase=usecase,
        )
    assert delete_error.value.status_code == 404
    assert delete_error.value.detail["code"] == "USER_NOT_FOUND"


def _request(method: str) -> Request:
    return Request({
        "type": "http",
        "method": method,
        "path": "/api/admin/users",
        "headers": [(b"user-agent", b"pytest")],
        "client": ("127.0.0.1", 12345),
    })


def _context() -> AuthenticatedSessionContext:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    user = _user(UUID("00000000-0000-0000-0000-000000000002"))
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset({"admin"}),
        permissions=frozenset({"admin:access"}),
    )


def _user(user_id: UUID | None = None) -> User:
    return User(
        id=user_id or UUID("00000000-0000-0000-0000-000000000001"),
        email="admin@example.com",
        password_hash="hash",
        is_active=True,
        registered_at=datetime(2026, 1, 1, tzinfo=UTC),
        modified_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
