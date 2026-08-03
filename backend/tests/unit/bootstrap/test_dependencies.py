from types import SimpleNamespace

from starlette.requests import Request

from app.bootstrap.dependencies import inject
from app.config.auth import AuthSettings


def _request_with_injector(injector) -> Request:
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/auth/csrf",
        "app": SimpleNamespace(state=SimpleNamespace(injector=injector)),
        "headers": [],
    })


def test_inject_returns_instance_from_app_injector():
    settings = AuthSettings(_env_file=None, AUTH_COOKIE_SECURE=True)

    class InjectorStub:

        def get(self, interface):
            assert interface is AuthSettings
            return settings

    dependency = inject(AuthSettings)

    assert dependency(_request_with_injector(InjectorStub())) is settings


def test_inject_returns_new_callable_each_time():
    assert inject(AuthSettings) is not inject(AuthSettings)


def test_inject_dependency_return_value_has_requested_type():
    settings = AuthSettings(_env_file=None, AUTH_COOKIE_SECURE=True)

    class InjectorStub:

        def get(self, interface):
            return settings

    dependency = inject(AuthSettings)
    resolved = dependency(_request_with_injector(InjectorStub()))

    assert isinstance(resolved, AuthSettings)
