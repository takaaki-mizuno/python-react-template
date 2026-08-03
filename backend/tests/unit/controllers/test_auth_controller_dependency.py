from datetime import timedelta
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.error_handlers import register_error_handlers
from app.config.auth import AuthSettings
from app.controllers import auth_dependencies
from app.controllers.auth_controller import router
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_context import AuthenticatedSessionContext, IssuedAuthSession
from app.models.auth_csrf import SessionCsrfStatus
from app.models.auth_errors import (EmailAlreadyRegisteredError, InvalidCredentialsError,
                                    RateLimitExceededError, WeakPasswordError)
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


def _client_with_stub(usecase: StubAuthUsecase, ) -> TestClient:
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(router, prefix="/api")
    app.dependency_overrides[auth_dependencies.get_auth_usecase] = lambda: usecase
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
