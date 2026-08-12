from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.bootstrap.create_app import create_app
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from app.interfaces.services.oidc_provider_client_interface import OidcProviderClientInterface
from app.libraries.clock import utcnow
from app.models.oidc import OidcAuthorizationUrl, OidcTokenSetForValidation, OidcVerifiedClaims
from app.models.oidc_errors import OidcClaimsValidationError, OidcReauthStaleError

pytestmark = pytest.mark.integration


@pytest.fixture
def oidc_client(monkeypatch):
    yield from _oidc_client(monkeypatch)


@pytest.fixture
def oidc_link_only_client(monkeypatch):
    yield from _oidc_client(monkeypatch, auto_provision="link-only")


def _oidc_client(monkeypatch, *, auto_provision: str = "enabled"):
    from tests.integration.helpers import require_test_database_url

    monkeypatch.setenv("DATABASE_URL", require_test_database_url())
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
    monkeypatch.setenv("AUTH_OIDC_ENABLED_PROVIDERS", "google")
    monkeypatch.setenv("AUTH_OIDC_REDIRECT_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_DISPLAY_NAME", "Google")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_ISSUER", "https://accounts.example.com")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL", "true")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION", auto_provision)
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE", "auto")

    app = create_app()
    fake_provider = FakeOidcProviderClient()
    provider_client = app.state.injector.get(OidcProviderClientInterface)
    monkeypatch.setattr(provider_client, "build_authorization_url",
                        fake_provider.build_authorization_url)
    monkeypatch.setattr(provider_client, "exchange_code", fake_provider.exchange_code)
    monkeypatch.setattr(provider_client, "validate_id_token", fake_provider.validate_id_token)
    with TestClient(app) as test_client:
        try:
            yield test_client, fake_provider
        finally:
            app.state.injector.get(LoginRateLimiterInterface).reset()


class FakeOidcProviderClient:

    def __init__(self) -> None:
        self.subject = "subject-1"
        self.email = "user@example.com"
        self.email_verified = True
        self.auth_time = utcnow()
        self.validation_error: Exception | None = None
        self.last_nonce_hash: str | None = None

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
        del nonce, code_challenge, prompt, max_age, login_hint
        return OidcAuthorizationUrl(
            provider_id=provider_id,
            url=f"https://idp.example/authorize?state={state}",
        )

    async def exchange_code(
        self,
        provider_id: str,
        code: str,
        code_verifier: str,
    ) -> OidcTokenSetForValidation:
        del provider_id, code, code_verifier
        return OidcTokenSetForValidation(id_token="id-token-value")

    async def validate_id_token(
        self,
        provider_id: str,
        id_token: str,
        *,
        expected_nonce: str | None = None,
        expected_nonce_hash: str | None = None,
        require_auth_time: bool = False,
    ) -> OidcVerifiedClaims:
        del provider_id, id_token, expected_nonce, require_auth_time
        if self.validation_error is not None:
            raise self.validation_error
        self.last_nonce_hash = expected_nonce_hash
        now = utcnow()
        return OidcVerifiedClaims(
            provider_id="google",
            issuer="https://accounts.example.com",
            audience="client-id",
            subject=self.subject,
            email=self.email,
            email_verified=self.email_verified,
            issued_at=now,
            expires_at=now + timedelta(minutes=5),
            auth_time=self.auth_time,
            claims_json={
                "iss": "https://accounts.example.com",
                "sub": self.subject,
                "email": self.email,
                "email_verified": self.email_verified,
            },
        )


def _csrf(client) -> str:
    return client.cookies.get("csrf_token") or client.get("/api/auth/csrf").json()["csrfToken"]


def _start_oidc(client, path: str = "/api/auth/oidc/google/start?redirect=/app"):
    response = client.get(path, follow_redirects=False)
    assert response.status_code == 303
    state = response.headers["location"].split("state=", 1)[1]
    binding_cookie_name = next(key for key in client.cookies if key.startswith("oidc_binding_"))
    return state, binding_cookie_name


def _complete_oidc(client, state: str, code: str = "code-1"):
    return client.get(
        f"/api/auth/oidc/google/callback?state={state}&code={code}",
        follow_redirects=False,
    )


def _cancel_oidc(client, state: str):
    return client.get(
        f"/api/auth/oidc/google/callback?state={state}&error=access_denied",
        follow_redirects=False,
    )


