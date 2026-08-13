from dataclasses import dataclass
from logging import Logger, getLogger

import redis.asyncio as redis
from injector import Binder, Module, provider, singleton
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Config, get_config
from app.config.auth import AuthSettings, get_auth_settings
from app.config.oidc import OidcSettings, get_oidc_settings
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from app.interfaces.services.admin_user_repository_interface import AdminUserRepositoryInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.oidc_provider_client_interface import OidcProviderClientInterface
from app.interfaces.services.sample_item_repository_interface import SampleItemRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.account_deletion_usecase_interface import \
    AccountDeletionUsecaseInterface
from app.interfaces.usecases.admin_user_usecase_interface import AdminUserUsecaseInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.authorization_usecase_interface import AuthorizationUsecaseInterface
from app.interfaces.usecases.oauth_oidc_usecase_interface import OAuthOidcUsecaseInterface
from app.interfaces.usecases.sample_item_usecase_interface import SampleItemUsecaseInterface
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.libraries.database_engine import build_engine_and_session_factory
from app.libraries.password_hasher import PasswordHashExecutor
from app.libraries.redis_login_rate_limiter import RedisLoginRateLimiter
from app.services.admin_user_repository import AdminUserRepository
from app.services.auth_repository import AuthRepository
from app.services.authorization_repository import AuthorizationRepository
from app.services.oidc_provider_client import OidcProviderClient
from app.services.sample_item_repository import SampleItemRepository
from app.services.unit_of_work import UnitOfWork
from app.usecases.account_deletion_usecase import AccountDeletionUsecase
from app.usecases.admin_user_usecase import AdminUserUsecase
from app.usecases.auth_usecase import AuthUsecase
from app.usecases.authorization_usecase import AuthorizationUsecase
from app.usecases.oauth_oidc_usecase import OAuthOidcUsecase
from app.usecases.sample_item_usecase import SampleItemUsecase


@dataclass(slots=True)
class DatabaseResources:
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]


class CoreModule(Module):

    @singleton
    @provider
    def provide_config(self) -> Config:
        return get_config()

    @singleton
    @provider
    def provide_auth_settings(self) -> AuthSettings:
        return get_auth_settings()

    @singleton
    @provider
    def provide_oidc_settings(self) -> OidcSettings:
        return get_oidc_settings()

    @singleton
    @provider
    def provide_logger(self) -> Logger:
        return getLogger("app")


class DatabaseModule(Module):

    def __init__(self) -> None:
        engine, session_factory = build_engine_and_session_factory()
        self._resources = DatabaseResources(engine, session_factory)

    @singleton
    @provider
    def provide_async_engine(self) -> AsyncEngine:
        return self._resources.engine

    @singleton
    @provider
    def provide_session_factory(self) -> async_sessionmaker[AsyncSession]:
        return self._resources.session_factory


class AuthModule(Module):

    def configure(self, binder: Binder) -> None:
        binder.bind(UnitOfWorkInterface, to=UnitOfWork, scope=singleton)
        binder.bind(AdminUserRepositoryInterface, to=AdminUserRepository, scope=singleton)
        binder.bind(AuthRepositoryInterface, to=AuthRepository, scope=singleton)
        binder.bind(AuthorizationRepositoryInterface, to=AuthorizationRepository, scope=singleton)
        binder.bind(OidcProviderClientInterface, to=OidcProviderClient, scope=singleton)
        binder.bind(AuthUsecaseInterface, to=AuthUsecase, scope=singleton)
        binder.bind(AdminUserUsecaseInterface, to=AdminUserUsecase, scope=singleton)
        binder.bind(AuthorizationUsecaseInterface, to=AuthorizationUsecase, scope=singleton)
        binder.bind(OAuthOidcUsecaseInterface, to=OAuthOidcUsecase, scope=singleton)

    @singleton
    @provider
    def provide_rate_limiter(
        self,
        settings: AuthSettings,
        oidc_settings: OidcSettings,
    ) -> LoginRateLimiterInterface:
        if settings.AUTH_RATE_LIMIT_BACKEND == "redis":
            pool_timeout_seconds = max(
                0.05,
                settings.AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS / 2,
            )
            redis_pool = redis.BlockingConnectionPool.from_url(
                settings.AUTH_RATE_LIMIT_REDIS_URL,
                socket_timeout=settings.AUTH_RATE_LIMIT_REDIS_SOCKET_TIMEOUT_SECONDS,
                socket_connect_timeout=(
                    settings.AUTH_RATE_LIMIT_REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS),
                max_connections=settings.AUTH_RATE_LIMIT_REDIS_MAX_CONNECTIONS,
                timeout=pool_timeout_seconds,
            )
            redis_client = redis.Redis.from_pool(redis_pool)
            return RedisLoginRateLimiter(
                window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
                registration_window_seconds=settings.AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS,
                max_failures_per_email_ip=settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP,
                max_failures_per_ip=settings.AUTH_RATE_LIMIT_FAILURES_PER_IP,
                max_failures_per_email=settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL,
                max_registrations_per_ip=settings.AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP,
                max_oidc_authorizations_per_ip=(
                    oidc_settings.AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP),
                redis_client=redis_client,
                key_prefix=settings.AUTH_RATE_LIMIT_REDIS_KEY_PREFIX,
                unavailable_policy=settings.AUTH_RATE_LIMIT_REDIS_UNAVAILABLE_POLICY,
                operation_deadline_seconds=(
                    settings.AUTH_RATE_LIMIT_REDIS_OPERATION_DEADLINE_SECONDS),
                circuit_breaker_failures=settings.AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_FAILURES,
                circuit_breaker_cooldown_seconds=(
                    settings.AUTH_RATE_LIMIT_REDIS_CIRCUIT_BREAKER_COOLDOWN_SECONDS),
            )
        return InMemoryLoginRateLimiter(
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
            registration_window_seconds=settings.AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS,
            max_failures_per_email_ip=settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP,
            max_failures_per_ip=settings.AUTH_RATE_LIMIT_FAILURES_PER_IP,
            max_failures_per_email=settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL,
            max_registrations_per_ip=settings.AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP,
            max_oidc_authorizations_per_ip=(oidc_settings.AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP),
            max_buckets_per_scope=settings.AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE,
        )

    @singleton
    @provider
    def provide_password_hash_executor(
        self,
        settings: AuthSettings,
    ) -> PasswordHashExecutor:
        return PasswordHashExecutor(max_workers=settings.AUTH_PASSWORD_HASH_CONCURRENCY)


class SampleModule(Module):

    def configure(self, binder: Binder) -> None:
        binder.bind(SampleItemRepositoryInterface, to=SampleItemRepository, scope=singleton)
        binder.bind(SampleItemUsecaseInterface, to=SampleItemUsecase, scope=singleton)


class AccountDeletionModule(Module):

    def configure(self, binder: Binder) -> None:
        binder.bind(AccountDeletionUsecaseInterface, to=AccountDeletionUsecase, scope=singleton)
