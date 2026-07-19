from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config.auth import AuthSettings
from app.controllers.auth_dependencies import (get_client_ip,
                                               get_request_auth_settings,
                                               get_user_agent, require_csrf,
                                               require_current_session)
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_errors import (EmailAlreadyRegisteredError,
                                    InvalidCredentialsError,
                                    RateLimitExceededError, WeakPasswordError)
from app.models.auth_schemas import (AuthUserResponse, CsrfTokenResponse,
                                     LoginRequest, RegisterRequest)
from app.usecases.auth_usecase import AuthenticatedSessionContext

router = APIRouter(prefix="/auth", tags=["auth"])


def is_secure_request(
    request: Request,
    auth_settings: AuthSettings,
) -> bool:
    if request.url.scheme == "https":
        return True
    return auth_settings.ENVIRONMENT not in {
        "local",
        "development",
        "test",
    }


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
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> CsrfTokenResponse:
    response.headers["Cache-Control"] = "no-store"
    existing_csrf_token = request.cookies.get("csrf_token")
    if existing_csrf_token:
        session_token = request.cookies.get("session_token")
        if not session_token:
            return CsrfTokenResponse(csrfToken=existing_csrf_token)

        usecase = request.app.state.injector.get(AuthUsecaseInterface)
        csrf_status = await usecase.validate_session_csrf(
            session_token=session_token,
            csrf_token=existing_csrf_token,
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
        if csrf_status is not False:
            return CsrfTokenResponse(csrfToken=existing_csrf_token)

    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    csrf_token = await usecase.issue_csrf_token(
        session_token=request.cookies.get("session_token"), )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=is_secure_request(request, auth_settings),
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return CsrfTokenResponse(csrfToken=csrf_token)


@router.get("/me", response_model=AuthUserResponse)
async def get_me(
    response: Response,
    auth_context: AuthenticatedSessionContext = Depends(
        require_current_session),
) -> AuthUserResponse:
    response.headers["Cache-Control"] = "no-store"
    return AuthUserResponse(id=auth_context.user.id,
                            email=auth_context.user.email)


@router.post(
    "/register",
    response_model=AuthUserResponse,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> AuthUserResponse:
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    try:
        user, _session, session_token, csrf_token = await usecase.register(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(status_code=409,
                            detail="Email already registered") from error
    except RateLimitExceededError as error:
        raise HTTPException(
            status_code=429,
            detail="Too many register attempts",
            headers={
                "Retry-After":
                str(auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            },
        ) from error
    except WeakPasswordError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error

    secure = is_secure_request(request, auth_settings)
    set_session_cookie(
        response,
        session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=user.id, email=user.email)


@router.post(
    "/login",
    response_model=AuthUserResponse,
    dependencies=[Depends(require_csrf)],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> AuthUserResponse:
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    try:
        user, _session, session_token, csrf_token = await usecase.login(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=get_client_ip(request),
            user_agent=get_user_agent(request),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=401, detail="Unauthorized") from error
    except RateLimitExceededError as error:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={
                "Retry-After":
                str(auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
            },
        ) from error

    secure = is_secure_request(request, auth_settings)
    set_session_cookie(
        response,
        session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=user.id, email=user.email)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(
    request: Request,
    response: Response,
    auth_settings: AuthSettings = Depends(get_request_auth_settings),
) -> Response:
    secure = is_secure_request(request, auth_settings)
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    await usecase.logout(
        request.cookies.get("session_token"),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    clear_session_cookie(response, secure=secure)
    clear_csrf_cookie(response, secure=secure)
    response.status_code = 204
    return response
