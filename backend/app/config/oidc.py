import os
import re
from collections.abc import Mapping
from typing import Literal, cast
from urllib.parse import urljoin, urlparse

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

AutoProvisionMode = Literal["enabled", "link-only"]
LinkMode = Literal["auto", "manual", "disabled"]

_PROVIDER_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]*$")


class OidcProviderSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider_id: str
    display_name: str
    issuer: str
    client_id: str
    client_secret: str
    scope: tuple[str, ...] = ("openid", "email", "profile")
    trust_verified_email: bool = False
    auto_provision: AutoProvisionMode = "link-only"
    link_mode: LinkMode = "manual"
    callback_path: str
    claims_allowlist: tuple[str, ...] = ()

    @field_validator("provider_id")
    @classmethod
    def _validate_provider_id(cls, value: str) -> str:
        if not _PROVIDER_ID_PATTERN.fullmatch(value):
            raise ValueError("provider_id must be lowercase alphanumeric, dash, or underscore")
        return value

    @field_validator("issuer")
    @classmethod
    def _validate_issuer(cls, value: str) -> str:
        _validate_absolute_url(value, "issuer")
        return value.rstrip("/")

    @field_validator("client_id", "client_secret", "display_name")
    @classmethod
    def _validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("callback_path")
    @classmethod
    def _validate_callback_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("callback_path must be an absolute path")
        return value

    @property
    def allows_auto_provision(self) -> bool:
        return self.trust_verified_email and self.auto_provision == "enabled"

    @property
    def allows_auto_link(self) -> bool:
        return self.trust_verified_email and self.link_mode == "auto"


class OidcSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    providers: tuple[OidcProviderSettings, ...] = ()
    AUTH_OIDC_REDIRECT_BASE_URL: str | None = None
    AUTH_OIDC_REAUTH_FRESHNESS_SECONDS: int = 300
    AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP: int = 20
    AUTH_OIDC_STATE_TTL_SECONDS: int = 300
    AUTH_OIDC_AUTH_TIME_FUTURE_LEEWAY_SECONDS: int = 60

    @field_validator(
        "AUTH_OIDC_REAUTH_FRESHNESS_SECONDS",
        "AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP",
        "AUTH_OIDC_STATE_TTL_SECONDS",
        "AUTH_OIDC_AUTH_TIME_FUTURE_LEEWAY_SECONDS",
    )
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("value must be at least 1")
        return value

    @field_validator("AUTH_OIDC_REDIRECT_BASE_URL")
    @classmethod
    def _validate_redirect_base_url(cls, value: str | None) -> str | None:
        if value is not None:
            _validate_absolute_url(value, "AUTH_OIDC_REDIRECT_BASE_URL")
            return value.rstrip("/")
        return value

    @model_validator(mode="after")
    def _validate_redirect_base_url_required_for_providers(self) -> "OidcSettings":
        if self.providers and self.AUTH_OIDC_REDIRECT_BASE_URL is None:
            raise ValueError(
                "AUTH_OIDC_REDIRECT_BASE_URL is required when OIDC providers are enabled")
        return self

    def get_provider(self, provider_id: str) -> OidcProviderSettings:
        for provider in self.providers:
            if provider.provider_id == provider_id:
                return provider
        raise KeyError(provider_id)

    def redirect_uri_for(self, provider_id: str) -> str:
        provider = self.get_provider(provider_id)
        if self.AUTH_OIDC_REDIRECT_BASE_URL is None:
            raise ValueError("AUTH_OIDC_REDIRECT_BASE_URL is required")
        return urljoin(f"{self.AUTH_OIDC_REDIRECT_BASE_URL}/", provider.callback_path.lstrip("/"))


