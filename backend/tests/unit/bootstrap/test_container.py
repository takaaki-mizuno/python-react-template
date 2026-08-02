from logging import Logger

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bootstrap import container as container_module
from app.config import Config
from app.config.auth import AuthSettings
from app.interfaces.services.auth_repository_interface import \
    AuthRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.get_sample_index_usecase_interface import \
    GetSampleIndexUsecaseInterface
from app.libraries.password_hasher import PasswordHashExecutor


def test_build_container_binds_module_provider_singletons(monkeypatch):
    from app.bootstrap import modules

    config = Config(ENVIRONMENT="test")
    settings = AuthSettings(_env_file=None,
                            AUTH_COOKIE_SECURE=True,
                            AUTH_SESSION_ABSOLUTE_TTL_SECONDS=123)
    engine = object()
    session_factory = object()

    monkeypatch.setattr(modules, "get_config", lambda: config)
    monkeypatch.setattr(modules, "get_auth_settings", lambda: settings)
    monkeypatch.setattr(
        modules,
        "build_engine_and_session_factory",
        lambda: (engine, session_factory),
    )

    injector = container_module.build_container()

    assert injector.get(Config) is config
    assert injector.get(AuthSettings) is settings
    assert injector.get(AsyncEngine) is engine
    assert injector.get(async_sessionmaker[AsyncSession]) is session_factory
    assert isinstance(injector.get(Logger), Logger)
    assert injector.get(AuthSettings) is injector.get(AuthSettings)
    assert injector.get(AuthUsecaseInterface) is injector.get(
        AuthUsecaseInterface)
    assert injector.get(GetSampleIndexUsecaseInterface) is injector.get(
        GetSampleIndexUsecaseInterface)
    assert injector.get(AuthRepositoryInterface) is injector.get(
        AuthRepositoryInterface)
    assert injector.get(UnitOfWorkInterface) is injector.get(
        UnitOfWorkInterface)
    password_hash_executor = injector.get(PasswordHashExecutor)
    try:
        assert password_hash_executor is injector.get(PasswordHashExecutor)
    finally:
        password_hash_executor.shutdown()


@pytest.mark.asyncio
async def test_build_container_resolves_real_async_engine():
    injector = container_module.build_container()
    engine = injector.get(AsyncEngine)

    try:
        assert isinstance(engine, AsyncEngine)
    finally:
        await engine.dispose()
