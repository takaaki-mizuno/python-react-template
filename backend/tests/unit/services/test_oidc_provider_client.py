import base64
import json
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from joserfc import jwt
from joserfc.jwk import RSAKey

from app.config.oidc import OidcProviderSettings, OidcSettings
from app.models.oidc_errors import (OidcClaimsValidationError, OidcProviderMetadataError,
                                    OidcProviderNotConfiguredError, OidcProviderUnavailableError,
                                    OidcReauthAuthTimeRequiredError, OidcReauthStaleError,
                                    OidcTokenExchangeError)
from app.services.oidc_provider_client import OidcProviderClient

pytestmark = pytest.mark.asyncio

FIXED_NOW = datetime(2026, 8, 7, 1, 0, 0, tzinfo=UTC)


def _settings() -> OidcSettings:
    return OidcSettings(
        providers=(OidcProviderSettings(
            provider_id="google",
            display_name="Google",
            issuer="https://accounts.example.com",
            client_id="client-id",
            client_secret="client-secret",
            scope=("openid", "email", "profile"),
            trust_verified_email=True,
            auto_provision="enabled",
            link_mode="auto",
            callback_path="/api/auth/oidc/google/callback",
            claims_allowlist=("hd", "locale"),
        ), ),
        AUTH_OIDC_REDIRECT_BASE_URL="https://app.example.com",
        AUTH_OIDC_REAUTH_FRESHNESS_SECONDS=300,
        AUTH_OIDC_AUTH_TIME_FUTURE_LEEWAY_SECONDS=60,
    )


def _rsa_key(kid: str = "test-key") -> RSAKey:
    return RSAKey.generate_key(
        parameters={
            "kid": kid,
            "alg": "RS256",
            "use": "sig",
        },
        private=True,
    )


def _id_token(
    key: RSAKey,
    *,
    issuer: str = "https://accounts.example.com",
    audience: str = "client-id",
    subject: str = "subject-1",
    email: str | None = "USER@EXAMPLE.COM",
    email_verified: bool | None = True,
    nonce: str = "nonce-1",
    expires_at: datetime | None = None,
    issued_at: datetime | None = None,
    auth_time: datetime | None = None,
    kid: str = "test-key",
    extra_claims: dict | None = None,
) -> str:
    expires_at = expires_at or FIXED_NOW + timedelta(minutes=5)
    issued_at = issued_at or FIXED_NOW - timedelta(seconds=30)
    claims = {
        "iss": issuer,
        "aud": audience,
        "sub": subject,
        "nonce": nonce,
        "exp": int(expires_at.timestamp()),
        "iat": int(issued_at.timestamp()),
        **(extra_claims or {}),
    }
    if email is not None:
        claims["email"] = email
    if email_verified is not None:
        claims["email_verified"] = email_verified
    if auth_time is not None:
        claims["auth_time"] = int(auth_time.timestamp())
    return jwt.encode({"alg": "RS256", "kid": kid}, claims, key)


def _unsigned_id_token(*, subject: str = "subject-1", nonce: str = "nonce-1") -> str:
    claims = {
        "iss": "https://accounts.example.com",
        "aud": "client-id",
        "sub": subject,
        "nonce": nonce,
        "exp": int((FIXED_NOW + timedelta(minutes=5)).timestamp()),
        "iat": int((FIXED_NOW - timedelta(seconds=30)).timestamp()),
    }
    header = {"alg": "none"}
    return f"{_b64_json(header)}.{_b64_json(claims)}."


def _b64_json(value: dict) -> str:
    return base64.urlsafe_b64encode(json.dumps(value).encode("utf-8")).rstrip(b"=").decode("ascii")


