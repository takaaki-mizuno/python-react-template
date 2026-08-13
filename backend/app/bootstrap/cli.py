import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar

from injector import Injector
from sqlalchemy.ext.asyncio import AsyncEngine

from app.bootstrap.container import build_container
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface

T = TypeVar("T")
logger = logging.getLogger(__name__)


async def run_with_container(operation: Callable[[Injector], Awaitable[T]]) -> T:  # noqa: UP047
    container = build_container()
    try:
        return await operation(container)
    finally:
        try:
            await container.get(LoginRateLimiterInterface).aclose()
        except Exception:
            logger.exception("Failed to close CLI rate limiter")
        try:
            await container.get(AsyncEngine).dispose()
        except Exception:
            logger.exception("Failed to dispose CLI database engine")
