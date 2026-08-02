from collections.abc import Callable
from typing import TypeVar

from fastapi import Request

T = TypeVar("T")


def inject(interface: type[T]) -> Callable[[Request], T]:

    def _resolve(request: Request) -> T:
        return request.app.state.injector.get(interface)

    return _resolve
