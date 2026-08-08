from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Uuid
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow


class Role(SQLModel, table=True):
    __tablename__ = "roles"
    __table_args__ = (Index("uq_roles_code", "code", unique=True), )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(sa_column=Column(String(length=64), nullable=False))
    display_name: str = Field(sa_column=Column(String(length=120), nullable=False))
    description: str | None = Field(
        default=None,
        sa_column=Column(String(length=500), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow))


class Permission(SQLModel, table=True):
    __tablename__ = "permissions"
    __table_args__ = (Index("uq_permissions_code", "code", unique=True), )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    code: str = Field(sa_column=Column(String(length=120), nullable=False))
    display_name: str = Field(sa_column=Column(String(length=120), nullable=False))
    description: str | None = Field(
        default=None,
        sa_column=Column(String(length=500), nullable=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow))
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow))


class UserRole(SQLModel, table=True):
    __tablename__ = "user_roles"
    __table_args__ = (Index("ix_user_roles_role_id", "role_id"), )

    user_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ))
    role_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ))
    assigned_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow))
    assigned_by_user_id: UUID | None = Field(default=None,
                                             sa_column=Column(
                                                 Uuid,
                                                 ForeignKey("users.id", ondelete="SET NULL"),
                                                 nullable=True,
                                             ))


class RolePermission(SQLModel, table=True):
    __tablename__ = "role_permissions"
    __table_args__ = (Index("ix_role_permissions_permission_id", "permission_id"), )

    role_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("roles.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ))
    permission_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("permissions.id", ondelete="CASCADE"),
        nullable=False,
        primary_key=True,
    ))
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow))


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
    current_permission_codes: tuple[str, ...]
