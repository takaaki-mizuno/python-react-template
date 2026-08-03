from ipaddress import ip_network

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    AUTH_COOKIE_SECURE: bool | None = None
    AUTH_TRUSTED_PROXY_IPS: str = ""
    AUTH_SESSION_ABSOLUTE_TTL_SECONDS: int = 604800
    AUTH_SESSION_IDLE_TTL_SECONDS: int = 86400
    AUTH_SESSION_TOUCH_INTERVAL_SECONDS: int = 300
    AUTH_PASSWORD_HASH_CONCURRENCY: int = 4
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 900
    AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP: int = 5
    AUTH_RATE_LIMIT_FAILURES_PER_IP: int = 20
    AUTH_RATE_LIMIT_FAILURES_PER_EMAIL: int = 20
    AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP: int = 10
    AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS: int = 3600
    AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE: int = 10000
    AUTH_CSRF_EXEMPT_PATHS: str = ""

    @field_validator("AUTH_PASSWORD_HASH_CONCURRENCY")
    @classmethod
    def _validate_positive_password_hash_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("AUTH_PASSWORD_HASH_CONCURRENCY must be at least 1")
        return value

    @field_validator(
        "AUTH_SESSION_ABSOLUTE_TTL_SECONDS",
        "AUTH_SESSION_IDLE_TTL_SECONDS",
        "AUTH_RATE_LIMIT_WINDOW_SECONDS",
        "AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP",
        "AUTH_RATE_LIMIT_FAILURES_PER_IP",
        "AUTH_RATE_LIMIT_FAILURES_PER_EMAIL",
        "AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP",
        "AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS",
        "AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE",
    )
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("value must be at least 1")
        return value

    @field_validator("AUTH_TRUSTED_PROXY_IPS")
    @classmethod
    def _validate_trusted_proxy_ips(cls, value: str) -> str:
        for raw_proxy_ip in value.split(","):
            proxy_ip = raw_proxy_ip.strip()
            if not proxy_ip:
                continue
            try:
                network = ip_network(proxy_ip, strict=False)
            except ValueError as error:
                raise ValueError("AUTH_TRUSTED_PROXY_IPS must contain only IP addresses "
                                 "or CIDR networks") from error
            if network.prefixlen == 0:
                raise ValueError("AUTH_TRUSTED_PROXY_IPS must not trust all addresses")
        return value

    def effective_session_touch_interval_seconds(self) -> int:
        configured_interval = self.AUTH_SESSION_TOUCH_INTERVAL_SECONDS
        if configured_interval <= 0:
            return configured_interval
        max_interval = self.AUTH_SESSION_IDLE_TTL_SECONDS // 2
        if configured_interval >= max_interval:
            return max_interval
        return configured_interval


def get_auth_settings() -> AuthSettings:
    return AuthSettings()
