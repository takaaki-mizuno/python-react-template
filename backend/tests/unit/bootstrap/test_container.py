from app.bootstrap import container as container_module
from app.config.auth import AuthSettings


def test_build_container_binds_created_auth_settings_instance(monkeypatch):
    settings = AuthSettings(
        ENVIRONMENT="production",
        AUTH_SESSION_ABSOLUTE_TTL_SECONDS=123,
    )
    monkeypatch.setattr(container_module, "get_auth_settings",
                        lambda: settings)

    injector = container_module.build_container()

    # Injector auto-constructs unbound concrete classes, so identity is the
    # regression guard that proves the explicit startup binding still exists.
    assert injector.get(AuthSettings) is settings
    assert injector.get(AuthSettings) is injector.get(AuthSettings)
