from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response

from app.bootstrap.dependencies import inject
from app.bootstrap.error_handlers import api_error
from app.config.auth import AuthSettings
from app.controllers.auth_dependencies import (get_auth_settings, get_client_ip, get_user_agent,
                                               require_permission)
from app.interfaces.usecases.admin_user_usecase_interface import AdminUserUsecaseInterface
from app.models.admin_query import normalize_admin_search
from app.models.admin_user import AdminUserListQuery, AdminUserUpdateChanges
from app.models.admin_user_schemas import (AdminUserCreateRequest, AdminUserListItemResponse,
                                           AdminUserListResponse, AdminUserResponse,
                                           AdminUserUpdateRequest)
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_errors import EmailAlreadyRegisteredError, UserNotFoundError, WeakPasswordError
from app.models.authorization_errors import RoleNotFoundError
from app.models.error import problem_response_openapi

ProblemResponses = dict[int | str, dict[str, Any]]
ERROR_RESPONSE: dict[str, Any] = problem_response_openapi()
ADMIN_USER_ERROR_RESPONSES: ProblemResponses = {
    401: ERROR_RESPONSE,
    403: ERROR_RESPONSE,
    404: ERROR_RESPONSE,
    409: ERROR_RESPONSE,
    422: ERROR_RESPONSE,
}

get_admin_user_usecase = inject(AdminUserUsecaseInterface)
require_admin_access = require_permission("admin:access")

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=AdminUserListResponse, responses=ADMIN_USER_ERROR_RESPONSES)
async def list_admin_users(
    request: Request,
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    query: str | None = Query(default=None, max_length=320),
    role: str | None = Query(default=None, max_length=64),
    is_active: bool | None = Query(default=None),
    _auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
    usecase: AdminUserUsecaseInterface = Depends(get_admin_user_usecase),
) -> AdminUserListResponse:
    del request
    try:
        result = await usecase.list_users(
            AdminUserListQuery(
                search=normalize_admin_search(query),
                is_active=is_active,
                role=role,
            ),
            offset=offset,
            limit=limit,
        )
    except ValueError as error:
        raise api_error(422, "invalid_admin_user_query", "Invalid admin user query") from error
    except RoleNotFoundError as error:
        raise _role_not_found_error(error) from error
    return AdminUserListResponse(
        data=[AdminUserListItemResponse.from_record(record) for record in result.items],
        count=result.total,
        offset=result.offset,
        limit=result.limit,
    )


@router.post(
    "",
    response_model=AdminUserResponse,
    status_code=201,
    responses=ADMIN_USER_ERROR_RESPONSES,
)
async def create_admin_user(
        payload: AdminUserCreateRequest,
        request: Request,
        response: Response,
        auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AdminUserUsecaseInterface = Depends(get_admin_user_usecase),
) -> AdminUserResponse:
    try:
        detail = await usecase.create_user(
            actor_context=auth_context,
            email=str(payload.email),
            password=payload.password,
            is_active=payload.is_active,
            roles=tuple(payload.roles),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except EmailAlreadyRegisteredError as error:
        raise api_error(409, "email_already_registered", "Email already registered") from error
    except WeakPasswordError as error:
        raise api_error(422, "weak_password", "Password does not meet requirements") from error
    except RoleNotFoundError as error:
        raise _role_not_found_error(error) from error
    response.headers["Location"] = f"/api/admin/users/{detail.user.id}"
    return AdminUserResponse.from_detail(detail)


@router.get("/{user_id}", response_model=AdminUserResponse, responses=ADMIN_USER_ERROR_RESPONSES)
async def get_admin_user(
        user_id: UUID,
        _auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
        usecase: AdminUserUsecaseInterface = Depends(get_admin_user_usecase),
) -> AdminUserResponse:
    try:
        detail = await usecase.get_user(user_id)
    except UserNotFoundError as error:
        raise _user_not_found_error() from error
    return AdminUserResponse.from_detail(detail)


@router.patch("/{user_id}", response_model=AdminUserResponse, responses=ADMIN_USER_ERROR_RESPONSES)
async def update_admin_user(
        user_id: UUID,
        payload: AdminUserUpdateRequest,
        request: Request,
        auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AdminUserUsecaseInterface = Depends(get_admin_user_usecase),
) -> AdminUserResponse:
    changes = AdminUserUpdateChanges(
        email=str(payload.email) if payload.email is not None else None,
        password=payload.password,
        is_active=payload.is_active,
        roles=tuple(payload.roles) if payload.roles is not None else None,
        fields_set=frozenset(payload.model_fields_set),
    )
    try:
        detail = await usecase.update_user(
            actor_context=auth_context,
            user_id=user_id,
            changes=changes,
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except UserNotFoundError as error:
        raise _user_not_found_error() from error
    except EmailAlreadyRegisteredError as error:
        raise api_error(409, "email_already_registered", "Email already registered") from error
    except WeakPasswordError as error:
        raise api_error(422, "weak_password", "Password does not meet requirements") from error
    except RoleNotFoundError as error:
        raise _role_not_found_error(error) from error
    return AdminUserResponse.from_detail(detail)


@router.delete("/{user_id}", status_code=204, responses=ADMIN_USER_ERROR_RESPONSES)
async def delete_admin_user(
        user_id: UUID,
        request: Request,
        auth_context: AuthenticatedSessionContext = Depends(require_admin_access),
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AdminUserUsecaseInterface = Depends(get_admin_user_usecase),
) -> Response:
    try:
        await usecase.delete_user(
            actor_context=auth_context,
            user_id=user_id,
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except UserNotFoundError as error:
        raise _user_not_found_error() from error
    return Response(status_code=204)


def _user_not_found_error() -> HTTPException:
    return api_error(404, "user_not_found", "User not found")


def _role_not_found_error(error: RoleNotFoundError) -> HTTPException:
    return api_error(
        422,
        "role_not_found",
        "Role not found",
        extensions={"role_codes": sorted(error.role_codes)},
    )