def get_oidc_settings(environ: Mapping[str, str] | None = None) -> OidcSettings:
    env = os.environ if environ is None else environ
    provider_ids = _split_csv(env.get("AUTH_OIDC_ENABLED_PROVIDERS", ""))
    _validate_unique(provider_ids, "AUTH_OIDC_ENABLED_PROVIDERS")
    _validate_unique([_provider_env_suffix(provider_id) for provider_id in provider_ids],
                     "AUTH_OIDC_ENABLED_PROVIDERS env suffix")

    providers = tuple(_read_provider(env, provider_id) for provider_id in provider_ids)
    return OidcSettings(
        providers=providers,
        AUTH_OIDC_REDIRECT_BASE_URL=_empty_to_none(env.get("AUTH_OIDC_REDIRECT_BASE_URL")),
        AUTH_OIDC_REAUTH_FRESHNESS_SECONDS=_read_int(
            env,
            "AUTH_OIDC_REAUTH_FRESHNESS_SECONDS",
            300,
        ),
        AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP=_read_int(
            env,
            "AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP",
            20,
        ),
        AUTH_OIDC_STATE_TTL_SECONDS=_read_int(env, "AUTH_OIDC_STATE_TTL_SECONDS", 300),
    )


def _read_provider(env: Mapping[str, str], provider_id: str) -> OidcProviderSettings:
    if not _PROVIDER_ID_PATTERN.fullmatch(provider_id):
        raise ValueError("AUTH_OIDC_ENABLED_PROVIDERS must contain lowercase provider ids")
    prefix = f"AUTH_OIDC_PROVIDER_{_provider_env_suffix(provider_id)}"
    callback_path = env.get(f"{prefix}_CALLBACK_PATH", f"/api/auth/oidc/{provider_id}/callback")
    return OidcProviderSettings(
        provider_id=provider_id,
        display_name=_required(env, f"{prefix}_DISPLAY_NAME"),
        issuer=_required(env, f"{prefix}_ISSUER"),
        client_id=_required(env, f"{prefix}_CLIENT_ID"),
        client_secret=_required(env, f"{prefix}_CLIENT_SECRET"),
        scope=tuple(_split_csv_or_space(env.get(f"{prefix}_SCOPE", "openid email profile"))),
        trust_verified_email=_read_bool(env.get(f"{prefix}_TRUST_VERIFIED_EMAIL", "false")),
        auto_provision=cast(
            AutoProvisionMode,
            _read_literal(
                env.get(f"{prefix}_AUTO_PROVISION", "link-only"),
                {"enabled", "link-only"},
                f"{prefix}_AUTO_PROVISION",
            )),
        link_mode=cast(
            LinkMode,
            _read_literal(
                env.get(f"{prefix}_LINK_MODE", "manual"),
                {"auto", "manual", "disabled"},
                f"{prefix}_LINK_MODE",
            )),
        callback_path=callback_path,
        claims_allowlist=tuple(_split_csv(env.get(f"{prefix}_CLAIMS_ALLOWLIST", ""))),
    )


def _required(env: Mapping[str, str], key: str) -> str:
    value = env.get(key)
    if value is None or not value.strip():
        raise ValueError(f"{key} is required")
    return value


def _read_int(env: Mapping[str, str], key: str, default: int) -> int:
    raw_value = env.get(key)
    if raw_value is None or raw_value == "":
        return default
    return int(raw_value)


def _read_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no"}:
        return False
    raise ValueError("boolean value must be true or false")


def _read_literal(value: str, allowed: set[str], key: str) -> str:
    if value not in allowed:
        raise ValueError(f"{key} must be one of: {', '.join(sorted(allowed))}")
    return value


def _split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def _split_csv_or_space(value: str) -> list[str]:
    if "," in value:
        return _split_csv(value)
    return [part.strip() for part in value.split() if part.strip()]


def _validate_unique(values: list[str], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise ValueError(f"{label} contains duplicates")
        seen.add(value)


def _provider_env_suffix(provider_id: str) -> str:
    return provider_id.replace("-", "_").upper()


def _empty_to_none(value: str | None) -> str | None:
    if value is None or value == "":
        return None
    return value


def _validate_absolute_url(value: str, label: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        raise ValueError(f"{label} must be an absolute URL")
