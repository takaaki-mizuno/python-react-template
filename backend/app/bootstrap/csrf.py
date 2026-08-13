import logging
import secrets

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from app.bootstrap.error_handlers import problem_response
from app.config.auth import AuthSettings
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.libraries.auth_cookies import csrf_cookie_name, session_cookie_name
from app.libraries.client_ip import get_user_agent, resolve_client_ip
from app.models.auth_csrf import SessionCsrfStatus

logger = logging.getLogger(__name__)

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class CSRFMiddleware:

    def __init__(self, app: ASGIApp) -> None:
        self._app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._requires_csrf(scope):
            await self._app(scope, receive, send)
            return

        request = Request(scope, receive=receive)
        try:
            error_response = await self._validate(request)
        except Exception:
            logger.exception("CSRF middleware failed")
            response = problem_response(
                500,
                "internal_server_error",
                "Internal server error",
                request_path=request.url.path,
            )
            await response(scope, receive, send)
            return

        if error_response is not None:
            await error_response(scope, receive, send)
            return
        await self._app(scope, receive, send)

    def _requires_csrf(self, scope: Scope) -> bool:
        method = str(scope["method"]).upper()
        path = _route_path(scope)
        if method not in UNSAFE_METHODS:
            return False
        if path != "/api" and not path.startswith("/api/"):
            return False

        settings = self._settings(scope)
        return path not in _csrf_exempt_paths(settings.AUTH_CSRF_EXEMPT_PATHS)

    async def _validate(self, request: Request) -> Response | None:
        cookie_token = request.cookies.get(csrf_cookie_name())
        header_token = request.headers.get("X-CSRF-Token")
        if not cookie_token or not header_token:
            return _csrf_error_response(request.url.path)

        if not secrets.compare_digest(
                cookie_token.encode("utf-8"),
                header_token.encode("utf-8"),
        ):
            return _csrf_error_response(request.url.path)

        settings = request.app.state.injector.get(AuthSettings)
        session_token = request.cookies.get(session_cookie_name(settings))
        if not session_token:
            return None

        usecase = request.app.state.injector.get(AuthUsecaseInterface)
        csrf_status = await usecase.validate_session_csrf(
            session_token=session_token,
            csrf_token=header_token,
            ip_address=resolve_client_ip(request, settings.AUTH_TRUSTED_PROXY_IPS),
            user_agent=get_user_agent(request),
        )
        if csrf_status == SessionCsrfStatus.MISMATCH:
            return _csrf_error_response(request.url.path)
        return None

    def _settings(self, scope: Scope) -> AuthSettings:
        return scope["app"].state.injector.get(AuthSettings)


def _csrf_exempt_paths(raw_paths: str) -> set[str]:
    return {path.strip() for path in raw_paths.split(",") if path.strip()}


def _route_path(scope: Scope) -> str:
    path = str(scope["path"])
    root_path = str(scope.get("root_path", ""))
    if not root_path:
        return path
    if path == root_path:
        return ""
    if path.startswith(f"{root_path}/"):
        return path[len(root_path):]
    return path


def _csrf_error_response(request_path: str) -> Response:
    return problem_response(
        403,
        "csrf_validation_failed",
        "CSRF validation failed",
        request_path=request_path,
    )
