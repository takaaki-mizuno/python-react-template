from typing import Any

from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.database import get_database_settings


def build_engine_and_session_factory(
    database_url: str | None = None, ) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    database_settings = get_database_settings()
    target_url = database_url or database_settings.DATABASE_URL
    engine_kwargs: dict[str, Any] = {
        "future": True,
        "echo": database_settings.DATABASE_ECHO,
        "hide_parameters": True,
        "pool_pre_ping": True,
    }

    if target_url.startswith("postgresql+asyncpg://"):
        engine_kwargs.update({
            "pool_size": database_settings.DATABASE_POOL_SIZE,
            "max_overflow": database_settings.DATABASE_MAX_OVERFLOW,
            "pool_recycle": database_settings.DATABASE_POOL_RECYCLE_SECONDS,
        })

    engine = create_async_engine(target_url, **engine_kwargs)
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory
