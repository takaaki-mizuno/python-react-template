from starlette.requests import Request
from starlette.responses import Response

from app.config.auth import AuthSettings
from app.controllers.auth_controller import (is_secure_request,
                                             set_csrf_cookie,
                                             set_session_cookie)


def test_is_secure_request_fails_closed_for_production_without_proxy_headers():
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/csrf",
        "scheme": "http",
        "headers": [],
    })

    assert is_secure_request(
        request,
        AuthSettings(ENVIRONMENT="production"),
    ) is True


def test_is_secure_request_ignores_untrusted_forwarded_proto():
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/csrf",
        "scheme": "http",
        "headers": [(b"x-forwarded-proto", b"https")],
    })

    assert is_secure_request(
        request,
        AuthSettings(ENVIRONMENT="local"),
    ) is False


def test_is_secure_request_accepts_https_in_local_environment():
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/csrf",
        "scheme": "https",
        "server": ("testserver", 443),
        "headers": [],
    })

    assert is_secure_request(
        request,
        AuthSettings(ENVIRONMENT="local"),
    ) is True


def test_issued_auth_cookies_have_required_security_attributes():
    response = Response()
    set_session_cookie(response,
                       "session-token",
                       secure=True,
                       max_age_seconds=60)
    set_csrf_cookie(response, "csrf-token", secure=True, max_age_seconds=60)
    cookie_headers = [
        value.decode() for key, value in response.raw_headers
        if key.lower() == b"set-cookie"
    ]
    session_cookie = next(header for header in cookie_headers
                          if header.startswith("session_token="))
    csrf_cookie = next(header for header in cookie_headers
                       if header.startswith("csrf_token="))

    assert "HttpOnly" in session_cookie
    assert "Secure" in session_cookie
    assert "SameSite=lax" in session_cookie
    assert "Path=/" in session_cookie
    assert "Max-Age=60" in session_cookie
    assert "HttpOnly" not in csrf_cookie
    assert "Secure" in csrf_cookie
    assert "SameSite=lax" in csrf_cookie
    assert "Path=/" in csrf_cookie
    assert "Max-Age=60" in csrf_cookie
