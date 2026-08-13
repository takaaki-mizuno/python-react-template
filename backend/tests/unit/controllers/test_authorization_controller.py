from datetime import timedelta
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.config.auth import AuthSettings
from app.controllers.authorization_controller import get_user_roles, list_roles, replace_user_roles
from app.libraries.clock import utcnow
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_session import AuthSession
from app.models.authorization import (PermissionDefinition, RoleWithPermissions, UserAuthorization,
                                      UserRoleReplacementResult)
from app.models.authorization_errors import AuthorizationUserNotFoundError, RoleNotFoundError
from app.models.authorization_schemas import UserRoleReplaceRequest
from app.models.user import User


class AuthorizationUsecaseStub:

    def __init__(self) -> None:
        self.target_user_id = uuid4()
        self.replace_calls = []

    async def list_roles(self):
        return [
            RoleWithPermissions(
                code="admin",
                display_name="Admin",
                description="Administrators",
                permissions=("admin:access", ),
            )
        ]

    async def list_permissions(self):
        return [
            PermissionDefinition(
                code="admin:access",
                display_name="Admin access",
                description="Access admin",
            )
        ]

    async def get_user_authorization(self, user_id: UUID):
        if user_id != self.target_user_id:
            raise AuthorizationUserNotFoundError(user_id)
        return UserAuthorization(
            user_id=user_id,
            roles=frozenset({"admin"}),
            permissions=frozenset({"admin:access"}),
        )

    async def replace_user_roles(
        self,
        actor_context,
        target_user_id,
        role_codes,
        ip_address,
        user_agent,
    ):
        self.replace_calls.append(
            (actor_context, target_user_id, role_codes, ip_address, user_agent))
        if role_codes == ("missing", ):
            raise RoleNotFoundError(frozenset({"missing"}))
        return UserRoleReplacementResult(
            user_id=target_user_id,
            granted_role_codes=("admin", ),
            revoked_role_codes=("viewer", ),
            current_role_codes=("admin", ),
        )


@pytest.mark.asyncio
async def test_list_roles_includes_permission_catalog() -> None:
    response = await list_roles(_auth_context=_context(), usecase=AuthorizationUsecaseStub())

    assert [role.code for role in response.data] == ["admin"]
    assert response.data[0].permissions == ["admin:access"]
    assert [permission.code for permission in response.permissions] == ["admin:access"]


def test_user_role_replace_request_requires_roles_field() -> None:
    with pytest.raises(ValidationError):
        UserRoleReplaceRequest.model_validate({})


@pytest.mark.asyncio
async def test_get_user_roles_maps_missing_user_to_404() -> None:
    with pytest.raises(Exception) as exc_info:
        await get_user_roles(
            uuid4(),
            _auth_context=_context(),
            usecase=AuthorizationUsecaseStub(),
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail["code"] == "user_not_found"


@pytest.mark.asyncio
async def test_replace_user_roles_maps_missing_role_to_422() -> None:
    with pytest.raises(Exception) as exc_info:
        await replace_user_roles(
            uuid4(),
            UserRoleReplaceRequest(roles=["missing"]),
            _request(),
            auth_context=_context(),
            auth_settings=AuthSettings(AUTH_COOKIE_SECURE=False),
            usecase=AuthorizationUsecaseStub(),
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "role_not_found"
    assert exc_info.value.detail["role_codes"] == ["missing"]


def _request() -> Request:
    return Request({
        "type": "http",
        "method": "PUT",
        "path": "/api/admin/users/test/roles",
        "headers": [(b"user-agent", b"pytest")],
        "client": ("127.0.0.1", 12345),
    })


def _context() -> AuthenticatedSessionContext:
    now = utcnow()
    user = User(id=uuid4(), email="admin@example.com", password_hash="hash")
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
