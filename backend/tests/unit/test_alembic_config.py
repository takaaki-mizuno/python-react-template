from pathlib import Path

from alembic.config import Config as AlembicConfig

from app.bootstrap.alembic_config import build_alembic_engine_section

BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_build_alembic_engine_section_preserves_percent_encoded_database_url() -> None:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    database_url = "postgresql+asyncpg://app:p%40ss@localhost:5432/app_test"

    section = build_alembic_engine_section(config, database_url)

    assert section["script_location"].endswith("/alembic")
    assert section["sqlalchemy.url"] == database_url
    assert "%40" in section["sqlalchemy.url"]


def test_alembic_env_does_not_use_configparser_url_setter() -> None:
    env_source = (BACKEND_DIR / "alembic" / "env.py").read_text(encoding="utf-8")

    assert "set_main_option" not in env_source
    assert "build_alembic_engine_section" in env_source
