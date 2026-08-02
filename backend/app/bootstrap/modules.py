from dataclasses import dataclass
from logging import Logger, getLogger

from injector import Binder, Module, provider, singleton
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config import Config, get_config
from app.config.auth import AuthSettings, get_auth_settings
from app.interfaces.libraries.rate_limiter_interface import \
    LoginRateLimiterInterface
from app.interfaces.services.auth_repository_interface import \
    AuthRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.get_sample_index_usecase_interface import \
    GetSampleIndexUsecaseInterface
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.libraries.database_engine import build_engine_and_session_factory
from app.libraries.password_hasher import PasswordHashExecutor
from app.services.auth_repository import AuthRepository
from app.services.unit_of_work import UnitOfWork
from app.usecases.auth_usecase import AuthUsecase
from app.usecases.get_sample_index_usecase import GetSampleIndexUsecase


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
        binder.bind(AuthRepositoryInterface,
                    to=AuthRepository,
                    scope=singleton)
        binder.bind(AuthUsecaseInterface, to=AuthUsecase, scope=singleton)

    @singleton
    @provider
    def provide_rate_limiter(
        self,
        settings: AuthSettings,
    ) -> LoginRateLimiterInterface:
        return InMemoryLoginRateLimiter(
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
            registration_window_seconds=settings.
            AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS,
            max_failures_per_email_ip=settings.
            AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP,
            max_failures_per_ip=settings.AUTH_RATE_LIMIT_FAILURES_PER_IP,
            max_failures_per_email=settings.AUTH_RATE_LIMIT_FAILURES_PER_EMAIL,
            max_registrations_per_ip=settings.
            AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP,
            max_buckets_per_scope=settings.
            AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE,
        )

    @singleton
    @provider
    def provide_password_hash_executor(
        self,
        settings: AuthSettings,
    ) -> PasswordHashExecutor:
        return PasswordHashExecutor(
            max_workers=settings.AUTH_PASSWORD_HASH_CONCURRENCY)


class SampleModule(Module):

    def configure(self, binder: Binder) -> None:
        binder.bind(
            GetSampleIndexUsecaseInterface,
            to=GetSampleIndexUsecase,
            scope=singleton,
        )
