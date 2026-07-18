from logging import Logger, getLogger

from injector import Binder, Injector, singleton

from app.config import Config, config
from app.config.auth import get_auth_settings
from app.interfaces.services.auth_repository_interface import \
    AuthRepositoryInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.get_sample_index_usecase_interface import \
    GetSampleIndexUsecaseInterface
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.libraries.database_engine import build_engine_and_session_factory
from app.services.auth_repository import AuthRepository
from app.usecases.auth_usecase import AuthUsecase
from app.usecases.get_sample_index_usecase import GetSampleIndexUsecase


def build_container() -> Injector:
    return Injector(modules=[configure])


def configure(binder: Binder):
    binder.bind(Config, to=config, scope=singleton)

    logger = getLogger(__name__)
    binder.bind(Logger, to=logger, scope=singleton)

    # Usecases
    get_sample_index_usecase = GetSampleIndexUsecase(
        config=config,
        logger=logger,
    )
    binder.bind(GetSampleIndexUsecaseInterface, to=get_sample_index_usecase)

    auth_settings = get_auth_settings()
    _, session_factory = build_engine_and_session_factory()
    auth_repository = AuthRepository(session_factory=session_factory)
    auth_rate_limiter = InMemoryLoginRateLimiter(
        window_seconds=auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts_per_email_ip=auth_settings.
        AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP,
        max_attempts_per_ip=auth_settings.AUTH_RATE_LIMIT_ATTEMPTS_PER_IP,
    )
    auth_usecase = AuthUsecase(
        auth_repository=auth_repository,
        auth_rate_limiter=auth_rate_limiter,
        auth_settings=auth_settings,
        logger=logger,
    )

    binder.bind(AuthRepositoryInterface, to=auth_repository, scope=singleton)
    binder.bind(InMemoryLoginRateLimiter,
                to=auth_rate_limiter,
                scope=singleton)
    binder.bind(AuthUsecaseInterface, to=auth_usecase, scope=singleton)
