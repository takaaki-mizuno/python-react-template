import pytest
from starlette.responses import Response

from app.config.auth import AuthSettings
from app.libraries.auth_cookies import (clear_auth_cookie, csrf_cookie_name, session_cookie_name,
                                        set_auth_cookie)


def _cookie_headers(response: Response) -> list[str]:
    return [value.decode() for key, value in response.raw_headers if key.lower() == b"set-cookie"]


def test_session_cookie_name_uses_session_prefix_only():
    assert session_cookie_name(AuthSettings(_env_file=None)) == "session_token"
    assert session_cookie_name(AuthSettings(
        _env_file=None, AUTH_SESSION_COOKIE_PREFIX="__Host-")) == "__Host-session_token"
    assert csrf_cookie_name() == "csrf_token"


def test_set_auth_cookie_preserves_security_attributes():
    response = Response()

    set_auth_cookie(
        response,
        key="session_token",
        value="session-token",
        httponly=True,
        secure=True,
        max_age_seconds=60,
    )

    session_cookie = _cookie_headers(response)[0]
    assert session_cookie.startswith("session_token=session-token")
    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Max-Age=60" in session_cookie


def test_clear_auth_cookie_uses_zero_max_age():
    response = Response()

    clear_auth_cookie(response, key="session_token", httponly=True, secure=True)

    session_cookie = _cookie_headers(response)[0]
    assert session_cookie.startswith("session_token=")
    assert "Max-Age=0" in session_cookie
    assert "HttpOnly" in session_cookie


def test_host_prefixed_session_cookie_requires_secure_path_root_and_no_domain():
    response = Response()

    with pytest.raises(ValueError):
        set_auth_cookie(
            response,
            key="__Host-session_token",
            value="session-token",
            httponly=True,
            secure=False,
            max_age_seconds=60,
        )