def _discovery() -> dict:
    return {
        "issuer": "https://accounts.example.com",
        "authorization_endpoint": "https://accounts.example.com/oauth2/v2/auth",
        "token_endpoint": "https://accounts.example.com/token",
        "jwks_uri": "https://accounts.example.com/.well-known/jwks.json",
        "response_types_supported": ["code"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256"],
    }


class HttpStub:

    def __init__(
        self,
        *,
        key: RSAKey | None = None,
        discovery: dict | None = None,
        jwks_sequence: list[dict] | None = None,
    ) -> None:
        self.key = key or _rsa_key()
        self.discovery = discovery or _discovery()
        self.jwks_sequence = jwks_sequence or [{"keys": [self.key.as_dict(private=False)]}]
        self.get_calls: list[str] = []

    async def get_json(self, url: str) -> dict:
        self.get_calls.append(url)
        if url.endswith("/.well-known/openid-configuration"):
            return self.discovery
        if url.endswith("/.well-known/jwks.json"):
            if len(self.jwks_sequence) > 1:
                return self.jwks_sequence.pop(0)
            return self.jwks_sequence[0]
        raise AssertionError(f"Unexpected GET: {url}")


class OAuthClientStub:

    def __init__(self, token_response: dict | None = None) -> None:
        self.token_response = token_response or {"id_token": "id-token-value"}
        self.authorization_calls: list[tuple[str, str | None, dict]] = []
        self.fetch_token_calls: list[tuple[str | None, dict]] = []
        self.close_calls = 0

    def create_authorization_url(self, url: str, state: str | None = None, **kwargs) -> tuple:
        self.authorization_calls.append((url, state, kwargs))
        query = {
            "response_type": "code",
            "client_id": "client-id",
            "redirect_uri": "https://app.example.com/api/auth/oidc/google/callback",
            "scope": "openid email profile",
            "state": state,
            **kwargs,
        }
        from urllib.parse import urlencode

        return f"{url}?{urlencode(query)}", state

    async def fetch_token(self, url: str | None = None, **kwargs) -> dict:
        self.fetch_token_calls.append((url, kwargs))
        return self.token_response

    async def aclose(self) -> None:
        self.close_calls += 1


class FailingOAuthClientStub(OAuthClientStub):

    async def fetch_token(self, url: str | None = None, **kwargs) -> dict:
        self.fetch_token_calls.append((url, kwargs))
        raise RuntimeError("token endpoint unavailable")


async def test_build_authorization_url_uses_configured_redirect_uri_and_pkce() -> None:
    http = HttpStub()
    oauth_client = OAuthClientStub()
    client = OidcProviderClient(
        _settings(),
        http_client=http,
        now=lambda: FIXED_NOW,
        oauth_client_factory=lambda _provider: oauth_client,
    )

    authorization = await client.build_authorization_url(
        provider_id="google",
        state="state-1",
        nonce="nonce-1",
        code_challenge="challenge-1",
        prompt="login",
        max_age=0,
        login_hint="user@example.com",
    )

    parsed = urlparse(authorization.url)
    params = parse_qs(parsed.query)
    assert parsed.scheme == "https"
    assert parsed.netloc == "accounts.example.com"
    assert params["client_id"] == ["client-id"]
    assert params["redirect_uri"] == ["https://app.example.com/api/auth/oidc/google/callback"]
    assert params["scope"] == ["openid email profile"]
    assert params["state"] == ["state-1"]
    assert params["nonce"] == ["nonce-1"]
    assert params["code_challenge"] == ["challenge-1"]
    assert params["code_challenge_method"] == ["S256"]
    assert params["prompt"] == ["login"]
    assert params["max_age"] == ["0"]
    assert params["login_hint"] == ["user@example.com"]
    assert oauth_client.authorization_calls[0][0] == ("https://accounts.example.com/oauth2/v2/auth")
    assert oauth_client.close_calls == 1


async def test_exchange_code_posts_to_discovered_token_endpoint_without_persisting_tokens() -> None:
    oauth_client = OAuthClientStub(
        token_response={
            "id_token": "id-token-value",
            "access_token": "access-token-value",
            "refresh_token": "refresh-token-value",
        })
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(),
        now=lambda: FIXED_NOW,
        oauth_client_factory=lambda _provider: oauth_client,
    )

    token_set = await client.exchange_code(
        provider_id="google",
        code="code-1",
        code_verifier="verifier-1",
    )

    assert token_set.id_token == "id-token-value"
    assert not hasattr(token_set, "access_token")
    assert not hasattr(token_set, "refresh_token")
    assert oauth_client.fetch_token_calls == [(
        "https://accounts.example.com/token",
        {
            "code": "code-1",
            "code_verifier": "verifier-1",
            "grant_type": "authorization_code",
        },
    )]
    assert oauth_client.close_calls == 1


