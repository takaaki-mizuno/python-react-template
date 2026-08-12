from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, Text, text
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import UnixTimestampMillis
from app.models.language import DEFAULT_LANGUAGE_CODE, LanguageCode


@dataclass(frozen=True, slots=True)
class AuthUserUpdateChanges:
    language_code: LanguageCode | None = field(default=None)
    fields_set: frozenset[str] = field(default_factory=frozenset)


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "language_code in ('en', 'ja')",
            name="language_code_supported",
        ),
        Index(
            "uq_users_email_lower_active",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index("ix_users_registered_at_id", "registered_at", "id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(sa_column=Column(Text, nullable=False), )
    password_hash: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
            comment=("NULL means the user can authenticate only through "
                     "external identity providers."),
        ),
    )
    is_active: bool = Field(sa_column=Column(Boolean,
                                             nullable=False,
                                             default=True,
                                             server_default=text("true")), )
    language_code: str = Field(
        default=DEFAULT_LANGUAGE_CODE,
        sa_column=Column(
            Text,
            nullable=False,
            server_default=text("'ja'"),
            comment="User interface language code.",
        ),
    )
    registered_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        default=utcnow,
        comment="Unix timestamp in milliseconds. Business registration time.",
    ), )
    modified_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        default=utcnow,
        comment="Unix timestamp in milliseconds. Business time when the user was last modified.",
    ), )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )
    last_logged_in_at: datetime | None = Field(
        sa_column=Column(
            UnixTimestampMillis(),
            nullable=True,
            comment=
            "Unix timestamp in milliseconds. NULL means the user has never completed a login.",
        ),
        default=None,
    )
    deleted_at: datetime | None = Field(
        sa_column=Column(
            UnixTimestampMillis(),
            nullable=True,
            comment="Unix timestamp in milliseconds. NULL means the user is not logically deleted.",
        ),
        default=None,
    )
