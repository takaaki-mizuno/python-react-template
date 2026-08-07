import base64
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, cast

import httpx
from authlib.integrations.httpx_client import AsyncOAuth2Client  # type: ignore[import-untyped]
from authlib.oidc.discovery import OpenIDProviderMetadata  # type: ignore[import-untyped]
from injector import NoInject, inject
from joserfc import jwt
from joserfc.jwk import KeySet

from app.config.oidc import OidcProviderSettings, OidcSettings
from app.interfaces.services.oidc_provider_client_interface import OidcProviderClientInterface
from app.libraries.session_tokens import hash_token
from app.models.oidc import OidcAuthorizationUrl, OidcTokenSetForValidation, OidcVerifiedClaims
from app.models.oidc_errors import (OidcClaimsValidationError, OidcProviderMetadataError,
                                    OidcProviderNotConfiguredError, OidcProviderUnavailableError,
                                    OidcReauthAuthTimeRequiredError, OidcReauthStaleError,
                                    OidcTokenExchangeError)

DISCOVERY_CACHE_TTL_SECONDS = 3600
JWKS_CACHE_TTL_SECONDS = 3600
NEGATIVE_CACHE_TTL_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 5.0
JWKS_REFRESH_COOLDOWN_SECONDS = 60
SAFE_ID_TOKEN_ALGORITHMS = (
    "RS256",
    "RS384",
    "RS512",
    "ES256",
    "ES384",
    "ES512",
    "PS256",
    "PS384",
    "PS512",
)


class OidcHttpClient(Protocol):

    async def get_json(self, url: str) -> dict[str, Any]:
        ...


class OAuth2ClientProtocol(Protocol):

    def create_authorization_url(self, url: str, state: str | None = None, **kwargs) -> tuple:
        ...

    async def fetch_token(self, url: str | None = None, **kwargs) -> dict[str, Any]:
        ...

    async def aclose(self) -> None:
        ...


