from app.libraries.database_engine import build_engine_and_session_factory


def test_engine_factory_accepts_override_database_url():
    engine, session_factory = build_engine_and_session_factory(
        "postgresql+asyncpg://app:app@localhost:5432/app_test", )

    assert "postgresql+asyncpg://app:***@localhost:5432/app_test" in str(
        engine.url)
    assert session_factory is not None
