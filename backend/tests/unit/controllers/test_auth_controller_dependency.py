from datetime import timedelta
from logging import getLogger
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.error_handlers import register_error_handlers
from app.config.auth import AuthSettings
from app.config.oidc import OidcProviderSettings, OidcSettings
from app.controllers import auth_dependencies
from app.controllers.auth_controller import router
from app.interfaces.usecases.account_deletion_usecase_interface import \
    AccountDeletionUsecaseInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.oauth_oidc_usecase_interface import OAuthOidcUsecaseInterface
from app.libraries.session_tokens import hash_token
from app.models.auth_context import AuthenticatedSessionContext, IssuedAuthSession
from app.models.auth_csrf import SessionCsrfStatus
from app.models.auth_errors import (AccountDeletionConfirmationMismatchError,
                                    AccountDeletionInvalidPasswordError,
                                    AccountDeletionOidcReauthRequiredError,
                                    AccountDeletionReauthRequiredError, EmailAlreadyRegisteredError,
                                    InvalidCredentialsError, RateLimitExceededError,
                                    WeakPasswordError)
from app.models.auth_session import AuthSession
from app.models.oidc import OidcAuthorizationStartResult, OidcCallbackResult
from app.models.oidc_errors import (OidcAuthorizationRateLimitedError,
                                    OidcProviderAccessDeniedError, OidcProviderMetadataError,
                                    OidcProviderUnavailableError, OidcReauthStaleError)
from app.models.user import AuthUserUpdateChanges, User, utcnow


