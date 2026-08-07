from abc import ABCMeta, abstractmethod

from app.models.oidc import OidcAuthorizationUrl, OidcTokenSetForValidation, OidcVerifiedClaims


class OidcProviderClientInterface(metaclass=ABCMeta):

    @abstractmethod
    async def build_authorization_url(
        self,
        provider_id: str,
        state: str,
        nonce: str,
        code_challenge: str,
        *,
        prompt: str | None = None,
        max_age: int | None = None,
        login_hint: str | None = None,
    ) -> OidcAuthorizationUrl:
        raise NotImplementedError

    @abstractmethod
    async def exchange_code(
        self,
        provider_id: str,
        code: str,
        code_verifier: str,
    ) -> OidcTokenSetForValidation:
        raise NotImplementedError

    @abstractmethod
    async def validate_id_token(
        self,
        provider_id: str,
        id_token: str,
        *,
        expected_nonce: str | None = None,
        expected_nonce_hash: str | None = None,
        require_auth_time: bool = False,
    ) -> OidcVerifiedClaims:
        raise NotImplementedError
