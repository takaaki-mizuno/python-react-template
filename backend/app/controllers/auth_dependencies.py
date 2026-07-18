import secrets
from ipaddress import ip_address

from fastapi import HTTPException, Request

from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.usecases.auth_usecase import AuthenticatedSessionContext


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


async def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if (not cookie_token or not header_token
            or not secrets.compare_digest(cookie_token, header_token)):
        raise HTTPException(status_code=403, detail="CSRF validation failed")

    session_token = request.cookies.get("session_token")
    if not session_token:
        return

    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    is_valid_session_csrf = await usecase.validate_session_csrf(
        session_token=session_token,
        csrf_token=header_token,
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    if is_valid_session_csrf is False:
        raise HTTPException(status_code=403, detail="CSRF validation failed")


async def require_current_session(
        request: Request) -> AuthenticatedSessionContext:
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    auth_context = await usecase.authenticate_session(
        session_token=request.cookies.get("session_token"),
        ip_address=get_client_ip(request),
        user_agent=get_user_agent(request),
    )
    if auth_context is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return auth_context
