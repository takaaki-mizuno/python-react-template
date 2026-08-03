from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    DATABASE_ECHO: bool = False


def get_alembic_database_url(settings: DatabaseSettings) -> str:
    database_url = settings.DATABASE_URL.strip()
    if not database_url:
        raise ValueError("DATABASE_URL must not be empty.")

    try:
        url = make_url(database_url)
    except Exception as exc:
        raise ValueError("DATABASE_URL must be a valid PostgreSQL URL.") from exc

    if url.drivername == "postgresql":
        return url.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)
    if url.drivername == "postgresql+asyncpg":
        return url.render_as_string(hide_password=False)
    raise ValueError("DATABASE_URL must use postgresql+asyncpg or postgresql.")


def get_database_settings() -> DatabaseSettings:
    # Keep settings lazy so tests can override env vars before app creation.
    return DatabaseSettings()
