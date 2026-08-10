from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request

from app.bootstrap.dependencies import inject
from app.bootstrap.error_handlers import api_error
from app.config.auth import AuthSettings
from app.config.authorization import permissions_for_role_codes
from app.controllers.auth_dependencies import (get_auth_settings, get_client_ip, get_user_agent,
                                               require_permission)
from app.interfaces.usecases.authorization_usecase_interface import AuthorizationUsecaseInterface
from app.models.auth_context import AuthenticatedSessionContext
from app.models.authorization import (PermissionDefinition, RoleWithPermissions, UserAuthorization,
                                      UserRoleReplacementResult)
from app.models.authorization_errors import AuthorizationUserNotFoundError, RoleNotFoundError
from app.models.authorization_schemas import (PermissionResponse, RoleListResponse, RoleResponse,
                                              UserRoleListResponse, UserRoleReplaceRequest,
                                              UserRoleReplaceResponse)
from app.models.error import ErrorResponse

ErrorResponses = dict[int | str, dict[str, Any]]
ERROR_RESPONSE: dict[str, Any] = {"model": ErrorResponse}
ADMIN_ERROR_RESPONSES: ErrorResponses = {
    401: ERROR_RESPONSE,
    403: ERROR_RESPONSE,
    404: ERROR_RESPONSE,
    422: ERROR_RESPONSE,
}

get_authorization_usecase = inject(AuthorizationUsecaseInterface)
require_admin_access = require_permission("admin:access")

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/roles", response_model=RoleListResponse, responses=ADMIN_ERROR_RESPONSES)
async def list_roles(
    _auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
    usecase: AuthorizationUsecaseInterface = Depends(get_authorization_usecase),
) -> RoleListResponse:
    roles = await usecase.list_roles()
    permissions = await usecase.list_permissions()
    return RoleListResponse(
        roles=[_role_response(role) for role in roles],
        permissions=[_permission_response(permission) for permission in permissions],
    )


@router.get(
    "/users/{user_id}/roles",
    response_model=UserRoleListResponse,
    responses=ADMIN_ERROR_RESPONSES,
)
async def get_user_roles(
    user_id: UUID,
    _auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
    usecase: AuthorizationUsecaseInterface = Depends(get_authorization_usecase),
) -> UserRoleListResponse:
    try:
        authorization = await usecase.get_user_authorization(user_id)
    except AuthorizationUserNotFoundError as error:
        raise _user_not_found_error() from error
    return _user_role_list_response(authorization)


@router.put(
    "/users/{user_id}/roles",
    response_model=UserRoleReplaceResponse,
    responses=ADMIN_ERROR_RESPONSES,
)
async def replace_user_roles(
    user_id: UUID,
    payload: UserRoleReplaceRequest,
    request: Request,
    auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
    auth_settings: AuthSettings = Depends(get_auth_settings),
    usecase: AuthorizationUsecaseInterface = Depends(get_authorization_usecase),
) -> UserRoleReplaceResponse:
    try:
        result = await usecase.replace_user_roles(
            auth_context,
            user_id,
            tuple(payload.roles),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except AuthorizationUserNotFoundError as error:
        raise _user_not_found_error() from error
    except RoleNotFoundError as error:
        raise api_error(
            422,
            "ROLE_NOT_FOUND",
            "Role not found",
            details=[{
                "roleCodes": sorted(error.role_codes)
            }],
        ) from error
    return _user_role_replace_response(result)


def _role_response(role: RoleWithPermissions) -> RoleResponse:
    return RoleResponse(
        code=role.code,
        display_name=role.display_name,
        description=role.description,
        permissions=list(role.permissions),
    )


def _permission_response(permission: PermissionDefinition) -> PermissionResponse:
    return PermissionResponse(
        code=permission.code,
        display_name=permission.display_name,
        description=permission.description,
    )


def _user_role_list_response(authorization: UserAuthorization) -> UserRoleListResponse:
    return UserRoleListResponse(
        user_id=authorization.user_id,
        roles=sorted(authorization.roles),
        permissions=sorted(authorization.permissions),
    )


def _user_role_replace_response(result: UserRoleReplacementResult) -> UserRoleReplaceResponse:
    return UserRoleReplaceResponse(
        user_id=result.user_id,
        roles=list(result.current_role_codes),
        permissions=sorted(permissions_for_role_codes(result.current_role_codes)),
        granted_roles=list(result.granted_role_codes),
        revoked_roles=list(result.revoked_role_codes),
    )


def _user_not_found_error() -> HTTPException:
    return api_error(404, "USER_NOT_FOUND", "User not found")
