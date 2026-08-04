from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.error_handlers import register_error_handlers
from app.config.auth import AuthSettings
from app.controllers import auth_dependencies
from app.controllers.auth_controller import router
from app.interfaces.usecases.account_deletion_usecase_interface import \
    AccountDeletionUsecaseInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_context import AuthenticatedSessionContext, IssuedAuthSession
from app.models.auth_csrf import SessionCsrfStatus
from app.models.auth_errors import (AccountDeletionConfirmationMismatchError,
                                    AccountDeletionInvalidPasswordError,
                                    AccountDeletionReauthRequiredError, EmailAlreadyRegisteredError,
                                    InvalidCredentialsError, RateLimitExceededError,
                                    WeakPasswordError)
from app.models.auth_session import AuthSession
from app.models.user import User, utcnow


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

    async def issue_csrf_token(self, session_token: str | None = None) -> str:
        self.csrf_issued = True
        assert session_token is None
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
        )

    async def authenticate_session(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ):
        return self.auth_context

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
    return AuthenticatedSessionContext(user=user, session=session)


def _client_with_stub(
    usecase: StubAuthUsecase,
    account_deletion_usecase: StubAccountDeletionUsecase | None = None,
) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[auth_dependencies.get_auth_usecase] = lambda: usecase
    app.dependency_overrides[auth_dependencies.get_account_deletion_usecase] = (
        lambda: account_deletion_usecase or StubAccountDeletionUsecase())
    app.dependency_overrides[auth_dependencies.get_auth_settings] = lambda: AuthSettings(
        _env_file=None, AUTH_COOKIE_SECURE=False)
    return TestClient(app)


def _csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": "csrf-token"}


def _set_csrf_cookie(client: TestClient) -> None:
    client.cookies.set("csrf_token", "csrf-token")


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


def test_get_me_without_authenticated_session_returns_unauthorized_envelope():
    client = _client_with_stub(StubAuthUsecase(auth_context=None))

    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


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
