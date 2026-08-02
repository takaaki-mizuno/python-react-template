import secrets
from ipaddress import ip_address

from fastapi import Depends, Request

from app.bootstrap.dependencies import inject
from app.bootstrap.error_handlers import api_error
from app.config.auth import AuthSettings
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_context import AuthenticatedSessionContext

get_auth_settings = inject(AuthSettings)
get_auth_usecase = inject(AuthUsecaseInterface)


def get_client_ip(request: Request) -> str | None:
    if not request.client:
        return None
    try:
        return str(ip_address(request.client.host))
    except ValueError:
        return None


def get_user_agent(request: Request) -> str | None:
    user_agent = request.headers.get("user-agent")
    return user_agent[:512] if user_agent else None


async def require_csrf(
        request: Request,
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> None:
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token:
        raise api_error(403, "CSRF_VALIDATION_FAILED",
                        "CSRF validation failed")

    if not secrets.compare_digest(
            cookie_token.encode("utf-8"),
            header_token.encode("utf-8"),
    ):
        raise api_error(403, "CSRF_VALIDATION_FAILED",
                        "CSRF validation failed")

    session_token = request.cookies.get("session_token")
    if not session_token:
        return

    is_valid_session_csrf = await usecase.validate_session_csrf(
        session_token=session_token,
        csrf_token=header_token,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    if is_valid_session_csrf is False:
        raise api_error(403, "CSRF_VALIDATION_FAILED",
                        "CSRF validation failed")


async def require_current_session(
    request: Request,
    usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
) -> AuthenticatedSessionContext:
    auth_context = await usecase.authenticate_session(
        session_token=request.cookies.get("session_token"),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    if auth_context is None:
        raise api_error(401, "UNAUTHORIZED", "Unauthorized")
    return auth_context
