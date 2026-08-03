from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, String, Uuid
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import InetString


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
    session_token_hash: str = Field(sa_column=Column(String(length=64), nullable=False), )
    csrf_token_hash: str = Field(sa_column=Column(String(length=64), nullable=False), )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    issued_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                 nullable=False,
                                                 default=utcnow), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )
    last_seen_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                    nullable=False,
                                                    default=utcnow), )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False), )
    revoked_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True),
        default=None,
    )
    ip_address: str | None = Field(
        sa_column=Column(InetString(), nullable=True),
        default=None,
    )
    user_agent: str | None = Field(
        sa_column=Column(String(length=512), nullable=True),
        default=None,
    )
