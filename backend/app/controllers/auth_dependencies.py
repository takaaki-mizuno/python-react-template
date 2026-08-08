from collections.abc import Awaitable, Callable, Iterable
from logging import Logger

from fastapi import Depends, Request

from app.bootstrap.dependencies import inject
from app.bootstrap.error_handlers import api_error
from app.config.auth import AuthSettings
from app.config.oidc import OidcSettings
from app.interfaces.usecases.account_deletion_usecase_interface import \
    AccountDeletionUsecaseInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.oauth_oidc_usecase_interface import OAuthOidcUsecaseInterface
from app.libraries.auth_cookies import session_cookie_name
from app.libraries.client_ip import get_user_agent as resolve_user_agent
from app.libraries.client_ip import resolve_client_ip
from app.models.auth_context import AuthenticatedSessionContext

get_auth_settings = inject(AuthSettings)
get_oidc_settings = inject(OidcSettings)
get_auth_usecase = inject(AuthUsecaseInterface)
get_oauth_oidc_usecase = inject(OAuthOidcUsecaseInterface)
get_account_deletion_usecase = inject(AccountDeletionUsecaseInterface)
get_logger = inject(Logger)


def get_client_ip(request: Request, trusted_proxy_ips: str = "") -> str | None:
    return resolve_client_ip(request, trusted_proxy_ips)


def get_user_agent(request: Request) -> str | None:
    return resolve_user_agent(request)


async def require_current_session(
        request: Request,
        usecase: AuthUsecaseInterface = Depends(get_auth_usecase),
        auth_settings: AuthSettings = Depends(get_auth_settings),
) -> AuthenticatedSessionContext:
    auth_context = await usecase.authenticate_session(
        session_token=request.cookies.get(session_cookie_name(auth_settings)),
        ip_address=get_client_ip(request, auth_settings.AUTH_TRUSTED_PROXY_IPS),
        user_agent=get_user_agent(request),
    )
    if auth_context is None:
        raise api_error(401, "UNAUTHORIZED", "Unauthorized")
    return auth_context


AuthDependency = Callable[..., Awaitable[AuthenticatedSessionContext]]


def require_permission(permission_code: str) -> AuthDependency:

    async def dependency(
        auth_context: AuthenticatedSessionContext = Depends(require_current_session),
    ) -> AuthenticatedSessionContext:
        if permission_code not in auth_context.permissions:
            raise api_error(403, "PERMISSION_DENIED", "Permission denied")
        return auth_context

    return dependency


def require_any_permission(permission_codes: Iterable[str]) -> AuthDependency:
    required_permissions = frozenset(permission_codes)
    if not required_permissions:
        raise ValueError("permission_codes must not be empty")

    async def dependency(
        auth_context: AuthenticatedSessionContext = Depends(require_current_session),
    ) -> AuthenticatedSessionContext:
        if not auth_context.permissions.intersection(required_permissions):
            raise api_error(403, "PERMISSION_DENIED", "Permission denied")
        return auth_context

    return dependency
