from dataclasses import dataclass, field

from app.models.user import User


@dataclass(frozen=True, slots=True)
class AdminUserListQuery:
    search: str | None = None
    is_active: bool | None = None
    role: str | None = None


@dataclass(frozen=True, slots=True)
class AdminUserRecord:
    user: User
    roles: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminUserDetail:
    user: User
    roles: tuple[str, ...]
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AdminUserUpdateChanges:
    email: str | None = None
    password: str | None = None
    is_active: bool | None = None
    roles: tuple[str, ...] | None = None
    fields_set: frozenset[str] = field(default_factory=frozenset)
