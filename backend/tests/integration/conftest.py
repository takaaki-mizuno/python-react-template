import asyncio
import inspect
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
    engine = create_async_engine(database_url, future=True, poolclass=NullPool)
    try:
        await wait_for_database_engine(engine)
        return
    finally:
        await engine.dispose()


async def wait_for_database_engine(engine: AsyncEngine) -> None:
    for _ in range(20):
        try:
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
            return
        except Exception:
            await asyncio.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready for auth integration tests")


@pytest_asyncio.fixture
async def async_engine() -> AsyncIterator[AsyncEngine]:
    database_url = require_test_database_url()
    engine = create_async_engine(database_url, future=True, pool_pre_ping=True, poolclass=NullPool)
    try:
        await wait_for_database_engine(engine)
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def force_memory_rate_limiter_backend(monkeypatch, request) -> None:
    if request.node.get_closest_marker("redis_rate_limiter") is None:
        monkeypatch.setenv("AUTH_RATE_LIMIT_BACKEND", "memory")


@pytest_asyncio.fixture(autouse=True)
async def clean_auth_tables(request) -> AsyncIterator[None]:
    if (request.node.get_closest_marker("redis_rate_limiter") is not None
            and request.node.get_closest_marker("auth_tables") is None):
        yield
        return

    database_url = require_test_database_url()
    engine = create_async_engine(database_url, future=True, pool_pre_ping=True, poolclass=NullPool)
    await wait_for_database_engine(engine)
    async with engine.begin() as connection:
        await _truncate_auth_tables(connection)
    try:
        yield
    finally:
        async with engine.begin() as connection:
            await _truncate_auth_tables(connection)
        await engine.dispose()


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
            limiter = app.state.injector.get(LoginRateLimiterInterface)
            reset = getattr(limiter, "reset_for_tests", None)
            if reset is None:
                raise AssertionError("Login rate limiter must provide reset_for_tests()")
            result = reset()
            if inspect.isawaitable(result):
                raise AssertionError("Integration client fixture requires sync reset_for_tests(); "
                                     "Redis limiter must use Redis-specific async tests")
