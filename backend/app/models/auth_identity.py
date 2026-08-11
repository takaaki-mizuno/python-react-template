from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Text, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import UnixTimestampMillis


class AuthIdentity(SQLModel, table=True):
    __tablename__ = "auth_identities"
    __table_args__ = (
        Index(
            "uq_auth_identities_provider_subject",
            "provider_id",
            "provider_subject",
            unique=True,
        ),
        Index("ix_auth_identities_user_id", "user_id"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    ), )
    provider_id: str = Field(sa_column=Column(Text, nullable=False), )
    provider_subject: str = Field(sa_column=Column(Text, nullable=False), )
    email: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
            comment="NULL means the identity provider did not return an email address.",
        ),
    )
    is_email_verified: bool = Field(sa_column=Column(Boolean,
                                                     nullable=False,
                                                     default=False,
                                                     server_default=text("false")), )
    claims_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    linked_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        default=utcnow,
        comment=
        "Unix timestamp in milliseconds. Business time when the provider identity was linked.",
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
            "Unix timestamp in milliseconds. NULL means the identity has never completed a login.",
        ),
        default=None,
    )