class StubAuthUsecase(AuthUsecaseInterface):

    def __init__(
        self,
        auth_error: Exception | None = None,
        auth_context: AuthenticatedSessionContext | None = None,
    ) -> None:
        self.auth_error = auth_error
        self.auth_context = auth_context
        self.csrf_issued = False
        self.login_called = False
        self.register_called = False
        self.logout_called = False
        self.csrf_session_tokens: list[str | None] = []
        self.updated_changes: AuthUserUpdateChanges | None = None

    async def issue_csrf_token(self, session_token: str | None = None) -> str:
        self.csrf_issued = True
        self.csrf_session_tokens.append(session_token)
        return "issued-csrf-token"

    async def validate_session_csrf(
        self,
        session_token: str,
        csrf_token: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SessionCsrfStatus:
        assert session_token == "session-token"
        assert csrf_token == "csrf-token"
        return SessionCsrfStatus.VALID

    async def register(
        self,
        email: str,
        password: str,
        language_code: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ):
        self.register_called = True
        if self.auth_error is not None:
            raise self.auth_error
        user = User(
            id=uuid4(),
            email=email,
            password_hash="hash",
            language_code=language_code,
        )
        session = AuthSession(
            user_id=user.id,
            session_token_hash="session-token-hash",
            csrf_token_hash="csrf-token-hash",
            created_at=utcnow(),
            last_seen_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=10),
        )
        return IssuedAuthSession(
            user=user,
            session=session,
            session_token="new-session-token",
            csrf_token="new-csrf-token",
            roles=frozenset(),
            permissions=frozenset(),
        )

    async def login(
        self,
        email: str,
        password: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ):
        self.login_called = True
        if self.auth_error is not None:
            raise self.auth_error
        assert email == "user@example.com"
        assert current_session_token == "session-token"
        user = User(
            id=uuid4(),
            email=email,
            password_hash="hash",
            language_code="ja",
        )
        session = AuthSession(
            user_id=user.id,
            session_token_hash="session-token-hash",
            csrf_token_hash="csrf-token-hash",
            created_at=utcnow(),
            last_seen_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=10),
        )
        return IssuedAuthSession(
            user=user,
            session=session,
            session_token="new-session-token",
            csrf_token="new-csrf-token",
            roles=frozenset({"admin"}),
            permissions=frozenset({"admin:access"}),
        )

    async def authenticate_session(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ):
        return self.auth_context

    async def update_current_user(
        self,
        auth_context: AuthenticatedSessionContext,
        changes: AuthUserUpdateChanges,
    ) -> AuthenticatedSessionContext:
        self.updated_changes = changes
        auth_context.user.language_code = changes.language_code or auth_context.user.language_code
        return auth_context

    async def logout(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.logout_called = True
        assert session_token == "session-token"


class StubAccountDeletionUsecase(AccountDeletionUsecaseInterface):

    def __init__(self, error: Exception | None = None) -> None:
        self.error = error
        self.delete_account_called = False
        self.deleted_auth_context: AuthenticatedSessionContext | None = None
        self.deleted_confirm_email: str | None = None
        self.deleted_password: str | None = None
        self.deleted_ip_address: str | None = None
        self.deleted_user_agent: str | None = None

    async def delete_account(
        self,
        auth_context: AuthenticatedSessionContext,
        confirm_email: str,
        password: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.delete_account_called = True
        self.deleted_auth_context = auth_context
        self.deleted_confirm_email = confirm_email
        self.deleted_password = password
        self.deleted_ip_address = ip_address
        self.deleted_user_agent = user_agent
        if self.error is not None:
            raise self.error


class StubOAuthOidcUsecase(OAuthOidcUsecaseInterface):

    def __init__(
        self,
        callback_error: Exception | None = None,
        start_error: Exception | None = None,
    ) -> None:
        self.callback_error = callback_error
        self.start_error = start_error
        self.start_calls: list[dict] = []
        self.callback_calls: list[dict] = []
        self.error_callback_calls: list[dict] = []
        self.callback_result: OidcCallbackResult | None = None

    async def start_authorization(
        self,
        provider_id: str,
        redirect_path: str | None,
        purpose,
        current_session: AuthenticatedSessionContext | None,
        ip_address: str | None,
        language_code=None,
    ) -> OidcAuthorizationStartResult:
        self.start_calls.append({
            "provider_id": provider_id,
            "redirect_path": redirect_path,
            "purpose": purpose,
            "current_session": current_session,
            "ip_address": ip_address,
            "language_code": language_code,
        })
        if self.start_error is not None:
            raise self.start_error
        return OidcAuthorizationStartResult(
            provider_id=provider_id,
            authorization_url=f"https://idp.example/{provider_id}/authorize",
            browser_binding_cookie_name="oidc_binding_test",
            browser_binding_cookie_value="browser-binding-value",
            browser_binding_cookie_max_age=300,
        )

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
        self.callback_calls.append({
            "provider_id": provider_id,
            "state": state,
            "code": code,
            "browser_binding_cookie_value": browser_binding_cookie_value,
            "current_session": current_session,
            "current_session_token": current_session_token,
            "ip_address": ip_address,
            "user_agent": user_agent,
        })
        if self.callback_error is not None:
            raise self.callback_error
        if self.callback_result is not None:
            return self.callback_result
        user = User(id=uuid4(), email="oidc@example.com", password_hash=None)
        session = AuthSession(
            user_id=user.id,
            session_token_hash="session-token-hash",
            csrf_token_hash="csrf-token-hash",
            created_at=utcnow(),
            last_seen_at=utcnow(),
            expires_at=utcnow() + timedelta(minutes=10),
        )
        return OidcCallbackResult(
            redirect_path="/app",
            issued_session=IssuedAuthSession(
                user=user,
                session=session,
                session_token="oidc-session-token",
                csrf_token="oidc-csrf-token",
                roles=frozenset(),
                permissions=frozenset(),
            ),
        )

    async def complete_error_callback(
        self,
        provider_id: str,
        state: str,
        browser_binding_cookie_value: str | None,
        provider_error: Exception,
        current_session: AuthenticatedSessionContext | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        self.error_callback_calls.append({
            "provider_id": provider_id,
            "state": state,
            "browser_binding_cookie_value": browser_binding_cookie_value,
            "provider_error": provider_error,
            "current_session": current_session,
            "ip_address": ip_address,
            "user_agent": user_agent,
        })
        if self.callback_error is not None:
            raise self.callback_error
        raise provider_error


class LoggerStub:

    def __init__(self) -> None:
        self.exceptions: list[tuple[str, dict]] = []
        self.infos: list[tuple[str, dict]] = []

    def exception(self, message: str, **kwargs) -> None:
        self.exceptions.append((message, kwargs))

    def info(self, message: str, **kwargs) -> None:
        self.infos.append((message, kwargs))


def _authenticated_context(email: str = "user@example.com") -> AuthenticatedSessionContext:
    user = User(
        id=uuid4(),
        email=email,
        password_hash="hash",
    )
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset(),
        permissions=frozenset(),
    )


def _client_with_stub(
    usecase: StubAuthUsecase,
    account_deletion_usecase: StubAccountDeletionUsecase | None = None,
    oauth_oidc_usecase: StubOAuthOidcUsecase | None = None,
) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[auth_dependencies.get_auth_usecase] = lambda: usecase
    app.dependency_overrides[auth_dependencies.get_account_deletion_usecase] = (
        lambda: account_deletion_usecase or StubAccountDeletionUsecase())
    app.dependency_overrides[auth_dependencies.get_oauth_oidc_usecase] = (
        lambda: oauth_oidc_usecase or StubOAuthOidcUsecase())
    app.dependency_overrides[auth_dependencies.get_oidc_settings] = lambda: OidcSettings(
        providers=(OidcProviderSettings(
            provider_id="google",
            display_name="Google",
            issuer="https://accounts.example.com",
            client_id="client-id",
            client_secret="client-secret",
            callback_path="/api/auth/oidc/google/callback",
        ), ),
        AUTH_OIDC_REDIRECT_BASE_URL="https://app.example.com",
    )
    app.dependency_overrides[auth_dependencies.get_auth_settings] = lambda: AuthSettings(
        _env_file=None, AUTH_COOKIE_SECURE=False)
    app.dependency_overrides[auth_dependencies.get_logger] = lambda: getLogger("test")
    return TestClient(app)


def _csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": "csrf-token"}


def _set_csrf_cookie(client: TestClient) -> None:
    client.cookies.set("csrf_token", "csrf-token")


def _oidc_binding_cookie_name(state: str) -> str:
    return f"oidc_binding_{hash_token(state)[:16]}"


def test_get_csrf_uses_overridden_usecase_and_sets_cookie():
    usecase = StubAuthUsecase()
    client = _client_with_stub(usecase)

    response = client.get("/api/auth/csrf")

    assert response.status_code == 200
    assert response.json() == {"csrfToken": "issued-csrf-token"}
    assert response.cookies.get("csrf_token") == "issued-csrf-token"
    assert usecase.csrf_issued is True


def test_login_uses_overridden_usecase():
    usecase = StubAuthUsecase()
    client = _client_with_stub(usecase)
    _set_csrf_cookie(client)
    client.cookies.set("session_token", "session-token")

    response = client.post(
        "/api/auth/login",
        json={
            "email": "user@example.com",
            "password": "correct-password",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 200
    assert response.json()["email"] == "user@example.com"
    assert response.cookies.get("session_token") == "new-session-token"
    assert response.cookies.get("csrf_token") == "new-csrf-token"
    assert usecase.login_called is True


def test_logout_uses_overridden_usecase():
    usecase = StubAuthUsecase()
    client = _client_with_stub(usecase)
    _set_csrf_cookie(client)
    client.cookies.set("session_token", "session-token")

    response = client.post(
        "/api/auth/logout",
        headers=_csrf_headers(),
    )

    assert response.status_code == 204
    assert usecase.logout_called is True


def test_delete_me_uses_account_deletion_usecase_and_clears_cookies():
    auth_context = _authenticated_context()
    auth_usecase = StubAuthUsecase(auth_context=auth_context)
    account_deletion_usecase = StubAccountDeletionUsecase()
    client = _client_with_stub(auth_usecase, account_deletion_usecase)
    _set_csrf_cookie(client)
    client.cookies.set("session_token", "session-token")

    response = client.request(
        "DELETE",
        "/api/auth/me",
        json={
            "confirmEmail": "user@example.com",
            "password": "Password123!",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 204
    assert account_deletion_usecase.delete_account_called is True
    assert account_deletion_usecase.deleted_auth_context is auth_context
    assert account_deletion_usecase.deleted_confirm_email == "user@example.com"
    assert account_deletion_usecase.deleted_password == "Password123!"
    assert account_deletion_usecase.deleted_user_agent == "testclient"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith("session_token=") and "Max-Age=0" in header
        for header in set_cookie_headers)
    assert any(
        header.startswith("csrf_token=") and "Max-Age=0" in header for header in set_cookie_headers)


def test_delete_me_confirmation_mismatch_returns_error_without_clearing_cookies():
    account_deletion_usecase = StubAccountDeletionUsecase(
        AccountDeletionConfirmationMismatchError())
    client = _client_with_stub(
        StubAuthUsecase(auth_context=_authenticated_context()),
        account_deletion_usecase,
    )
    _set_csrf_cookie(client)
    client.cookies.set("session_token", "session-token")

    response = client.request(
        "DELETE",
        "/api/auth/me",
        json={"confirmEmail": "other@example.com"},
        headers=_csrf_headers(),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "ACCOUNT_DELETION_CONFIRMATION_MISMATCH"
    assert response.headers.get_list("set-cookie") == []


def test_delete_me_password_reauth_errors_return_400_envelopes():
    for error, code in [
        (AccountDeletionReauthRequiredError(), "ACCOUNT_DELETION_REAUTH_REQUIRED"),
        (AccountDeletionInvalidPasswordError(), "ACCOUNT_DELETION_INVALID_PASSWORD"),
    ]:
        account_deletion_usecase = StubAccountDeletionUsecase(error)
        client = _client_with_stub(
            StubAuthUsecase(auth_context=_authenticated_context()),
            account_deletion_usecase,
        )
        _set_csrf_cookie(client)
        client.cookies.set("session_token", "session-token")

        response = client.request(
            "DELETE",
            "/api/auth/me",
            json={
                "confirmEmail": "user@example.com",
                "password": "Password123!",
            },
            headers=_csrf_headers(),
        )

        assert response.status_code == 400
        assert response.json()["error"]["code"] == code


def test_delete_me_oidc_reauth_required_returns_provider_details():
    account_deletion_usecase = StubAccountDeletionUsecase(
        AccountDeletionOidcReauthRequiredError([{
            "providerId": "google",
            "displayName": "Google",
        }]))
    client = _client_with_stub(
        StubAuthUsecase(auth_context=_authenticated_context()),
        account_deletion_usecase,
    )
    _set_csrf_cookie(client)
    client.cookies.set("session_token", "session-token")

    response = client.request(
        "DELETE",
        "/api/auth/me",
        json={"confirmEmail": "user@example.com"},
        headers=_csrf_headers(),
    )

    assert response.status_code == 400
    assert response.json()["error"] == {
        "code": "ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED",
        "message": "OIDC reauthentication is required",
        "details": [{
            "providerId": "google",
            "displayName": "Google",
        }],
    }


def test_delete_me_rate_limit_returns_retry_after_header():
    account_deletion_usecase = StubAccountDeletionUsecase(RateLimitExceededError(3600))
    client = _client_with_stub(
        StubAuthUsecase(auth_context=_authenticated_context()),
        account_deletion_usecase,
    )
    _set_csrf_cookie(client)
    client.cookies.set("session_token", "session-token")

    response = client.request(
        "DELETE",
        "/api/auth/me",
        json={
            "confirmEmail": "user@example.com",
            "password": "Password123!",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"
    assert response.json()["error"]["code"] == "ACCOUNT_DELETION_REAUTH_RATE_LIMITED"


def test_delete_me_without_authenticated_session_returns_unauthorized_before_delete():
    account_deletion_usecase = StubAccountDeletionUsecase()
    client = _client_with_stub(StubAuthUsecase(auth_context=None), account_deletion_usecase)
    _set_csrf_cookie(client)
    client.cookies.set("session_token", "session-token")

    response = client.request(
        "DELETE",
        "/api/auth/me",
        json={"confirmEmail": "user@example.com"},
        headers=_csrf_headers(),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"
    assert account_deletion_usecase.delete_account_called is False


def test_delete_me_openapi_contract():
    client = _client_with_stub(StubAuthUsecase())

    delete_operation = client.app.openapi()["paths"]["/api/auth/me"]["delete"]

    assert "auth" in delete_operation["tags"]
    assert "AccountDeletionRequest" in str(delete_operation["requestBody"]["content"])
    assert set(delete_operation["responses"]) == {"204", "400", "401", "403", "422", "429"}


def test_oidc_providers_returns_public_provider_metadata_only():
    client = _client_with_stub(StubAuthUsecase())

    response = client.get("/api/auth/oidc/providers")

    assert response.status_code == 200
    assert response.json() == {
        "providers": [{
            "providerId": "google",
            "displayName": "Google",
        }]
    }
    assert "client-secret" not in response.text
    assert "accounts.example.com" not in response.text


def test_oidc_start_redirects_to_provider_and_sets_browser_binding_cookie():
    oidc_usecase = StubOAuthOidcUsecase()
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)

    response = client.get(
        "/api/auth/oidc/google/start?redirect=/app&languageCode=en",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "https://idp.example/google/authorize"
    assert oidc_usecase.start_calls[0]["purpose"] == "login"
    assert oidc_usecase.start_calls[0]["redirect_path"] == "/app"
    assert oidc_usecase.start_calls[0]["language_code"] == "en"
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith("oidc_binding_test=browser-binding-value")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Max-Age=300" in set_cookie


def test_oidc_start_invalid_language_falls_back_to_default_language():
    oidc_usecase = StubOAuthOidcUsecase()
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)

    response = client.get(
        "/api/auth/oidc/google/start?languageCode=fr",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert oidc_usecase.start_calls[0]["language_code"] == "ja"


def test_oidc_start_rate_limit_redirects_to_login_error():
    oidc_usecase = StubOAuthOidcUsecase(start_error=OidcAuthorizationRateLimitedError())
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)

    response = client.get(
        "/api/auth/oidc/google/start?redirect=/app",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == ("/login?oidcError=OIDC_AUTHORIZATION_RATE_LIMITED")


def test_oidc_start_provider_unavailable_redirects_to_login_error():
    oidc_usecase = StubOAuthOidcUsecase(start_error=OidcProviderUnavailableError("idp down"))
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)

    response = client.get(
        "/api/auth/oidc/google/start?redirect=/app",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?oidcError=OIDC_PROVIDER_UNAVAILABLE"


def test_oidc_start_metadata_error_redirects_to_login_error():
    oidc_usecase = StubOAuthOidcUsecase(start_error=OidcProviderMetadataError("bad metadata"))
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)

    response = client.get(
        "/api/auth/oidc/google/start?redirect=/app",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?oidcError=OIDC_PROVIDER_METADATA_INVALID"


def test_oidc_reauth_requires_session_and_starts_reauth_flow():
    auth_context = _authenticated_context()
    oidc_usecase = StubOAuthOidcUsecase()
    client = _client_with_stub(
        StubAuthUsecase(auth_context=auth_context),
        oauth_oidc_usecase=oidc_usecase,
    )
    client.cookies.set("session_token", "session-token")

    response = client.get(
        "/api/auth/oidc/google/reauth?redirect=/app/settings",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert oidc_usecase.start_calls[0]["purpose"] == "account_deletion_reauth"
    assert oidc_usecase.start_calls[0]["current_session"] is auth_context


def test_oidc_reauth_rate_limit_redirects_to_settings_error():
    auth_context = _authenticated_context()
    oidc_usecase = StubOAuthOidcUsecase(start_error=OidcAuthorizationRateLimitedError())
    client = _client_with_stub(
        StubAuthUsecase(auth_context=auth_context),
        oauth_oidc_usecase=oidc_usecase,
    )
    client.cookies.set("session_token", "session-token")

    response = client.get(
        "/api/auth/oidc/google/reauth?redirect=/app/settings",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/app/settings?oidcError=OIDC_AUTHORIZATION_RATE_LIMITED")


def test_oidc_reauth_without_session_redirects_to_login_instead_of_json():
    client = _client_with_stub(StubAuthUsecase(auth_context=None))

    response = client.get(
        "/api/auth/oidc/google/reauth?redirect=/app/settings",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == ("/login?oidcError=OIDC_REAUTH_AUTHENTICATION_REQUIRED")
    assert "application/json" not in response.headers.get("content-type", "")


def test_oidc_reauth_provider_unavailable_redirects_to_settings_error():
    auth_context = _authenticated_context()
    oidc_usecase = StubOAuthOidcUsecase(start_error=OidcProviderUnavailableError("idp down"))
    client = _client_with_stub(
        StubAuthUsecase(auth_context=auth_context),
        oauth_oidc_usecase=oidc_usecase,
    )
    client.cookies.set("session_token", "session-token")

    response = client.get(
        "/api/auth/oidc/google/reauth?redirect=/app/settings",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == ("/app/settings?oidcError=OIDC_PROVIDER_UNAVAILABLE")


def test_oidc_callback_provider_error_redirects_and_clears_binding_cookie():
    client = _client_with_stub(StubAuthUsecase())
    logger = LoggerStub()
    client.app.dependency_overrides[auth_dependencies.get_logger] = lambda: logger
    client.cookies.set(_oidc_binding_cookie_name("test"), "browser-binding-value")

    response = client.get(
        "/api/auth/oidc/google/callback?state=test&error=access_denied"
        "&error_description=user+denied",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?oidcError=OIDC_PROVIDER_ACCESS_DENIED"
    assert "user+denied" not in response.headers["location"]
    assert "user denied" not in response.headers["location"]
    assert logger.infos == [(
        "OIDC provider returned callback error",
        {
            "extra": {
                "provider_id": "google",
                "oidc_error": "access_denied",
                "oidc_error_description": "user denied",
            }
        },
    )]
    assert "application/json" not in response.headers.get("content-type", "")
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith(f"{_oidc_binding_cookie_name('test')}=") and "Max-Age=0" in header
        for header in set_cookie_headers)


def test_oidc_callback_provider_error_for_reauth_merges_settings_error_and_clears_cookie():
    auth_context = _authenticated_context()
    from app.models.oidc_errors import OidcCallbackFlowError

    oidc_usecase = StubOAuthOidcUsecase(callback_error=OidcCallbackFlowError(
        OidcProviderAccessDeniedError("access_denied"),
        purpose="account_deletion_reauth",
        redirect_path="/app/settings?tab=danger#delete",
    ))
    client = _client_with_stub(
        StubAuthUsecase(auth_context=auth_context),
        oauth_oidc_usecase=oidc_usecase,
    )
    client.cookies.set("session_token", "session-token")
    client.cookies.set(_oidc_binding_cookie_name("test"), "browser-binding-value")

    response = client.get(
        "/api/auth/oidc/google/callback?state=test&error=access_denied",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == (
        "/app/settings?tab=danger&oidcError=OIDC_PROVIDER_ACCESS_DENIED#delete")
    assert isinstance(
        oidc_usecase.error_callback_calls[0]["provider_error"],
        OidcProviderAccessDeniedError,
    )
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith(f"{_oidc_binding_cookie_name('test')}=") and "Max-Age=0" in header
        for header in set_cookie_headers)


def test_oidc_callback_login_success_sets_session_and_clears_binding_cookie():
    oidc_usecase = StubOAuthOidcUsecase()
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)
    client.cookies.set(_oidc_binding_cookie_name("test"), "browser-binding-value")

    response = client.get(
        "/api/auth/oidc/google/callback?state=test&code=code-1",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/app"
    assert oidc_usecase.callback_calls[0]["browser_binding_cookie_value"] == (
        "browser-binding-value")
    assert response.cookies.get("session_token") == "oidc-session-token"
    assert response.cookies.get("csrf_token") == "oidc-csrf-token"
    set_cookie_headers = response.headers.get_list("set-cookie")
    assert any(
        header.startswith(f"{_oidc_binding_cookie_name('test')}=") and "Max-Age=0" in header
        for header in set_cookie_headers)


def test_oidc_callback_reauth_success_keeps_session_and_merges_success_query():
    auth_context = _authenticated_context()
    oidc_usecase = StubOAuthOidcUsecase()
    oidc_usecase.callback_result = OidcCallbackResult(
        redirect_path="/app/settings?tab=danger#delete",
        issued_session=None,
        reauthenticated_context=auth_context,
    )
    auth_usecase = StubAuthUsecase(auth_context=auth_context)
    client = _client_with_stub(auth_usecase, oauth_oidc_usecase=oidc_usecase)
    client.cookies.set("session_token", "session-token")
    client.cookies.set(_oidc_binding_cookie_name("test"), "browser-binding-value")

    response = client.get(
        "/api/auth/oidc/google/callback?state=test&code=code-1",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/app/settings?tab=danger&oidcReauth=success#delete"
    assert response.cookies.get("session_token") is None
    assert response.cookies.get("csrf_token") == "issued-csrf-token"
    assert auth_usecase.csrf_issued is True
    assert auth_usecase.csrf_session_tokens == ["session-token"]


def test_oidc_callback_reauth_failure_merges_error_query_without_raw_error():
    error = OidcReauthStaleError("raw provider text")
    from app.models.oidc_errors import OidcCallbackFlowError

    callback_error = OidcCallbackFlowError(
        error,
        purpose="account_deletion_reauth",
        redirect_path="/app/settings?tab=danger#delete",
    )
    oidc_usecase = StubOAuthOidcUsecase(callback_error=callback_error)
    client = _client_with_stub(
        StubAuthUsecase(auth_context=_authenticated_context()),
        oauth_oidc_usecase=oidc_usecase,
    )
    client.cookies.set("session_token", "session-token")
    client.cookies.set(_oidc_binding_cookie_name("test"), "browser-binding-value")

    response = client.get(
        "/api/auth/oidc/google/callback?state=test&code=secret-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers[
        "location"] == "/app/settings?tab=danger&oidcError=OIDC_REAUTH_STALE#delete"
    assert "secret-code" not in response.headers["location"]
    assert "raw provider text" not in response.headers["location"]


def test_oidc_callback_login_failure_redirects_to_login_error():
    oidc_usecase = StubOAuthOidcUsecase(callback_error=OidcReauthStaleError())
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)
    client.cookies.set(_oidc_binding_cookie_name("test"), "browser-binding-value")

    response = client.get(
        "/api/auth/oidc/google/callback?state=test&code=secret-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?oidcError=OIDC_REAUTH_STALE"


def test_oidc_callback_unknown_exception_is_logged_and_redirected():
    oidc_usecase = StubOAuthOidcUsecase(callback_error=RuntimeError("db unavailable"))
    logger = LoggerStub()
    client = _client_with_stub(StubAuthUsecase(), oauth_oidc_usecase=oidc_usecase)
    client.app.dependency_overrides[auth_dependencies.get_logger] = lambda: logger
    client.cookies.set(_oidc_binding_cookie_name("test"), "browser-binding-value")

    response = client.get(
        "/api/auth/oidc/google/callback?state=test&code=secret-code",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login?oidcError=OIDC_UNEXPECTED_ERROR"
    assert logger.exceptions
    assert logger.exceptions[0][0] == "Unexpected OIDC callback failure"


def test_oidc_error_code_mapping_table():
    from app.controllers.auth_controller import oidc_error_code_for_exception

    assert oidc_error_code_for_exception(OidcReauthStaleError()) == "OIDC_REAUTH_STALE"


def test_get_me_without_authenticated_session_returns_unauthorized_envelope():
    client = _client_with_stub(StubAuthUsecase(auth_context=None))

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_get_me_returns_language_code():
    auth_context = _authenticated_context()
    auth_context.user.language_code = "en"
    client = _client_with_stub(StubAuthUsecase(auth_context=auth_context))

    response = client.get("/api/auth/me")

    assert response.status_code == 200
    assert response.json()["languageCode"] == "en"


def test_patch_me_updates_language_with_fields_set():
    auth_context = _authenticated_context()
    usecase = StubAuthUsecase(auth_context=auth_context)
    client = _client_with_stub(usecase)
    _set_csrf_cookie(client)

    response = client.patch(
        "/api/auth/me",
        json={"languageCode": "en"},
        headers=_csrf_headers(),
    )

    assert response.status_code == 200
    assert response.json()["languageCode"] == "en"
    assert usecase.updated_changes == AuthUserUpdateChanges(
        language_code="en",
        fields_set=frozenset({"language_code"}),
    )


def test_register_duplicate_email_returns_error_envelope():
    client = _client_with_stub(StubAuthUsecase(EmailAlreadyRegisteredError()))
    _set_csrf_cookie(client)

    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_REGISTERED"


def test_register_rate_limit_preserves_retry_after_header():
    client = _client_with_stub(StubAuthUsecase(RateLimitExceededError()))
    _set_csrf_cookie(client)

    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"
    assert response.json()["error"]["code"] == "REGISTER_RATE_LIMITED"


def test_register_rate_limit_uses_error_retry_after_when_present():
    client = _client_with_stub(StubAuthUsecase(RateLimitExceededError(3600)))
    _set_csrf_cookie(client)

    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "3600"


def test_register_weak_password_returns_error_envelope():
    client = _client_with_stub(StubAuthUsecase(WeakPasswordError("Too weak")))
    _set_csrf_cookie(client)

    response = client.post(
        "/api/auth/register",
        json={
            "email": "user@example.com",
            "password": "Password123!",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "WEAK_PASSWORD"


def test_login_invalid_credentials_returns_error_envelope():
    client = _client_with_stub(StubAuthUsecase(InvalidCredentialsError()))
    _set_csrf_cookie(client)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "user@example.com",
            "password": "wrong-password",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_login_rate_limit_preserves_retry_after_header():
    client = _client_with_stub(StubAuthUsecase(RateLimitExceededError()))
    _set_csrf_cookie(client)

    response = client.post(
        "/api/auth/login",
        json={
            "email": "user@example.com",
            "password": "wrong-password",
        },
        headers=_csrf_headers(),
    )

    assert response.status_code == 429
    assert response.headers["Retry-After"] == "900"
    assert response.json()["error"]["code"] == "LOGIN_RATE_LIMITED"
