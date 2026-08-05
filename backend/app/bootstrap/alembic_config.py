from alembic.config import Config as AlembicConfig


def build_alembic_engine_section(
    config: AlembicConfig,
    database_url: str,
) -> dict[str, str]:
    section = dict(config.get_section(config.config_ini_section) or {})
    section["sqlalchemy.url"] = database_url
    return section
