from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.models.user import utcnow


class AuthAuditLog(SQLModel, table=True):
    __tablename__ = "auth_audit_logs"
    __table_args__ = (Index("ix_auth_audit_logs_event_type", "event_type"), )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID | None = Field(
        default=None,
        foreign_key="users.id",
        index=True,
        nullable=True,
    )
    session_id: UUID | None = Field(
        default=None,
        foreign_key="auth_sessions.id",
        index=True,
        nullable=True,
    )
    event_type: str = Field(sa_column=Column(String(length=64), nullable=False), )
    ip_address: str | None = Field(
        sa_column=Column(String(length=45), nullable=True),
        default=None,
    )
    user_agent: str | None = Field(
        sa_column=Column(String(length=512), nullable=True),
        default=None,
    )
    detail_json: dict | None = Field(
        default=None,
        sa_column=Column(JSONB, nullable=True),
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
