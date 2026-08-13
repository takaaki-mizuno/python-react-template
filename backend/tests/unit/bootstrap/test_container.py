from logging import Logger

import pytest
from injector import Injector
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bootstrap import container as container_module
from app.config import Config
from app.config.auth import AuthSettings
from app.config.oidc import OidcProviderSettings, OidcSettings
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from app.interfaces.services.admin_user_repository_interface import AdminUserRepositoryInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.oidc_provider_client_interface import OidcProviderClientInterface
from app.interfaces.services.sample_item_repository_interface import SampleItemRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.admin_user_usecase_interface import AdminUserUsecaseInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.oauth_oidc_usecase_interface import OAuthOidcUsecaseInterface
from app.interfaces.usecases.sample_item_usecase_interface import SampleItemUsecaseInterface
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.libraries.password_hasher import PasswordHashExecutor
from app.libraries.redis_login_rate_limiter import RedisLoginRateLimiter


def test_build_container_binds_module_provider_singletons(monkeypatch):
    from app.bootstrap import modules

    config = Config(ENVIRONMENT="test")
    settings = AuthSettings(_env_file=None,
                            AUTH_COOKIE_SECURE=True,
                            AUTH_SESSION_ABSOLUTE_TTL_SECONDS=123)
    oidc_settings = OidcSettings(
        providers=(OidcProviderSettings(
            provider_id="google",
            display_name="Google",
            issuer="https://accounts.example.com",
            client_id="client-id",
            client_secret="client-secret",
            callback_path="/api/auth/oidc/google/callback",
        ), ),
        AUTH_OIDC_REDIRECT_BASE_URL="https://app.example.com",
    )
    engine = object()
    session_factory = object()

    monkeypatch.setattr(modules, "get_config", lambda: config)
    monkeypatch.setattr(modules, "get_auth_settings", lambda: settings)
    monkeypatch.setattr(modules, "get_oidc_settings", lambda: oidc_settings)
    monkeypatch.setattr(
        modules,
        "build_engine_and_session_factory",
        lambda: (engine, session_factory),
    )

    injector = container_module.build_container()

    assert injector.get(Config) is config
    assert injector.get(AuthSettings) is settings
    assert injector.get(OidcSettings) is oidc_settings
    assert injector.get(AsyncEngine) is engine
    assert injector.get(async_sessionmaker[AsyncSession]) is session_factory
    assert isinstance(injector.get(Logger), Logger)
    assert injector.get(AuthSettings) is injector.get(AuthSettings)
    assert injector.get(AuthUsecaseInterface) is injector.get(AuthUsecaseInterface)
    assert injector.get(OidcProviderClientInterface) is injector.get(OidcProviderClientInterface)
    assert injector.get(OAuthOidcUsecaseInterface) is injector.get(OAuthOidcUsecaseInterface)
    assert injector.get(SampleItemUsecaseInterface) is injector.get(SampleItemUsecaseInterface)
    assert injector.get(AdminUserUsecaseInterface) is injector.get(AdminUserUsecaseInterface)
    assert injector.get(AdminUserRepositoryInterface) is injector.get(AdminUserRepositoryInterface)
    assert injector.get(SampleItemRepositoryInterface) is injector.get(
        SampleItemRepositoryInterface)
    assert injector.get(AuthRepositoryInterface) is injector.get(AuthRepositoryInterface)
    assert injector.get(UnitOfWorkInterface) is injector.get(UnitOfWorkInterface)
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


def test_build_container_binds_memory_rate_limiter_by_default(monkeypatch):
    from app.bootstrap import modules

    settings = AuthSettings(_env_file=None)
    oidc_settings = OidcSettings()

    monkeypatch.setattr(modules, "get_auth_settings", lambda: settings)
    monkeypatch.setattr(modules, "get_oidc_settings", lambda: oidc_settings)
    injector = Injector(modules=[
        modules.CoreModule(),
        modules.AuthModule(),
    ])

    rate_limiter = injector.get(LoginRateLimiterInterface)

    assert isinstance(rate_limiter, InMemoryLoginRateLimiter)


def test_build_container_binds_redis_rate_limiter_when_configured(monkeypatch):
    from app.bootstrap import modules

    created_pools = []
    created_clients = []

    class BlockingConnectionPoolFactory:

        @staticmethod
        def from_url(url: str, **kwargs):
            pool = object()
            created_pools.append((url, kwargs, pool))
            return pool

    class RedisFactory:

        @staticmethod
        def from_pool(pool):
            created_clients.append(pool)
            return object()

    settings = AuthSettings(
        _env_file=None,
        AUTH_RATE_LIMIT_BACKEND="redis",
        AUTH_RATE_LIMIT_REDIS_URL="redis://localhost:6379/1",
        AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS=0.3,
        AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS=0.2,
        AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS=0.8,
        AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS=25,
    )
    oidc_settings = OidcSettings()
    monkeypatch.setattr(modules, "get_auth_settings", lambda: settings)
    monkeypatch.setattr(modules, "get_oidc_settings", lambda: oidc_settings)
    monkeypatch.setattr(modules.redis, "Redis", RedisFactory)
    monkeypatch.setattr(modules.redis, "BlockingConnectionPool", BlockingConnectionPoolFactory)

    injector = Injector(modules=[
        modules.CoreModule(),
        modules.AuthModule(),
    ])
    rate_limiter = injector.get(LoginRateLimiterInterface)

    assert isinstance(rate_limiter, RedisLoginRateLimiter)
    assert created_pools == [(
        "redis://localhost:6379/1",
        {
            "socket_timeout": 0.3,
            "socket_connect_timeout": 0.2,
            "max_connections": 25,
            "timeout": 0.4,
        },
        created_clients[0],
    )]
    assert created_clients == [created_pools[0][2]]
