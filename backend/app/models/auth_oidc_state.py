from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, Index, String, Uuid
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow


class AuthOidcState(SQLModel, table=True):
    __tablename__ = "auth_oidc_authorization_states"
    __table_args__ = (
        Index("uq_auth_oidc_states_state_hash", "state_hash", unique=True),
        Index("ix_auth_oidc_states_expires_at", "expires_at"),
        Index("ix_auth_oidc_states_consumed_at", "consumed_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    state_hash: str = Field(sa_column=Column(String(length=64), nullable=False), )
    browser_binding_hash: str = Field(sa_column=Column(String(length=64), nullable=False), )
    nonce_hash: str = Field(sa_column=Column(String(length=64), nullable=False), )
    pkce_verifier: str = Field(sa_column=Column(String(length=128), nullable=False), )
    provider_id: str = Field(sa_column=Column(String(length=64), nullable=False), )
    purpose: str = Field(sa_column=Column(String(length=64), nullable=False), )
    expected_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid, nullable=True),
    )
    expected_session_id: UUID | None = Field(
        default=None,
        sa_column=Column(Uuid, nullable=True),
    )
    redirect_path: str = Field(sa_column=Column(String(length=2048), nullable=False), )
    login_hint: str | None = Field(
        default=None,
        sa_column=Column(String(length=320), nullable=True),
    )
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False), )
    consumed_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )


AuthOidcStateConsumeStatus = Literal[
    "consumed",
    "state_mismatch",
    "expired",
    "already_consumed",
    "browser_binding_mismatch",
]


@dataclass(frozen=True)
class AuthOidcStateConsumeResult:
    status: AuthOidcStateConsumeStatus
    state: AuthOidcState | None = None