def _start_oidc_reauth(client, path: str = "/api/auth/oidc/google/reauth?redirect=/app/settings"):
    return _start_oidc(client, path)


def test_oidc_callback_auto_provisions_user_and_me_returns_user(oidc_client):
    client, _ = oidc_client
    state, binding_cookie_name = _start_oidc(client)

    callback_response = _complete_oidc(client, state)
    me_response = client.get("/api/auth/me")

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == "/app"
    assert callback_response.cookies.get("session_token")
    assert callback_response.cookies.get("csrf_token")
    assert callback_response.cookies.get(binding_cookie_name) is None
    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user@example.com"


def test_oidc_auto_provision_uses_language_code_from_start_query(oidc_client):
    client, _ = oidc_client
    state, _ = _start_oidc(
        client,
        "/api/auth/oidc/google/start?redirect=/app&languageCode=en",
    )

    callback_response = _complete_oidc(client, state)
    me_response = client.get("/api/auth/me")

    assert callback_response.status_code == 303
    assert me_response.status_code == 200
    assert me_response.json()["languageCode"] == "en"


def test_oidc_invalid_language_code_falls_back_to_default(oidc_client):
    client, _ = oidc_client
    state, _ = _start_oidc(
        client,
        "/api/auth/oidc/google/start?redirect=/app&languageCode=fr",
    )

    callback_response = _complete_oidc(client, state)
    me_response = client.get("/api/auth/me")

    assert callback_response.status_code == 303
    assert me_response.status_code == 200
    assert me_response.json()["languageCode"] == "ja"


@pytest.mark.asyncio
async def test_oidc_start_creates_state_and_is_rate_limited(oidc_client, async_session):
    client, _ = oidc_client

    for _ in range(20):
        response = client.get("/api/auth/oidc/google/start?redirect=/app", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"].startswith("https://idp.example/authorize?state=")
    rate_limited_response = client.get(
        "/api/auth/oidc/google/start?redirect=/app",
        follow_redirects=False,
    )
    state_count = await async_session.scalar(
        text("SELECT count(*) FROM auth_oidc_authorization_states"))

    assert rate_limited_response.status_code == 303
    assert rate_limited_response.headers["location"] == (
        "/login?oidcError=OIDC_AUTHORIZATION_RATE_LIMITED")
    assert state_count == 20
    assert any(key.startswith("oidc_binding_") for key in client.cookies)


@pytest.mark.asyncio
async def test_oidc_verified_email_auto_links_existing_password_user(oidc_client, async_session):
    client, fake_provider = oidc_client
    csrf_token = _csrf(client)
    register_response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert register_response.status_code == 201
    existing_user_id = register_response.json()["id"]
    client.cookies.clear()
    fake_provider.subject = "linked-subject"
    state, _ = _start_oidc(client)

    callback_response = _complete_oidc(client, state)
    identity_rows = (await async_session.execute(
        text("SELECT user_id, provider_subject FROM auth_identities"))).all()

    assert callback_response.status_code == 303
    assert client.get("/api/auth/me").json()["id"] == existing_user_id
    assert [(str(row.user_id), row.provider_subject)
            for row in identity_rows] == [(existing_user_id, "linked-subject")]


def test_oidc_link_preserves_existing_user_language_code(oidc_client):
    client, fake_provider = oidc_client
    csrf_token = _csrf(client)
    register_response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
            "languageCode": "en",
        },
        headers={"X-CSRF-Token": csrf_token},
    )
    assert register_response.status_code == 201
    client.cookies.clear()
    fake_provider.subject = "linked-language-subject"
    state, _ = _start_oidc(
        client,
        "/api/auth/oidc/google/start?redirect=/app&languageCode=ja",
    )

    callback_response = _complete_oidc(client, state)
    me_response = client.get("/api/auth/me")

    assert callback_response.status_code == 303
    assert me_response.status_code == 200
    assert me_response.json()["languageCode"] == "en"


@pytest.mark.asyncio
async def test_oidc_existing_provider_subject_logs_in_without_new_user(
    oidc_client,
    async_session,
):
    client, _ = oidc_client
    state, _ = _start_oidc(client)
    assert _complete_oidc(client, state).status_code == 303
    first_user_id = client.get("/api/auth/me").json()["id"]
    client.cookies.clear()

    state, _ = _start_oidc(client)
    second_callback = _complete_oidc(client, state)
    user_count = await async_session.scalar(text("SELECT count(*) FROM users"))

    assert second_callback.status_code == 303
    assert client.get("/api/auth/me").json()["id"] == first_user_id
    assert user_count == 1


