from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, Index, String, text
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow


class User(SQLModel, table=True):
    __tablename__ = "users"
    __table_args__ = (Index(
        "uq_users_email_lower_active",
        text("lower(email)"),
        unique=True,
        postgresql_where=text("deleted_at IS NULL"),
    ), )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(sa_column=Column(String(length=320), nullable=False), )
    password_hash: str | None = Field(
        default=None,
        sa_column=Column(String(length=255), nullable=True),
    )
    is_active: bool = Field(sa_column=Column(Boolean,
                                             nullable=False,
                                             default=True,
                                             server_default=text("true")), )
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
    deleted_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True),
        default=None,
    )
