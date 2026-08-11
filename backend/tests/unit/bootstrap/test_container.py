from logging import Logger

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.bootstrap import container as container_module
from app.config import Config
from app.config.auth import AuthSettings
from app.config.oidc import OidcProviderSettings, OidcSettings
from app.interfaces.services.admin_user_repository_interface import AdminUserRepositoryInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.oidc_provider_client_interface import OidcProviderClientInterface
from app.interfaces.services.sample_item_repository_interface import SampleItemRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.admin_user_usecase_interface import AdminUserUsecaseInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.oauth_oidc_usecase_interface import OAuthOidcUsecaseInterface
from app.interfaces.usecases.sample_item_usecase_interface import SampleItemUsecaseInterface
from app.libraries.password_hasher import PasswordHashExecutor


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
