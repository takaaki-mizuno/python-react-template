from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, String, Uuid, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow


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
    provider_id: str = Field(sa_column=Column(String(length=64), nullable=False), )
    provider_subject: str = Field(sa_column=Column(String(length=255), nullable=False), )
    email: str | None = Field(
        default=None,
        sa_column=Column(String(length=320), nullable=True),
    )
    email_verified: bool = Field(sa_column=Column(Boolean,
                                                  nullable=False,
                                                  default=False,
                                                  server_default=text("false")), )
    claims_json: dict = Field(default_factory=dict, sa_column=Column(JSONB, nullable=False))
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )
    last_login_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True),
        default=None,
    )
