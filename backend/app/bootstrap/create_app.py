import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Config
from app.config.auth import AuthSettings
from app.config.authorization import authorization_config_errors
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from app.libraries.password_hasher import PasswordHashExecutor

from .container import build_container
from .csrf import CSRFMiddleware
from .error_handlers import register_error_handlers
from .route import setup_routes

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_error: BaseException | None = None
    try:
        yield
    except BaseException as error:
        app_error = error
        raise
    finally:
        cleanup_error: Exception | None = None
        try:
            await app.state.injector.get(LoginRateLimiterInterface).aclose()
        except Exception as error:
            logger.exception("Failed to close rate limiter")
            cleanup_error = cleanup_error or error
        try:
            await app.state.injector.get(AsyncEngine).dispose()
        except Exception as error:
            logger.exception("Failed to dispose database engine")
            cleanup_error = cleanup_error or error
        try:
            app.state.injector.get(PasswordHashExecutor).shutdown()
        except Exception as error:
            logger.exception("Failed to shutdown password hash executor")
            cleanup_error = cleanup_error or error
        if app_error is None and cleanup_error is not None:
            raise cleanup_error


def create_app() -> FastAPI:
    authorization_errors = authorization_config_errors()
    if authorization_errors:
        raise RuntimeError(f"Authorization config is invalid: {'; '.join(authorization_errors)}")
    injector = build_container()
    config = injector.get(Config)
    injector.get(AuthSettings)
    _setup_logging(config)
    docs_enabled = config.ENVIRONMENT.lower() in {"local", "development", "test"}
    app = FastAPI(
        title="Fast API Template",
        lifespan=lifespan,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.injector = injector
    app.add_middleware(CSRFMiddleware)
    register_error_handlers(app)
    # If CORS is enabled later, do not combine credentialed requests with wildcard origins.
    app = setup_routes(app)

    return app


def _setup_logging(config: Config) -> None:
    level_name = config.LOG_LEVEL.upper()
    level = logging.getLevelNamesMapping().get(level_name)
    if level is None:
        logger.warning(
            "Invalid LOG_LEVEL=%s; falling back to INFO",
            config.LOG_LEVEL,
        )
        level = logging.INFO
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("app").setLevel(level)
