from dataclasses import dataclass
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, Uuid
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import UnixTimestampMillis


class UserRole(SQLModel, table=True):
    __tablename__ = "user_roles"
    __table_args__ = (
        Index("uq_user_roles_user_id_role_code", "user_id", "role_code", unique=True),
        Index("ix_user_roles_role_code", "role_code"),
        Index("ix_user_roles_assigned_by_user_id", "assigned_by_user_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ))
    role_code: str = Field(sa_column=Column(Text, nullable=False))
    assigned_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        default=utcnow,
        comment="Unix timestamp in milliseconds. Business time when the role was assigned.",
    ))
    assigned_by_user_id: UUID | None = Field(default=None,
                                             sa_column=Column(
                                                 Uuid,
                                                 ForeignKey("users.id", ondelete="SET NULL"),
                                                 nullable=True,
                                                 comment=("NULL means the role was assigned by a "
                                                          "system process or bootstrap operation."),
                                             ))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )


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
