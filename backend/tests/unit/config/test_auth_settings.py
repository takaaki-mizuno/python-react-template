import pytest
from pydantic import ValidationError

from app.config.auth import AuthSettings


def _settings() -> AuthSettings:
    return AuthSettings(_env_file=None)


def test_auth_settings_reads_session_ttl_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_ABSOLUTE_TTL_SECONDS", "123")

    settings = _settings()

    assert settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS == 123


def test_auth_settings_session_touch_interval_defaults_to_300():
    settings = _settings()

    assert settings.AUTH_SESSION_TOUCH_INTERVAL_SECONDS == 300
    assert settings.effective_session_touch_interval_seconds() == 300


def test_auth_settings_session_touch_interval_can_be_zero(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_TOUCH_INTERVAL_SECONDS", "0")

    settings = _settings()

    assert settings.effective_session_touch_interval_seconds() == 0


def test_auth_settings_session_touch_interval_clamps_to_half_idle_ttl():
    settings = AuthSettings(
        _env_file=None,
        AUTH_SESSION_IDLE_TTL_SECONDS=100,
        AUTH_SESSION_TOUCH_INTERVAL_SECONDS=90,
    )

    assert settings.effective_session_touch_interval_seconds() == 50


def test_auth_settings_cookie_secure_defaults_to_none():
    settings = _settings()

    assert settings.AUTH_COOKIE_SECURE is None


def test_auth_settings_reads_cookie_secure_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")

    settings = _settings()

    assert settings.AUTH_COOKIE_SECURE is False


def test_auth_settings_trusted_proxy_ips_defaults_to_empty_string():
    settings = _settings()

    assert settings.AUTH_TRUSTED_PROXY_IPS == ""


def test_auth_settings_reads_trusted_proxy_ips_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_IPS", "127.0.0.1,10.0.0.0/8")

    settings = _settings()

    assert settings.AUTH_TRUSTED_PROXY_IPS == "127.0.0.1,10.0.0.0/8"


def test_auth_settings_rejects_invalid_trusted_proxy_ips(monkeypatch):
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_IPS", "127.0.0.1,not-an-ip")

    try:
        _settings()
    except ValidationError as error:
        assert "AUTH_TRUSTED_PROXY_IPS must contain only IP addresses" in str(
            error)
    else:
        raise AssertionError("Expected settings validation to fail")


@pytest.mark.parametrize("trusted_proxy_ips", ["0.0.0.0/0", "::/0"])
def test_auth_settings_rejects_trusting_all_proxy_ips(monkeypatch,
                                                      trusted_proxy_ips):
    monkeypatch.setenv("AUTH_TRUSTED_PROXY_IPS", trusted_proxy_ips)

    try:
        _settings()
    except ValidationError as error:
        assert "AUTH_TRUSTED_PROXY_IPS must not trust all addresses" in str(
            error)
    else:
        raise AssertionError("Expected settings validation to fail")


def test_auth_settings_password_hash_concurrency_defaults_to_four():
    settings = _settings()

    assert settings.AUTH_PASSWORD_HASH_CONCURRENCY == 4


def test_auth_settings_reads_password_hash_concurrency_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD_HASH_CONCURRENCY", "2")

    settings = _settings()

    assert settings.AUTH_PASSWORD_HASH_CONCURRENCY == 2


def test_auth_settings_rejects_non_positive_password_hash_concurrency(
        monkeypatch):
    monkeypatch.setenv("AUTH_PASSWORD_HASH_CONCURRENCY", "0")

    try:
        _settings()
    except ValidationError as error:
        assert "AUTH_PASSWORD_HASH_CONCURRENCY must be at least 1" in str(
            error)
    else:
        raise AssertionError("Expected settings validation to fail")


def test_auth_settings_rate_limit_failure_defaults():
    settings = _settings()

    assert settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP == 5
    assert settings.AUTH_RATE_LIMIT_FAILURES_PER_IP == 20
    assert settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL == 20
    assert settings.AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP == 10
    assert settings.AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS == 3600
    assert settings.AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE == 10000


def test_auth_settings_rejects_non_positive_rate_limit_values(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP", "0")

    try:
        _settings()
    except ValidationError as error:
        assert "value must be at least 1" in str(error)
    else:
        raise AssertionError("Expected settings validation to fail")


def test_auth_settings_ignores_old_attempt_rate_limit_env_keys(monkeypatch):
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP", "1")
    monkeypatch.setenv("AUTH_RATE_LIMIT_ATTEMPTS_PER_IP", "1")

    settings = _settings()

    assert "AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP" not in settings.model_fields_set
    assert "AUTH_RATE_LIMIT_ATTEMPTS_PER_IP" not in settings.model_fields_set
    assert settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP == 5
    assert settings.AUTH_RATE_LIMIT_FAILURES_PER_IP == 20


def test_auth_settings_csrf_exempt_paths_defaults_to_empty_string():
    settings = _settings()

    assert settings.AUTH_CSRF_EXEMPT_PATHS == ""


def test_auth_settings_reads_csrf_exempt_paths_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_CSRF_EXEMPT_PATHS",
                       "/api/auth/oauth/callback,/api/webhooks/example")

    settings = _settings()

    assert settings.AUTH_CSRF_EXEMPT_PATHS == (
        "/api/auth/oauth/callback,/api/webhooks/example")
