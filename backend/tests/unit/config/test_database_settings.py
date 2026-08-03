import pytest

from app.config.database import DatabaseSettings, get_alembic_database_url


def test_database_settings_expose_urls_and_pool_defaults(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:app@localhost:5432/app",
    )

    settings = DatabaseSettings()

    assert settings.DATABASE_URL == "postgresql+asyncpg://app:app@localhost:5432/app"
    assert not hasattr(settings, "ALEMBIC_DATABASE_URL")
    assert settings.DATABASE_POOL_SIZE == 10
    assert settings.DATABASE_MAX_OVERFLOW == 20
    assert settings.DATABASE_POOL_RECYCLE_SECONDS == 1800
    assert settings.DATABASE_ECHO is False


def test_get_alembic_database_url_converts_psycopg_url():
    settings = DatabaseSettings(DATABASE_URL="postgresql://app:app@db:5432/app")

    assert get_alembic_database_url(settings) == "postgresql+asyncpg://app:app@db:5432/app"


def test_get_alembic_database_url_keeps_asyncpg_url():
    settings = DatabaseSettings(DATABASE_URL="postgresql+asyncpg://app:app@db:5432/app")

    assert get_alembic_database_url(settings) == "postgresql+asyncpg://app:app@db:5432/app"


@pytest.mark.parametrize(
    "database_url",
    [
        "",
        "sqlite:///tmp/app.db",
        "not-a-url",
    ],
)
def test_get_alembic_database_url_rejects_non_postgresql_urls(database_url):
    settings = DatabaseSettings(DATABASE_URL=database_url)

    with pytest.raises(ValueError):
        get_alembic_database_url(settings)
