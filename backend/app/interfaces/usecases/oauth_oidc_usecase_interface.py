from abc import ABCMeta, abstractmethod
from typing import NoReturn

from app.models.auth_context import AuthenticatedSessionContext
from app.models.language import LanguageCode
from app.models.oidc import (OidcAuthorizationPurpose, OidcAuthorizationStartResult,
                             OidcCallbackResult)


class OAuthOidcUsecaseInterface(metaclass=ABCMeta):

    @abstractmethod
    async def start_authorization(
        self,
        provider_id: str,
        redirect_path: str | None,
        purpose: OidcAuthorizationPurpose,
        current_session: AuthenticatedSessionContext | None,
        ip_address: str | None,
        language_code: LanguageCode | None = None,
    ) -> OidcAuthorizationStartResult:
        raise NotImplementedError

    @abstractmethod
    async def complete_callback(
        self,
        provider_id: str,
        state: str,
        code: str,
        browser_binding_cookie_value: str | None,
        current_session: AuthenticatedSessionContext | None,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> OidcCallbackResult:
        raise NotImplementedError

    @abstractmethod
    async def complete_error_callback(
        self,
        provider_id: str,
        state: str,
        browser_binding_cookie_value: str | None,
        provider_error: Exception,
        current_session: AuthenticatedSessionContext | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> NoReturn:
        raise NotImplementedError