async def test_exchange_code_rejects_token_response_without_id_token() -> None:
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(),
        now=lambda: FIXED_NOW,
        oauth_client_factory=lambda _provider: OAuthClientStub(
            token_response={"access_token": "access-token-value"}),
    )

    with pytest.raises(OidcTokenExchangeError):
        await client.exchange_code("google", code="code-1", code_verifier="verifier-1")


async def test_exchange_code_closes_oauth_client_when_fetch_token_fails() -> None:
    oauth_client = FailingOAuthClientStub()
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(),
        now=lambda: FIXED_NOW,
        oauth_client_factory=lambda _provider: oauth_client,
    )

    with pytest.raises(OidcTokenExchangeError):
        await client.exchange_code("google", code="code-1", code_verifier="verifier-1")

    assert oauth_client.fetch_token_calls == [(
        "https://accounts.example.com/token",
        {
            "code": "code-1",
            "code_verifier": "verifier-1",
            "grant_type": "authorization_code",
        },
    )]
    assert oauth_client.close_calls == 1


async def test_exchange_code_preserves_metadata_error_for_missing_token_endpoint() -> None:
    discovery = {key: value for key, value in _discovery().items() if key != "token_endpoint"}
    oauth_client = OAuthClientStub()
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(discovery=discovery),
        now=lambda: FIXED_NOW,
        oauth_client_factory=lambda _provider: oauth_client,
    )

    with pytest.raises(OidcProviderMetadataError):
        await client.exchange_code("google", code="code-1", code_verifier="verifier-1")

    assert oauth_client.fetch_token_calls == []
    assert oauth_client.close_calls == 0


async def test_validate_id_token_returns_normalized_claims_and_persisted_claims() -> None:
    key = _rsa_key()
    http = HttpStub(key=key)
    client = OidcProviderClient(_settings(), http_client=http, now=lambda: FIXED_NOW)
    token = _id_token(
        key,
        email="USER@EXAMPLE.COM",
        extra_claims={
            "hd": "example.com",
            "locale": "ja",
            "name": "Ignored Name",
        },
    )

    claims = await client.validate_id_token(
        provider_id="google",
        id_token=token,
        expected_nonce="nonce-1",
    )

    assert claims.provider_id == "google"
    assert claims.subject == "subject-1"
    assert claims.email == "user@example.com"
    assert claims.email_verified is True
    assert claims.claims_json == {
        "iss": "https://accounts.example.com",
        "sub": "subject-1",
        "email": "user@example.com",
        "email_verified": True,
        "hd": "example.com",
        "locale": "ja",
    }


async def test_validate_id_token_does_not_allow_raw_claims_to_override_base_claims() -> None:
    settings = OidcSettings(
        providers=(OidcProviderSettings(
            provider_id="google",
            display_name="Google",
            issuer="https://accounts.example.com",
            client_id="client-id",
            client_secret="client-secret",
            callback_path="/api/auth/oidc/google/callback",
            claims_allowlist=("sub", "email", "hd"),
        ), ),
        AUTH_OIDC_REDIRECT_BASE_URL="https://app.example.com",
    )
    key = _rsa_key()
    client = OidcProviderClient(settings, http_client=HttpStub(key=key), now=lambda: FIXED_NOW)

    claims = await client.validate_id_token(
        provider_id="google",
        id_token=_id_token(key, email="USER@EXAMPLE.COM", extra_claims={"hd": "example.com"}),
        expected_nonce="nonce-1",
    )

    assert claims.claims_json["sub"] == "subject-1"
    assert claims.claims_json["email"] == "user@example.com"
    assert claims.claims_json["hd"] == "example.com"


