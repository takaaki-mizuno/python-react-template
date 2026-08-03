from collections.abc import Callable
from typing import TypeVar, cast

from fastapi import Request

T = TypeVar("T")


def inject(interface: type[T]) -> Callable[[Request], T]:  # noqa: UP047

    def _resolve(request: Request) -> T:
        return cast(T, request.app.state.injector.get(interface))

    return _resolve
