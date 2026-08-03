import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.csrf import CSRFMiddleware
from app.config.auth import AuthSettings
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_csrf import SessionCsrfStatus


class StubUsecase:

    def __init__(self, csrf_status=SessionCsrfStatus.VALID) -> None:
        self.csrf_status = csrf_status
        self.calls = []

    async def validate_session_csrf(
        self,
        session_token: str,
        csrf_token: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SessionCsrfStatus:
        self.calls.append((session_token, csrf_token, ip_address, user_agent))
        if isinstance(self.csrf_status, Exception):
            raise self.csrf_status
        return self.csrf_status


class InjectorStub:

    def __init__(self, settings: AuthSettings, usecase: StubUsecase) -> None:
        self._settings = settings
        self._usecase = usecase

    def get(self, interface):
        if interface is AuthSettings:
            return self._settings
        if interface is AuthUsecaseInterface:
            return self._usecase
        raise AssertionError(f"Unexpected interface: {interface}")


def _client(
    usecase: StubUsecase | None = None,
    settings: AuthSettings | None = None,
    root_path: str = "",
) -> TestClient:
    app = FastAPI(root_path=root_path)
    app.state.injector = InjectorStub(settings or AuthSettings(_env_file=None), usecase
                                      or StubUsecase())
    app.add_middleware(CSRFMiddleware)

    @app.get("/api/protected")
    async def get_protected():
        return {"ok": True}

    @app.post("/api/protected")
    async def post_protected():
        return {"ok": True}

    @app.post("/api/exempt")
    async def post_exempt():
        return {"ok": True}

    @app.post("/outside")
    async def outside():
        return {"ok": True}

    return TestClient(app, root_path=root_path)


def test_post_api_requires_csrf_cookie_and_header():
    response = _client().post("/api/protected")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


def test_post_api_requires_csrf_under_root_path():
    response = _client(root_path="/backend").post("/backend/api/protected")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CSRF_VALIDATION_FAILED"


@pytest.mark.asyncio
async def test_post_api_requires_csrf_for_prefixed_asgi_scope():

    async def downstream_app(_scope, _receive, _send):
        raise AssertionError("CSRF middleware should reject before routing")

    app = FastAPI(root_path="/backend")
    app.state.injector = InjectorStub(AuthSettings(_env_file=None), StubUsecase())
    middleware = CSRFMiddleware(downstream_app)
    messages = []
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/backend/api/protected",
        "root_path": "/backend",
        "headers": [],
        "app": app,
        "client": ("127.0.0.1", 12345),
        "server": ("testserver", 80),
        "scheme": "http",
        "query_string": b"",
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await middleware(scope, receive, send)

    assert messages[0]["type"] == "http.response.start"
    assert messages[0]["status"] == 403


@pytest.mark.parametrize("method", ["put", "patch", "delete"])
def test_all_unsafe_api_methods_require_csrf(method):
    response = getattr(_client(), method)("/api/protected")

    assert response.status_code == 403


def test_csrf_compare_uses_bytes(monkeypatch):
    calls = []

    def compare_digest(left, right):
        calls.append((left, right))
        return True

    monkeypatch.setattr("app.bootstrap.csrf.secrets.compare_digest", compare_digest)
    client = _client()
    client.cookies.set("csrf_token", "csrf-token")

    response = client.post("/api/protected", headers={"X-CSRF-Token": "csrf-token"})

    assert response.status_code == 200
    assert calls == [(b"csrf-token", b"csrf-token")]


def test_non_ascii_csrf_mismatch_returns_403_not_500():
    client = _client()
    client.cookies.set("csrf_token", "cafe")

    response = client.post("/api/protected", headers={"X-CSRF-Token": "caf\u00e9".encode()})

    assert response.status_code == 403


def test_post_api_rejects_mismatched_csrf_tokens():
    client = _client()
    client.cookies.set("csrf_token", "cookie-token")

    response = client.post("/api/protected", headers={"X-CSRF-Token": "header-token"})

    assert response.status_code == 403


def test_post_api_accepts_matching_double_submit_without_session():
    client = _client()
    client.cookies.set("csrf_token", "csrf-token")

    response = client.post("/api/protected", headers={"X-CSRF-Token": "csrf-token"})

    assert response.status_code == 200


def test_post_api_rejects_session_csrf_mismatch():
    client = _client(StubUsecase(SessionCsrfStatus.MISMATCH))
    client.cookies.set("csrf_token", "csrf-token")
    client.cookies.set("session_token", "session-token")

    response = client.post("/api/protected", headers={"X-CSRF-Token": "csrf-token"})

    assert response.status_code == 403


def test_post_api_accepts_valid_session_csrf():
    client = _client(StubUsecase(SessionCsrfStatus.VALID))
    client.cookies.set("csrf_token", "csrf-token")
    client.cookies.set("session_token", "session-token")

    response = client.post("/api/protected", headers={"X-CSRF-Token": "csrf-token"})

    assert response.status_code == 200


def test_get_api_skips_csrf_validation():
    assert _client().get("/api/protected").status_code == 200


def test_non_api_path_skips_csrf_validation():
    assert _client().post("/outside").status_code == 200


def test_explicit_exempt_path_skips_csrf_validation():
    client = _client(settings=AuthSettings(_env_file=None, AUTH_CSRF_EXEMPT_PATHS="/api/exempt"))

    assert client.post("/api/exempt").status_code == 200


def test_middleware_returns_error_envelope_for_unexpected_exception():
    client = _client(StubUsecase(RuntimeError("boom")))
    client.cookies.set("csrf_token", "csrf-token")
    client.cookies.set("session_token", "session-token")

    response = client.post("/api/protected", headers={"X-CSRF-Token": "csrf-token"})

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_SERVER_ERROR"


def test_unknown_unsafe_api_path_is_rejected_before_routing():
    response = _client().post("/api/unknown")

    assert response.status_code == 403