@pytest.mark.asyncio
async def test_oidc_link_only_mode_rejects_new_verified_email_without_session(
    oidc_link_only_client,
    async_session,
):
    client, _ = oidc_link_only_client
    state, _ = _start_oidc(client)

    callback_response = _complete_oidc(client, state)
    user_count = await async_session.scalar(text("SELECT count(*) FROM users"))

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == ("/login?oidcError=OIDC_PROVISIONING_DISABLED")
    assert user_count == 0
    assert client.get("/api/auth/me").status_code == 401


def test_oidc_callback_rejects_missing_browser_binding_without_session(oidc_client):
    client, _ = oidc_client
    state, binding_cookie_name = _start_oidc(client)
    client.cookies.pop(binding_cookie_name)

    callback_response = _complete_oidc(client, state)

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == (
        "/login?oidcError=OIDC_BROWSER_BINDING_MISMATCH")
    assert client.get("/api/auth/me").status_code == 401


def test_oidc_callback_rejects_wrong_browser_binding_without_session(oidc_client):
    client, _ = oidc_client
    state, binding_cookie_name = _start_oidc(client)
    client.cookies.set(binding_cookie_name, "wrong-browser-binding")

    callback_response = _complete_oidc(client, state)

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == (
        "/login?oidcError=OIDC_BROWSER_BINDING_MISMATCH")
    assert client.get("/api/auth/me").status_code == 401


def test_oidc_callback_rejects_state_replay_without_new_session(oidc_client):
    client, _ = oidc_client
    state, binding_cookie_name = _start_oidc(client)
    binding_value = client.cookies.get(binding_cookie_name)
    assert _complete_oidc(client, state).status_code == 303
    client.cookies.clear()
    client.cookies.set(binding_cookie_name, binding_value)

    replay_response = _complete_oidc(client, state)

    assert replay_response.status_code == 303
    assert replay_response.headers["location"] == "/login?oidcError=OIDC_STATE_MISMATCH"
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.asyncio
async def test_oidc_callback_rejects_expired_state_without_session(oidc_client, async_session):
    client, _ = oidc_client
    state, _ = _start_oidc(client)
    await async_session.execute(text("UPDATE auth_oidc_authorization_states SET expires_at = 0"))
    await async_session.commit()

    callback_response = _complete_oidc(client, state)

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == "/login?oidcError=OIDC_STATE_MISMATCH"
    assert client.get("/api/auth/me").status_code == 401


def test_oidc_callback_rejects_unverified_email_without_session(oidc_client):
    client, fake_provider = oidc_client
    fake_provider.email_verified = False
    state, _ = _start_oidc(client)

    callback_response = _complete_oidc(client, state)

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == ("/login?oidcError=OIDC_EMAIL_NOT_VERIFIED")
    assert client.get("/api/auth/me").status_code == 401


@pytest.mark.asyncio
async def test_oidc_callback_failure_does_not_expose_provider_secrets(
    oidc_client,
    async_session,
):
    client, fake_provider = oidc_client
    fake_provider.validation_error = OidcClaimsValidationError(
        "issuer mismatch access_token refresh_token code-1 raw provider error")
    state, _ = _start_oidc(client)

    callback_response = _complete_oidc(client, state, code="code-1")
    audit_text = "\n".join(
        str(row.detail_json) for row in (
            await async_session.execute(text("SELECT detail_json FROM auth_audit_logs"))).all())

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == (
        "/login?oidcError=OIDC_CLAIMS_VALIDATION_FAILED")
    assert client.get("/api/auth/me").status_code == 401
    combined_output = f"{callback_response.headers['location']}\n{audit_text}"
    assert "access_token" not in combined_output
    assert "refresh_token" not in combined_output
    assert "code-1" not in combined_output
    assert "raw provider error" not in combined_output


