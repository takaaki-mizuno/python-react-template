from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Index, Text, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import InetString, UnixTimestampMillis


class AuthAuditLog(SQLModel, table=True):
    __tablename__ = "auth_audit_logs"
    __table_args__ = (
        Index("ix_auth_audit_logs_event_type", "event_type"),
        Index("ix_auth_audit_logs_occurred_at", "occurred_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid,
            ForeignKey("users.id", ondelete="SET NULL"),
            index=True,
            nullable=True,
            comment="NULL means the user row was deleted while the audit row is retained.",
        ),
    )
    session_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid,
            ForeignKey("auth_sessions.id", ondelete="SET NULL"),
            index=True,
            nullable=True,
            comment="NULL means the session row was deleted while the audit row is retained.",
        ),
    )
    event_type: str = Field(sa_column=Column(Text, nullable=False), )
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
    detail_json: dict | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True, comment="NULL means the event has no details."),
    )
    occurred_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        default=utcnow,
        comment="Unix timestamp in milliseconds. Business occurrence time of the audit event.",
    ), )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )
