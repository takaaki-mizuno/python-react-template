from app.config.database import DatabaseSettings


def test_database_settings_expose_urls_and_pool_defaults(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:app@localhost:5432/app",
    )
    monkeypatch.setenv(
        "ALEMBIC_DATABASE_URL",
        "postgresql://app:app@localhost:5432/app",
    )

    settings = DatabaseSettings()

    assert settings.DATABASE_URL == "postgresql+asyncpg://app:app@localhost:5432/app"
    assert settings.ALEMBIC_DATABASE_URL == "postgresql://app:app@localhost:5432/app"
    assert settings.DATABASE_POOL_SIZE == 10
    assert settings.DATABASE_MAX_OVERFLOW == 20
    assert settings.DATABASE_POOL_RECYCLE_SECONDS == 1800
    assert settings.DATABASE_ECHO is False
