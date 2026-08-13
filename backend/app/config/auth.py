from ipaddress import ip_network
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    AUTH_COOKIE_SECURE: bool | None = None
    AUTH_SESSION_COOKIE_PREFIX: str = ""
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
    AUTH_RATE_LIMIT_BACKEND: Literal["memory", "redis"] = "memory"
    AUTH_RATE_LIMIT_REDIS_URL: str = ""
    AUTH_RATE_LIMIT_REDIS_KEY_PREFIX: str = "auth:rate_limit"
    AUTH_RATE_LIMIT_REDIS_UNAVAILABLE_POLICY: Literal["fail_closed", "fail_open"] = "fail_closed"
    AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS: float = 0.25
    AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS: float = 0.25
    AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS: float = 0.8
    AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_FAILURES: int = 5
    AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_COOLDOWN_SECONDS: int = 10
    AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS: int = 100
    AUTH_CSRF_EXEMPT_PATHS: str = ""

    @model_validator(mode="after")
    def _validate_host_prefixed_session_cookie_requires_secure(self) -> "AuthSettings":
        if self.AUTH_SESSION_COOKIE_PREFIX == "__Host-" and self.AUTH_COOKIE_SECURE is False:
            raise ValueError("AUTH_SESSION_COOKIE_PREFIX=__Host- requires AUTH_COOKIE_SECURE=true")
        return self

    @model_validator(mode="after")
    def _validate_redis_rate_limit_settings(self) -> "AuthSettings":
        if self.AUTH_RATE_LIMIT_BACKEND == "redis" and not self.AUTH_RATE_LIMIT_REDIS_URL:
            raise ValueError(
                "AUTH_RATE_LIMIT_REDIS_URL is required when AUTH_RATE_LIMIT_BACKEND=redis")
        minimum_deadline = (self.AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS +
                            2 * self.AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS)
        if minimum_deadline > self.AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS:
            raise ValueError("AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS must be at least "
                             "AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS + "
                             "2 * AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS")
        return self

    @field_validator("AUTH_PASSWORD_HASH_CONCURRENCY")
    @classmethod
    def _validate_positive_password_hash_concurrency(cls, value: int) -> int:
        if value < 1:
            raise ValueError("AUTH_PASSWORD_HASH_CONCURRENCY must be at least 1")
        return value

    @field_validator("AUTH_SESSION_COOKIE_PREFIX")
    @classmethod
    def _validate_session_cookie_prefix(cls, value: str) -> str:
        if value not in {"", "__Host-"}:
            raise ValueError("AUTH_SESSION_COOKIE_PREFIX must be empty or __Host-")
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
        "AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_FAILURES",
        "AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_COOLDOWN_SECONDS",
    )
    @classmethod
    def _validate_positive_int(cls, value: int) -> int:
        if value < 1:
            raise ValueError("value must be at least 1")
        return value

    @field_validator(
        "AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS",
        "AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS",
        "AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS",
    )
    @classmethod
    def _validate_redis_timeout_minimum(cls, value: float) -> float:
        if value < 0.05:
            raise ValueError("value must be at least 0.05")
        return value

    @field_validator("AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS")
    @classmethod
    def _validate_redis_max_connections(cls, value: int) -> int:
        if value < 1:
            raise ValueError("AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS must be at least 1")
        return value

    @field_validator("AUTH_RATE_LIMIT_REDIS_KEY_PREFIX")
    @classmethod
    def _validate_redis_key_prefix(cls, value: str) -> str:
        glob_chars = {"*", "?", "[", "]"}
        if (not value.strip() or not value.strip(":") or any(char in value for char in glob_chars)
                or "\n" in value or "\r" in value):
            raise ValueError("AUTH_RATE_LIMIT_REDIS_KEY_PREFIX must not be empty or contain "
                             "glob characters, colon-only value, or newline")
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
