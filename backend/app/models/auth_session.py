from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, Uuid
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import InetString, UnixTimestampMillis


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"
    __table_args__ = (
        Index(
            "uq_auth_sessions_session_token_hash",
            "session_token_hash",
            unique=True,
        ),
        Index("ix_auth_sessions_expires_at", "expires_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(sa_column=Column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ), )
    session_token_hash: str = Field(sa_column=Column(Text, nullable=False), )
    csrf_token_hash: str = Field(sa_column=Column(Text, nullable=False), )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    issued_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        default=utcnow,
        comment="Unix timestamp in milliseconds. Business time when the session was issued.",
    ), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )
    last_seen_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        default=utcnow,
        comment="Unix timestamp in milliseconds. Business time when the session was last seen.",
    ), )
    expires_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        comment="Unix timestamp in milliseconds. Business time when the session expires.",
    ), )
    revoked_at: datetime | None = Field(
        sa_column=Column(
            UnixTimestampMillis(),
            nullable=True,
            comment="Unix timestamp in milliseconds. NULL means the session has not been revoked.",
        ),
        default=None,
    )
    last_oidc_authenticated_at: datetime | None = Field(
        sa_column=Column(
            UnixTimestampMillis(),
            nullable=True,
            comment=("Unix timestamp in milliseconds. NULL means no fresh OIDC authentication "
                     "has been recorded for this session."),
        ),
        default=None,
    )
    ip_address: str | None = Field(
        sa_column=Column(
            InetString(),
            nullable=True,
            comment=("NULL means the client IP could not be determined or should not be stored. "
                     "Stored as PostgreSQL INET by intentional schema-guideline deviation."),
        ),
        default=None,
    )
    user_agent: str | None = Field(
        sa_column=Column(
            Text,
            nullable=True,
            comment="NULL means the request did not include a user agent.",
        ),
        default=None,
    )
