from app.config.auth import get_auth_settings


def test_auth_settings_reads_session_ttl_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_ABSOLUTE_TTL_SECONDS", "123")

    settings = get_auth_settings()

    assert settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS == 123
