from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Uuid
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow


class UserRole(SQLModel, table=True):
    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_code", "role_code"), )

    user_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ))
    role_code: str = Field(sa_column=Column(String(length=64), nullable=False, primary_key=True))
    assigned_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow))
    assigned_by_user_id: UUID | None = Field(default=None,
                                             sa_column=Column(
                                                 Uuid,
                                                 ForeignKey("users.id", ondelete="SET NULL"),
                                                 nullable=True,
                                             ))


@dataclass(frozen=True, slots=True)
class RoleDefinition:
    code: str
    display_name: str
    description: str | None = None
    permission_codes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class PermissionDefinition:
    code: str
    display_name: str
    description: str | None = None


@dataclass(frozen=True, slots=True)
class UserAuthorization:
    user_id: UUID
    roles: frozenset[str]
    permissions: frozenset[str]


@dataclass(frozen=True, slots=True)
class RoleWithPermissions:
    code: str
    display_name: str
    description: str | None
    permissions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UserRoleReplacementResult:
    user_id: UUID
    granted_role_codes: tuple[str, ...]
    revoked_role_codes: tuple[str, ...]
    current_role_codes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UnknownRoleAssignment:
    user_id: UUID
    role_code: str