async def test_validate_id_token_does_not_apply_provider_trust_policy_to_email() -> None:
    key = _rsa_key()
    client = OidcProviderClient(_settings(), http_client=HttpStub(key=key), now=lambda: FIXED_NOW)

    claims_without_email = await client.validate_id_token(
        provider_id="google",
        id_token=_id_token(key, email=None, email_verified=None),
        expected_nonce="nonce-1",
    )
    claims_with_unverified_email = await client.validate_id_token(
        provider_id="google",
        id_token=_id_token(key, email="USER@EXAMPLE.COM", email_verified=False),
        expected_nonce="nonce-1",
    )

    assert claims_without_email.email is None
    assert claims_without_email.email_verified is False
    assert claims_with_unverified_email.email == "user@example.com"
    assert claims_with_unverified_email.email_verified is False


@pytest.mark.parametrize(
    ("claim_overrides", "error_type"),
    [
        ({
            "issuer": "https://other.example.com"
        }, OidcClaimsValidationError),
        ({
            "audience": "other-client-id"
        }, OidcClaimsValidationError),
        ({
            "expires_at": FIXED_NOW - timedelta(seconds=1)
        }, OidcClaimsValidationError),
        ({
            "nonce": "other-nonce"
        }, OidcClaimsValidationError),
        ({
            "subject": ""
        }, OidcClaimsValidationError),
    ],
)
async def test_validate_id_token_rejects_invalid_claims(claim_overrides, error_type) -> None:
    key = _rsa_key()
    client = OidcProviderClient(_settings(), http_client=HttpStub(key=key), now=lambda: FIXED_NOW)
    token = _id_token(key, **claim_overrides)

    with pytest.raises(error_type):
        await client.validate_id_token(
            provider_id="google",
            id_token=token,
            expected_nonce="nonce-1",
        )


async def test_validate_id_token_requires_auth_time_for_reauth() -> None:
    key = _rsa_key()
    client = OidcProviderClient(_settings(), http_client=HttpStub(key=key), now=lambda: FIXED_NOW)

    with pytest.raises(OidcReauthAuthTimeRequiredError):
        await client.validate_id_token(
            provider_id="google",
            id_token=_id_token(key),
            expected_nonce="nonce-1",
            require_auth_time=True,
        )


async def test_validate_id_token_rejects_auth_time_too_far_in_future() -> None:
    key = _rsa_key()
    client = OidcProviderClient(_settings(), http_client=HttpStub(key=key), now=lambda: FIXED_NOW)

    with pytest.raises(OidcReauthStaleError):
        await client.validate_id_token(
            provider_id="google",
            id_token=_id_token(key, auth_time=FIXED_NOW + timedelta(seconds=61)),
            expected_nonce="nonce-1",
            require_auth_time=True,
        )


async def test_discovery_and_jwks_are_loaded_lazily_and_cached() -> None:
    key = _rsa_key()
    http = HttpStub(key=key)
    client = OidcProviderClient(_settings(), http_client=http, now=lambda: FIXED_NOW)
    token = _id_token(key)

    await client.validate_id_token("google", token, expected_nonce="nonce-1")
    await client.validate_id_token("google", token, expected_nonce="nonce-1")

    assert http.get_calls.count(
        "https://accounts.example.com/.well-known/openid-configuration") == 1
    assert http.get_calls.count("https://accounts.example.com/.well-known/jwks.json") == 1


async def test_discovery_issuer_mismatch_is_metadata_error() -> None:
    discovery = {**_discovery(), "issuer": "https://evil.example.com"}
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(discovery=discovery),
        now=lambda: FIXED_NOW,
    )

    with pytest.raises(OidcProviderMetadataError):
        await client.build_authorization_url(
            provider_id="google",
            state="state-1",
            nonce="nonce-1",
            code_challenge="challenge-1",
        )


async def test_missing_discovery_endpoint_is_metadata_error() -> None:
    discovery = {key: value for key, value in _discovery().items() if key != "token_endpoint"}
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(discovery=discovery),
        now=lambda: FIXED_NOW,
    )

    with pytest.raises(OidcProviderMetadataError):
        await client.exchange_code("google", code="code-1", code_verifier="verifier-1")


async def test_unsafe_id_token_algorithms_are_rejected() -> None:
    discovery = {
        **_discovery(),
        "id_token_signing_alg_values_supported": ["none", "HS256"],
    }
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(discovery=discovery),
        now=lambda: FIXED_NOW,
    )

    with pytest.raises(OidcProviderMetadataError):
        await client.validate_id_token(
            "google",
            _unsigned_id_token(subject="attacker"),
            expected_nonce="nonce-1",
        )


