import asyncio
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import (AsyncEngine, AsyncSession, async_sessionmaker,
                                    create_async_engine)
from sqlalchemy.pool import NullPool

from app.bootstrap.create_app import create_app
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from tests.integration.helpers import require_test_database_url


async def wait_for_database(database_url: str) -> None:
    for _ in range(20):
        engine = create_async_engine(database_url, future=True, poolclass=NullPool)
        try:
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
            return
        except Exception:
            await asyncio.sleep(1)
        finally:
            await engine.dispose()
    raise RuntimeError("PostgreSQL did not become ready for auth integration tests")


@pytest_asyncio.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    database_url = require_test_database_url()
    await wait_for_database(database_url)
    engine = create_async_engine(database_url, future=True, pool_pre_ping=True, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_auth_tables(async_engine: AsyncEngine) -> AsyncIterator[None]:
    async with async_engine.begin() as connection:
        await _truncate_auth_tables(connection)
    yield
    async with async_engine.begin() as connection:
        await _truncate_auth_tables(connection)


async def _truncate_auth_tables(connection) -> None:
    tables = [
        "sample_items",
        "auth_oidc_authorization_states",
        "auth_identities",
        "auth_audit_logs",
        "auth_sessions",
        "user_roles",
        "users",
    ]
    existing_tables = []
    for table in tables:
        exists = await connection.scalar(text("SELECT to_regclass(:table_name)"),
                                         {"table_name": f"public.{table}"})
        if exists is not None:
            existing_tables.append(table)
    if existing_tables:
        await connection.execute(text(f"TRUNCATE TABLE {', '.join(existing_tables)} CASCADE"))


@pytest_asyncio.fixture
async def async_session(async_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session


@pytest.fixture
def client(monkeypatch) -> Iterator[TestClient]:
    test_database_url = require_test_database_url()

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")

    app = create_app()
    with TestClient(app) as test_client:
        try:
            yield test_client
        finally:
            app.state.injector.get(LoginRateLimiterInterface).reset()
