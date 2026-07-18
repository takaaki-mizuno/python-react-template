from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    ENVIRONMENT: str = "local"
    AUTH_SESSION_ABSOLUTE_TTL_SECONDS: int = 604800
    AUTH_SESSION_IDLE_TTL_SECONDS: int = 86400
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 900
    AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP: int = 5
    AUTH_RATE_LIMIT_ATTEMPTS_PER_IP: int = 20


def get_auth_settings() -> AuthSettings:
    return AuthSettings()
