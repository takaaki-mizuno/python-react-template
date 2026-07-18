from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    ALEMBIC_DATABASE_URL: str = "postgresql://app:app@localhost:5432/app"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    DATABASE_ECHO: bool = False


def get_database_settings() -> DatabaseSettings:
    # Keep settings lazy so tests can override env vars before app creation.
    return DatabaseSettings()
