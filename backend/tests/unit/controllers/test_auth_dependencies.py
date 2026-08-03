from types import SimpleNamespace

from starlette.requests import Request

from app.config.auth import AuthSettings
from app.controllers import auth_dependencies


def test_get_client_ip_ignores_untrusted_forwarded_header():
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "client": ("203.0.113.10", 12345),
        "headers": [(b"x-forwarded-for", b"198.51.100.99")],
    })

    assert auth_dependencies.get_client_ip(request) == "203.0.113.10"


def test_get_client_ip_uses_trusted_forwarded_header():
    request = Request({
        "type": "http",
        "method": "POST",
        "path": "/api/auth/login",
        "client": ("10.0.0.10", 12345),
        "headers": [(b"x-forwarded-for", b"198.51.100.99")],
    })

    assert auth_dependencies.get_client_ip(request, "10.0.0.0/8") == "198.51.100.99"


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


def test_get_auth_settings_alias_returns_injector_instance():
    settings = AuthSettings(_env_file=None, AUTH_COOKIE_SECURE=True)

    class InjectorStub:

        def get(self, interface):
            assert interface is AuthSettings
            return settings

    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/csrf",
        "app": SimpleNamespace(state=SimpleNamespace(injector=InjectorStub())),
        "headers": [],
    })

    assert auth_dependencies.get_auth_settings(request) is settings