@pytest.mark.asyncio
async def test_oidc_account_deletion_removes_identity_and_allows_same_subject_again(
    oidc_client,
    async_session,
):
    client, fake_provider = oidc_client
    fake_provider.auth_time = utcnow()
    state, _ = _start_oidc(client)
    assert _complete_oidc(client, state).status_code == 303
    csrf_token = client.cookies.get("csrf_token")

    delete_response = client.request(
        "DELETE",
        "/api/auth/me",
        json={"confirmEmail": "user@example.com"},
        headers={"X-CSRF-Token": csrf_token},
    )
    identity_count_after_delete = await async_session.scalar(
        text("SELECT count(*) FROM auth_identities"))

    client.cookies.clear()
    state, _ = _start_oidc(client)
    second_callback = _complete_oidc(client, state)
    identity_count_after_second_login = await async_session.scalar(
        text("SELECT count(*) FROM auth_identities"))

    assert delete_response.status_code == 204
    assert identity_count_after_delete == 0
    assert second_callback.status_code == 303
    assert identity_count_after_second_login == 1


def test_oidc_reauth_rejects_subject_mismatch_without_replacing_session(oidc_client):
    client, fake_provider = oidc_client
    state, _ = _start_oidc(client)
    assert _complete_oidc(client, state).status_code == 303
    csrf_token = client.cookies.get("csrf_token")
    original_session_token = client.cookies.get("session_token")

    state, _ = _start_oidc_reauth(client)
    fake_provider.subject = "different-subject"
    callback_response = _complete_oidc(client, state)

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == (
        "/app/settings?oidcError=OIDC_REAUTH_SUBJECT_MISMATCH")
    assert callback_response.cookies.get("session_token") is None
    assert client.cookies.get("session_token") == original_session_token
    assert client.cookies.get("csrf_token") == csrf_token
    assert client.get("/api/auth/me").status_code == 200


@pytest.mark.asyncio
async def test_oidc_reauth_provider_cancel_returns_to_settings_and_records_failure(
    oidc_client,
    async_session,
):
    client, _ = oidc_client
    state, binding_cookie_name = _start_oidc(client)
    assert _complete_oidc(client, state).status_code == 303

    state, binding_cookie_name = _start_oidc_reauth(
        client,
        "/api/auth/oidc/google/reauth?redirect=%2Fapp%2Fsettings%3Ftab%3Ddanger%23delete",
    )
    callback_response = _cancel_oidc(client, state)
    audit_count = await async_session.scalar(
        text("SELECT count(*) FROM auth_audit_logs WHERE event_type = 'oidc_reauth_failed'"))
    consumed_count = await async_session.scalar(
        text("SELECT count(*) FROM auth_oidc_authorization_states WHERE consumed_at IS NOT NULL"))

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == (
        "/app/settings?tab=danger&oidcError=OIDC_PROVIDER_ACCESS_DENIED#delete")
    assert callback_response.cookies.get(binding_cookie_name) is None
    assert audit_count == 1
    assert consumed_count == 2


def test_oidc_reauth_rejects_missing_auth_time_and_deletion_stays_blocked(oidc_client):
    client, fake_provider = oidc_client
    fake_provider.auth_time = utcnow() - timedelta(minutes=10)
    state, _ = _start_oidc(client)
    assert _complete_oidc(client, state).status_code == 303

    state, _ = _start_oidc_reauth(client)
    fake_provider.auth_time = None
    callback_response = _complete_oidc(client, state)
    delete_response = client.request(
        "DELETE",
        "/api/auth/me",
        json={"confirmEmail": "user@example.com"},
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == (
        "/app/settings?oidcError=OIDC_REAUTH_AUTH_TIME_REQUIRED")
    assert delete_response.status_code == 400
    assert delete_response.json()["error"]["code"] == "ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED"


def test_oidc_reauth_rejects_provider_auth_time_validation_failure(oidc_client):
    client, fake_provider = oidc_client
    fake_provider.auth_time = utcnow() - timedelta(minutes=10)
    state, _ = _start_oidc(client)
    assert _complete_oidc(client, state).status_code == 303

    state, _ = _start_oidc_reauth(client)
    fake_provider.validation_error = OidcReauthStaleError("future auth_time")
    callback_response = _complete_oidc(client, state)

    assert callback_response.status_code == 303
    assert callback_response.headers["location"] == "/app/settings?oidcError=OIDC_REAUTH_STALE"


def test_delete_me_rejects_stale_oidc_reauth(oidc_client):
    client, fake_provider = oidc_client
    fake_provider.auth_time = utcnow() - timedelta(minutes=10)
    state, _ = _start_oidc(client)
    assert _complete_oidc(client, state).status_code == 303

    response = client.request(
        "DELETE",
        "/api/auth/me",
        json={"confirmEmail": "user@example.com"},
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED"
    assert response.json()["error"]["details"] == [{
        "providerId": "google",
        "displayName": "Google",
    }]
