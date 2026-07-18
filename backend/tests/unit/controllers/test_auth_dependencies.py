from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from starlette.requests import Request

from app.controllers import auth_dependencies
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface


def _request_with_csrf_cookie_and_header(
    token: str,
    session_token: str | None = None,
    app=None,
) -> Request:
    cookie = f"csrf_token={token}"
    if session_token:
        cookie = f"{cookie}; session_token={session_token}"
    return Request({
        "type":
        "http",
        "method":
        "POST",
        "path":
        "/api/auth/logout",
        "app":
        app,
        "headers": [
            (b"cookie", cookie.encode()),
            (b"x-csrf-token", token.encode()),
        ],
    })


def test_get_client_ip_ignores_untrusted_forwarded_header():
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "client": ("203.0.113.10", 12345),
        "headers": [(b"x-forwarded-for", b"198.51.100.99")],
    })

    assert auth_dependencies.get_client_ip(request) == "203.0.113.10"


def test_request_metadata_is_normalized_and_bounded():
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "client": ("2001:0db8:0:0:0:0:0:1", 12345),
        "headers": [(b"user-agent", b"a" * 600)],
    })

    assert auth_dependencies.get_client_ip(request) == "2001:db8::1"
    assert auth_dependencies.get_user_agent(request) == "a" * 512


def test_get_client_ip_discards_invalid_asgi_client_address():
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "client": ("not-an-ip", 12345),
        "headers": [],
    })

    assert auth_dependencies.get_client_ip(request) is None


@pytest.mark.asyncio
async def test_require_csrf_uses_timing_safe_compare(monkeypatch):
    compare_digest = Mock(return_value=True)
    monkeypatch.setattr(
        auth_dependencies,
        "secrets",
        SimpleNamespace(compare_digest=compare_digest),
        raising=False,
    )

    await auth_dependencies.require_csrf(
        _request_with_csrf_cookie_and_header("csrf-token"))

    compare_digest.assert_called_once_with("csrf-token", "csrf-token")


@pytest.mark.asyncio
async def test_require_csrf_rejects_session_when_db_bound_token_is_invalid():

    class RejectingUsecase:

        async def validate_session_csrf(
            self,
            session_token: str,
            csrf_token: str,
            ip_address: str | None,
            user_agent: str | None,
        ) -> bool:
            assert session_token == "session-token"
            assert csrf_token == "csrf-token"
            return False

    class InjectorStub:

        def get(self, interface):
            assert interface is AuthUsecaseInterface
            return RejectingUsecase()

    app = SimpleNamespace(state=SimpleNamespace(injector=InjectorStub()))

    with pytest.raises(Exception) as error:
        await auth_dependencies.require_csrf(
            _request_with_csrf_cookie_and_header(
                "csrf-token",
                session_token="session-token",
                app=app,
            ))

    assert error.value.status_code == 403