async def test_unsigned_id_token_is_rejected_even_when_discovery_lists_none_with_safe_alg() -> None:
    discovery = {
        **_discovery(),
        "id_token_signing_alg_values_supported": ["none", "RS256"],
    }
    client = OidcProviderClient(
        _settings(),
        http_client=HttpStub(discovery=discovery),
        now=lambda: FIXED_NOW,
    )

    with pytest.raises(OidcClaimsValidationError):
        await client.validate_id_token(
            "google",
            _unsigned_id_token(subject="attacker"),
            expected_nonce="nonce-1",
        )


async def test_jwks_is_refetched_only_for_missing_kid_and_then_rate_limited() -> None:
    old_key = _rsa_key("old-key")
    new_key = _rsa_key("new-key")
    forged_key = _rsa_key("forged-key")
    http = HttpStub(jwks_sequence=[
        {
            "keys": [old_key.as_dict(private=False)]
        },
        {
            "keys": [new_key.as_dict(private=False)]
        },
        {
            "keys": [forged_key.as_dict(private=False)]
        },
    ])
    client = OidcProviderClient(_settings(), http_client=http, now=lambda: FIXED_NOW)

    claims = await client.validate_id_token(
        "google",
        _id_token(new_key, kid="new-key"),
        expected_nonce="nonce-1",
    )
    assert claims.subject == "subject-1"
    assert http.get_calls.count("https://accounts.example.com/.well-known/jwks.json") == 2

    with pytest.raises(OidcClaimsValidationError):
        await client.validate_id_token(
            "google",
            _id_token(forged_key, kid="forged-key"),
            expected_nonce="nonce-1",
        )
    assert http.get_calls.count("https://accounts.example.com/.well-known/jwks.json") == 2


async def test_jwks_is_not_refetched_for_invalid_signature_with_existing_kid() -> None:
    trusted_key = _rsa_key("same-kid")
    attacker_key = _rsa_key("same-kid")
    http = HttpStub(jwks_sequence=[{"keys": [trusted_key.as_dict(private=False)]}])
    client = OidcProviderClient(_settings(), http_client=http, now=lambda: FIXED_NOW)

    with pytest.raises(OidcClaimsValidationError):
        await client.validate_id_token(
            "google",
            _id_token(attacker_key, kid="same-kid"),
            expected_nonce="nonce-1",
        )

    assert http.get_calls.count("https://accounts.example.com/.well-known/jwks.json") == 1


async def test_discovery_failure_is_negative_cached_without_startup_fetch() -> None:

    class FailingHttp:

        def __init__(self) -> None:
            self.get_calls: list[str] = []

        async def get_json(self, url: str) -> dict:
            self.get_calls.append(url)
            raise RuntimeError("provider unavailable")

        async def post_form(
            self,
            url: str,
            data: dict[str, str],
            client_id: str,
            client_secret: str,
        ) -> dict:
            raise AssertionError("token endpoint should not be called")

    http = FailingHttp()
    client = OidcProviderClient(_settings(), http_client=http, now=lambda: FIXED_NOW)

    with pytest.raises(OidcProviderUnavailableError):
        await client.build_authorization_url(
            provider_id="google",
            state="state-1",
            nonce="nonce-1",
            code_challenge="challenge-1",
        )
    with pytest.raises(OidcProviderUnavailableError):
        await client.build_authorization_url(
            provider_id="google",
            state="state-2",
            nonce="nonce-2",
            code_challenge="challenge-2",
        )

    assert http.get_calls == ["https://accounts.example.com/.well-known/openid-configuration"]


async def test_unknown_provider_raises_domain_error() -> None:
    client = OidcProviderClient(_settings(), http_client=HttpStub(), now=lambda: FIXED_NOW)

    with pytest.raises(OidcProviderNotConfiguredError):
        await client.build_authorization_url(
            provider_id="unknown",
            state="state-1",
            nonce="nonce-1",
            code_challenge="challenge-1",
        )
