import pytest

from app.config.oidc import get_oidc_settings


def test_oidc_settings_defaults_to_no_providers(monkeypatch):
    monkeypatch.delenv("AUTH_OIDC_ENABLED_PROVIDERS", raising=False)

    settings = get_oidc_settings()

    assert settings.providers == ()
    assert settings.AUTH_OIDC_REAUTH_FRESHNESS_SECONDS == 300


def test_oidc_settings_reads_global_and_provider_specific_env(monkeypatch):
    monkeypatch.setenv("AUTH_OIDC_ENABLED_PROVIDERS", "google")
    monkeypatch.setenv("AUTH_OIDC_REDIRECT_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("AUTH_OIDC_REAUTH_FRESHNESS_SECONDS", "600")
    monkeypatch.setenv("AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP", "12")
    monkeypatch.setenv("AUTH_OIDC_STATE_TTL_SECONDS", "180")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_DISPLAY_NAME", "Google")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_ISSUER", "https://accounts.google.com")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_SCOPE", "openid email profile")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL", "true")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION", "enabled")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE", "auto")
    monkeypatch.setenv(
        "AUTH_OIDC_PROVIDER_GOOGLE_CALLBACK_PATH",
        "/api/auth/oidc/google/callback",
    )
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_CLAIMS_ALLOWLIST", "hd, locale")

    settings = get_oidc_settings()

    assert settings.AUTH_OIDC_REDIRECT_BASE_URL == "https://app.example.com"
    assert settings.AUTH_OIDC_REAUTH_FRESHNESS_SECONDS == 600
    assert settings.AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP == 12
    assert settings.AUTH_OIDC_STATE_TTL_SECONDS == 180

    provider = settings.get_provider("google")
    assert provider.provider_id == "google"
    assert provider.display_name == "Google"
    assert provider.issuer == "https://accounts.google.com"
    assert provider.client_id == "client-id"
    assert provider.client_secret == "client-secret"
    assert provider.scope == ("openid", "email", "profile")
    assert provider.trust_verified_email is True
    assert provider.auto_provision == "enabled"
    assert provider.link_mode == "auto"
    assert provider.callback_path == "/api/auth/oidc/google/callback"
    assert provider.claims_allowlist == ("hd", "locale")
    assert settings.redirect_uri_for("google") == (
        "https://app.example.com/api/auth/oidc/google/callback")


@pytest.mark.parametrize(
    ("env_key", "env_value"),
    [
        ("AUTH_OIDC_ENABLED_PROVIDERS", "Google"),
        ("AUTH_OIDC_ENABLED_PROVIDERS", "google,google"),
        ("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET", ""),
        ("AUTH_OIDC_PROVIDER_GOOGLE_ISSUER", "not-a-url"),
        ("AUTH_OIDC_REDIRECT_BASE_URL", "/relative"),
        ("AUTH_OIDC_PROVIDER_GOOGLE_AUTO_PROVISION", "yes"),
        ("AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE", "password"),
        ("AUTH_OIDC_REAUTH_FRESHNESS_SECONDS", "0"),
    ],
)
def test_oidc_settings_rejects_invalid_values(monkeypatch, env_key, env_value):
    _set_valid_google_env(monkeypatch)
    monkeypatch.setenv(env_key, env_value)

    with pytest.raises(ValueError):
        get_oidc_settings()


def test_oidc_settings_rejects_missing_required_provider_env(monkeypatch):
    _set_valid_google_env(monkeypatch)
    monkeypatch.delenv("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID")

    with pytest.raises(ValueError, match="AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID"):
        get_oidc_settings()


def test_untrusted_provider_disables_auto_provision_and_link(monkeypatch):
    _set_valid_google_env(monkeypatch)
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL", "false")

    provider = get_oidc_settings().get_provider("google")

    assert provider.allows_auto_provision is False
    assert provider.allows_auto_link is False


@pytest.mark.parametrize("link_mode", ["manual", "disabled"])
def test_non_auto_link_modes_do_not_auto_link(monkeypatch, link_mode):
    _set_valid_google_env(monkeypatch)
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_LINK_MODE", link_mode)

    provider = get_oidc_settings().get_provider("google")

    assert provider.allows_auto_link is False


def _set_valid_google_env(monkeypatch):
    monkeypatch.setenv("AUTH_OIDC_ENABLED_PROVIDERS", "google")
    monkeypatch.setenv("AUTH_OIDC_REDIRECT_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_DISPLAY_NAME", "Google")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_ISSUER", "https://accounts.google.com")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_ID", "client-id")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_CLIENT_SECRET", "client-secret")
    monkeypatch.setenv("AUTH_OIDC_PROVIDER_GOOGLE_TRUST_VERIFIED_EMAIL", "true")
