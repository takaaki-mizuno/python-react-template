from typing import Any

from fastapi import APIRouter, Depends, Request, Response

from app.bootstrap.error_handlers import api_error
from app.config.auth import AuthSettings
from app.controllers.auth_dependencies import (get_auth_settings, get_auth_usecase, get_client_ip,
                                               get_user_agent, require_current_session)
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_csrf import SessionCsrfStatus
from app.models.auth_errors import (EmailAlreadyRegisteredError, InvalidCredentialsError,
                                    RateLimitExceededError, WeakPasswordError)
from app.models.auth_schemas import (AuthUserResponse, CsrfTokenResponse, LoginRequest,
                                     RegisterRequest)
from app.models.error import ErrorResponse

router = APIRouter(prefix="/auth", tags=["auth"])

ErrorResponses = dict[int | str, dict[str, Any]]

ME_ERROR_RESPONSES: ErrorResponses = {
    401: {
        "model": ErrorResponse
    },
}
REGISTER_ERROR_RESPONSES: ErrorResponses = {
    403: {
        "model": ErrorResponse
    },
    409: {
        "model": ErrorResponse
    },
    422: {
        "model": ErrorResponse
    },
    429: {
        "model": ErrorResponse
    },
}
LOGIN_ERROR_RESPONSES: ErrorResponses = {
    401: {
        "model": ErrorResponse
    },
    403: {
        "model": ErrorResponse
    },
    422: {
        "model": ErrorResponse
    },
    429: {
        "model": ErrorResponse
    },
}
LOGOUT_ERROR_RESPONSES: ErrorResponses = {
    403: {
        "model": ErrorResponse
    },
}


def is_secure_request(
    request: Request,
    auth_settings: AuthSettings,
) -> bool:
    if auth_settings.AUTH_COOKIE_SECURE is not None:
        return auth_settings.AUTH_COOKIE_SECURE
    return True


def set_session_cookie(
    response: Response,
    session_token: str,
    secure: bool,
    max_age_seconds: int,
) -> None:
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age_seconds,
    )


def set_csrf_cookie(
    response: Response,
    csrf_token: str,
    secure: bool,
    max_age_seconds: int,
) -> None:
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age_seconds,
    )


def clear_session_cookie(response: Response, secure: bool) -> None:
    response.set_cookie(
        key="session_token",
        value="",
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=0,
    )


def clear_csrf_cookie(response: Response, secure: bool) -> None:
    response.set_cookie(
        key="csrf_token",
        value="",
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=0,
    )


@router.get("/csrf", response_model=CsrfTokenResponse)
async def get_csrf(
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> CsrfTokenResponse:
    response.headers["Cache-Control"] = "no-store"
    existing_csrf_token = request.cookies.get("csrf_token")
    if existing_csrf_token:
        session_token = request.cookies.get("session_token")
        if not session_token:
            return CsrfTokenResponse(csrfToken=existing_csrf_token)

        csrf_status = await usecase.validate_session_csrf(
            session_token=session_token,
            csrf_token=existing_csrf_token,
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
        if csrf_status in {
                SessionCsrfStatus.VALID,
                SessionCsrfStatus.NO_SESSION,
        }:
            return CsrfTokenResponse(csrfToken=existing_csrf_token)

    csrf_token = await usecase.issue_csrf_token(
        session_token=request.cookies.get("session_token"), )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=is_secure_request(request, auth_settings),
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return CsrfTokenResponse(csrfToken=csrf_token)


@router.get("/me", response_model=AuthUserResponse, responses=ME_ERROR_RESPONSES)
async def get_me(
    response: Response,
    auth_context: AuthenticatedSessionContext = Depends(require_current_session),
) -> AuthUserResponse:
    response.headers["Cache-Control"] = "no-store"
    return AuthUserResponse(id=auth_context.user.id, email=auth_context.user.email)


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=201,
    responses=REGISTER_ERROR_RESPONSES,
)
async def register(
        payload: RegisterRequest,
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> AuthUserResponse:
    try:
        issued_session = await usecase.register(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except EmailAlreadyRegisteredError as error:
        raise api_error(
            409,
            "EMAIL_ALREADY_REGISTERED",
            "Email already registered",
        ) from error
    except RateLimitExceededError as error:
        raise api_error(
            429,
            "REGISTER_RATE_LIMITED",
            "Too many register attempts",
            headers={
                "Retry-After":
                str(error.retry_after_seconds or auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            },
        ) from error
    except WeakPasswordError as error:
        raise api_error(422, "WEAK_PASSWORD", str(error)) from error

    secure = is_secure_request(request, auth_settings)
    set_session_cookie(
        response,
        issued_session.session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        issued_session.csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=issued_session.user.id, email=issued_session.user.email)


@router.post(
    "/login",
    response_model=AuthUserResponse,
    responses=LOGIN_ERROR_RESPONSES,
)
async def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> AuthUserResponse:
    try:
        issued_session = await usecase.login(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
    except InvalidCredentialsError as error:
        raise api_error(401, "INVALID_CREDENTIALS", "Unauthorized") from error
    except RateLimitExceededError as error:
        raise api_error(
            429,
            "LOGIN_RATE_LIMITED",
            "Too many login attempts",
            headers={
                "Retry-After":
                str(error.retry_after_seconds or auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            },
        ) from error

    secure = is_secure_request(request, auth_settings)
    set_session_cookie(
        response,
        issued_session.session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        issued_session.csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=issued_session.user.id, email=issued_session.user.email)


@router.post(
    "/logout",
    status_code=204,
    responses=LOGOUT_ERROR_RESPONSES,
)
async def logout(
        request: Request,
        response: Response,
        auth_settings: AuthSettings = Depends(get_auth_settings),
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> Response:
    secure = is_secure_request(request, auth_settings)
    await usecase.logout(
        request.cookies.get("session_token"),
        ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
        user_agent=get_user_agent(request),
    )
    clear_session_cookie(response, secure=secure)
    clear_csrf_cookie(response, secure=secure)
    response.status_code = 204
    return response
