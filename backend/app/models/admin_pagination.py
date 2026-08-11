from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class AdminOffsetPageRequest:
    offset: int
    limit: int


@dataclass(frozen=True)
class AdminOffsetPageResult(Generic[T]):  # noqa: UP046
    items: list[T]
    total: int
    offset: int
    limit: int