class HttpxOidcHttpClient:

    async def get_json(self, url: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
            response = await client.get(url)
            response.raise_for_status()
            value = response.json()
            if not isinstance(value, dict):
                raise OidcProviderUnavailableError("OIDC endpoint did not return a JSON object")
            return cast(dict[str, Any], value)


@dataclass(frozen=True)
class _CacheEntry:
    value: dict[str, Any]
    expires_at: datetime


@dataclass(frozen=True)
class _NegativeCacheEntry:
    error: Exception
    expires_at: datetime


class OidcProviderClient(OidcProviderClientInterface):

    @inject
    def __init__(
        self,
        oidc_settings: OidcSettings,
        http_client: NoInject[OidcHttpClient | None] = None,
        now: NoInject[Callable[[], datetime] | None] = None,
        oauth_client_factory: NoInject[Callable[[OidcProviderSettings], OAuth2ClientProtocol]
                                       | None] = None,
    ) -> None:
        self._settings = oidc_settings
        self._http_client = http_client or HttpxOidcHttpClient()
        self._now = now or (lambda: datetime.now(UTC))
        self._oauth_client_factory = oauth_client_factory or self._build_oauth_client
        self._discovery_cache: dict[str, _CacheEntry] = {}
        self._discovery_negative_cache: dict[str, _NegativeCacheEntry] = {}
        self._jwks_cache: dict[str, _CacheEntry] = {}
        self._jwks_negative_cache: dict[str, _NegativeCacheEntry] = {}
        self._jwks_refresh_at: dict[str, datetime] = {}

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
        provider = self._provider(provider_id)
        metadata = await self._discovery(provider)
        params: dict[str, str | int] = {
            "nonce": nonce,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if prompt is not None:
            params["prompt"] = prompt
        if max_age is not None:
            params["max_age"] = max_age
        if login_hint is not None:
            params["login_hint"] = login_hint
        oauth_client = self._oauth_client_factory(provider)
        try:
            url, _ = oauth_client.create_authorization_url(
                _required_metadata_str(metadata, "authorization_endpoint"),
                state=state,
                **params,
            )
        finally:
            await _close_oauth_client(oauth_client)
        return OidcAuthorizationUrl(provider_id=provider.provider_id, url=url)

    async def exchange_code(
        self,
        provider_id: str,
        code: str,
        code_verifier: str,
    ) -> OidcTokenSetForValidation:
        provider = self._provider(provider_id)
        metadata = await self._discovery(provider)
        token_endpoint = _required_metadata_str(metadata, "token_endpoint")
        oauth_client = self._oauth_client_factory(provider)
        try:
            token = await oauth_client.fetch_token(
                url=token_endpoint,
                grant_type="authorization_code",
                code=code,
                code_verifier=code_verifier,
            )
        except Exception as exc:
            raise OidcTokenExchangeError("OIDC token exchange failed") from exc
        finally:
            await _close_oauth_client(oauth_client)
        id_token = token.get("id_token")
        if not isinstance(id_token, str) or not id_token:
            raise OidcTokenExchangeError("OIDC token response did not include id_token")
        return OidcTokenSetForValidation(id_token=id_token)

    async def validate_id_token(
        self,
        provider_id: str,
        id_token: str,
        *,
        expected_nonce: str | None = None,
        expected_nonce_hash: str | None = None,
        require_auth_time: bool = False,
    ) -> OidcVerifiedClaims:
        if expected_nonce is None and expected_nonce_hash is None:
            raise OidcClaimsValidationError("Expected nonce or nonce hash is required")
        provider = self._provider(provider_id)
        metadata = await self._discovery(provider)
        jwks = await self._jwks(provider, metadata)
        try:
            token = self._decode_id_token(id_token, jwks, metadata)
        except Exception as first_error:
            if not self._should_refresh_jwks(provider.provider_id, id_token, jwks):
                raise OidcClaimsValidationError(
                    "ID token signature validation failed") from first_error
            jwks = await self._jwks(provider, metadata, force_refresh=True)
            try:
                token = self._decode_id_token(id_token, jwks, metadata)
            except Exception as exc:
                raise OidcClaimsValidationError("ID token signature validation failed") from exc
        claims = token.claims
        now = self._now()
        issuer = _required_str(claims, "iss")
        if issuer != provider.issuer:
            raise OidcClaimsValidationError("ID token issuer mismatch")
        if not _audience_contains(claims.get("aud"), provider.client_id):
            raise OidcClaimsValidationError("ID token audience mismatch")
        subject = _required_str(claims, "sub").strip()
        if not subject:
            raise OidcClaimsValidationError("ID token subject is empty")
        nonce = _required_str(claims, "nonce")
        if expected_nonce is not None and nonce != expected_nonce:
            raise OidcClaimsValidationError("ID token nonce mismatch")
        if expected_nonce_hash is not None and hash_token(nonce) != expected_nonce_hash:
            raise OidcClaimsValidationError("ID token nonce mismatch")
        expires_at = _datetime_claim(claims, "exp")
        if expires_at <= now:
            raise OidcClaimsValidationError("ID token is expired")
        issued_at = _datetime_claim(claims, "iat")
        if issued_at > now + timedelta(
                seconds=self._settings.AUTH_OIDC_AUTH_TIME_FUTURE_LEEWAY_SECONDS):
            raise OidcClaimsValidationError("ID token issued_at is in the future")

        auth_time = _optional_datetime_claim(claims, "auth_time")
        if require_auth_time:
            if auth_time is None:
                raise OidcReauthAuthTimeRequiredError("ID token auth_time is required")
            if auth_time > now + timedelta(
                    seconds=self._settings.AUTH_OIDC_AUTH_TIME_FUTURE_LEEWAY_SECONDS):
                raise OidcReauthStaleError("ID token auth_time is in the future")

        email = _optional_normalized_email(claims.get("email"))
        email_verified = claims.get("email_verified") is True
        return OidcVerifiedClaims(
            provider_id=provider.provider_id,
            issuer=issuer,
            audience=provider.client_id,
            subject=subject,
            email=email,
            email_verified=email_verified,
            issued_at=issued_at,
            expires_at=expires_at,
            auth_time=auth_time,
            claims_json=_claims_json(provider, claims, issuer, subject, email, email_verified,
                                     auth_time),
        )

    def _decode_id_token(self, id_token: str, jwks: dict[str, Any], metadata: dict[str, Any]):
        algorithms = _id_token_algorithms(metadata)
        return jwt.decode(
            id_token,
            KeySet.import_key_set(cast(Any, jwks)),
            algorithms=algorithms,
        )

    def _provider(self, provider_id: str) -> OidcProviderSettings:
        try:
            return self._settings.get_provider(provider_id)
        except KeyError as exc:
            raise OidcProviderNotConfiguredError(provider_id) from exc

    async def _discovery(self, provider: OidcProviderSettings) -> dict[str, Any]:
        cache_key = provider.provider_id
        url = f"{provider.issuer.rstrip('/')}/.well-known/openid-configuration"
        metadata = await self._cached_json(
            cache_key,
            self._discovery_cache,
            self._discovery_negative_cache,
            lambda: self._get_json(url),
            DISCOVERY_CACHE_TTL_SECONDS,
        )
        self._validate_discovery_metadata(provider, metadata)
        return metadata

    async def _jwks(
        self,
        provider: OidcProviderSettings,
        discovery: dict[str, Any],
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        jwks_uri = _required_metadata_str(discovery, "jwks_uri")
        if force_refresh:
            self._jwks_cache.pop(provider.provider_id, None)
            self._jwks_refresh_at[provider.provider_id] = self._now()
        return await self._cached_json(
            provider.provider_id,
            self._jwks_cache,
            self._jwks_negative_cache,
            lambda: self._get_json(jwks_uri),
            JWKS_CACHE_TTL_SECONDS,
        )

    async def _cached_json(
        self,
        cache_key: str,
        cache: dict[str, _CacheEntry],
        negative_cache: dict[str, _NegativeCacheEntry],
        loader: Callable[[], Awaitable[dict[str, Any]]],
        ttl_seconds: int,
    ) -> dict[str, Any]:
        now = self._now()
        cached = cache.get(cache_key)
        if cached is not None and cached.expires_at > now:
            return cached.value
        failed = negative_cache.get(cache_key)
        if failed is not None and failed.expires_at > now:
            raise OidcProviderUnavailableError(
                "OIDC provider metadata is temporarily unavailable") from failed.error
        try:
            value = await loader()
        except Exception as exc:
            negative_cache[cache_key] = _NegativeCacheEntry(
                error=exc,
                expires_at=now + timedelta(seconds=NEGATIVE_CACHE_TTL_SECONDS),
            )
            raise OidcProviderUnavailableError("OIDC provider metadata is unavailable") from exc
        cache[cache_key] = _CacheEntry(
            value=value,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        negative_cache.pop(cache_key, None)
        return value

    async def _get_json(self, url: str) -> dict[str, Any]:
        return await self._http_client.get_json(url)

    def _build_oauth_client(self, provider: OidcProviderSettings) -> OAuth2ClientProtocol:
        return AsyncOAuth2Client(
            client_id=provider.client_id,
            client_secret=provider.client_secret,
            scope=" ".join(provider.scope),
            redirect_uri=self._settings.redirect_uri_for(provider.provider_id),
            timeout=HTTP_TIMEOUT_SECONDS,
        )

    def _validate_discovery_metadata(
        self,
        provider: OidcProviderSettings,
        metadata: dict[str, Any],
    ) -> None:
        try:
            OpenIDProviderMetadata(metadata).validate()
        except Exception as exc:
            raise OidcProviderMetadataError("OIDC discovery metadata is invalid") from exc
        if metadata.get("issuer") != provider.issuer:
            raise OidcProviderMetadataError("OIDC discovery issuer mismatch")
        _id_token_algorithms(metadata)

    def _should_refresh_jwks(
        self,
        provider_id: str,
        id_token: str,
        jwks: dict[str, Any],
    ) -> bool:
        kid = _jwt_kid(id_token)
        if kid is None or _jwks_has_kid(jwks, kid):
            return False
        refreshed_at = self._jwks_refresh_at.get(provider_id)
        return (refreshed_at is None
                or self._now() - refreshed_at >= timedelta(seconds=JWKS_REFRESH_COOLDOWN_SECONDS))


def _required_str(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise OidcClaimsValidationError(f"OIDC required claim or metadata is missing: {key}")
    return value


def _required_metadata_str(mapping: dict[str, Any], key: str) -> str:
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise OidcProviderMetadataError(f"OIDC required metadata is missing: {key}")
    return value


def _audience_contains(audience: Any, client_id: str) -> bool:
    if isinstance(audience, str):
        return audience == client_id
    if isinstance(audience, list):
        return client_id in audience
    return False


def _id_token_algorithms(metadata: dict[str, Any]) -> tuple[str, ...]:
    algorithms = metadata.get("id_token_signing_alg_values_supported")
    if isinstance(algorithms, list):
        supported = tuple(algorithm for algorithm in algorithms
                          if isinstance(algorithm, str) and algorithm in SAFE_ID_TOKEN_ALGORITHMS)
        if supported:
            return supported
    raise OidcProviderMetadataError("OIDC provider does not advertise a safe ID token algorithm")


def _datetime_claim(claims: dict[str, Any], key: str) -> datetime:
    value = claims.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise OidcClaimsValidationError(f"ID token {key} claim is missing or invalid")
    return datetime.fromtimestamp(value, UTC)


def _optional_datetime_claim(claims: dict[str, Any], key: str) -> datetime | None:
    value = claims.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise OidcClaimsValidationError(f"ID token {key} claim is invalid")
    return datetime.fromtimestamp(value, UTC)


def _optional_normalized_email(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    email = value.strip().lower()
    return email or None


def _claims_json(
    provider: OidcProviderSettings,
    claims: dict[str, Any],
    issuer: str,
    subject: str,
    email: str | None,
    email_verified: bool,
    auth_time: datetime | None,
) -> dict[str, Any]:
    persisted_claims: dict[str, Any] = {
        "iss": issuer,
        "sub": subject,
        "email": email,
        "email_verified": email_verified,
    }
    if auth_time is not None:
        persisted_claims["auth_time"] = int(auth_time.timestamp())
    for claim_name in provider.claims_allowlist:
        if claim_name in claims and claim_name not in persisted_claims:
            persisted_claims[claim_name] = claims[claim_name]
    return persisted_claims


def _jwt_kid(id_token: str) -> str | None:
    try:
        header_segment = id_token.split(".", 1)[0]
        padded = header_segment + "=" * (-len(header_segment) % 4)
        header = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
    except Exception:
        return None
    kid = header.get("kid")
    if isinstance(kid, str) and kid:
        return kid
    return None


def _jwks_has_kid(jwks: dict[str, Any], kid: str) -> bool:
    keys = jwks.get("keys")
    if not isinstance(keys, list):
        return False
    return any(isinstance(key, dict) and key.get("kid") == kid for key in keys)


async def _close_oauth_client(oauth_client: OAuth2ClientProtocol) -> None:
    close = getattr(oauth_client, "aclose", None)
    if close is not None:
        await close()
