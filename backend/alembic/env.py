from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.bootstrap.alembic_config import build_alembic_engine_section
from app.config.database import get_alembic_database_url, get_database_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = SQLModel.metadata


def get_database_url() -> str:
    settings = get_database_settings()
    if "DATABASE_URL" not in settings.model_fields_set:
        raise CommandError("DATABASE_URL must be configured explicitly for Alembic.")
    try:
        return get_alembic_database_url(settings)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        build_alembic_engine_section(config, get_database_url()),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
