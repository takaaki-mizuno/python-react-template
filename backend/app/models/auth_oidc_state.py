from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Text, Uuid
from sqlmodel import Field, SQLModel

from app.libraries.clock import utcnow
from app.libraries.sqlalchemy_types import UnixTimestampMillis


class AuthOidcState(SQLModel, table=True):
    __tablename__ = "auth_oidc_authorization_states"
    __table_args__ = (
        CheckConstraint(
            "language_code is null or language_code in ('en', 'ja')",
            name="language_code_supported",
        ),
        Index("uq_auth_oidc_states_state_hash", "state_hash", unique=True),
        Index("ix_auth_oidc_states_expires_at", "expires_at"),
        Index("ix_auth_oidc_states_consumed_at", "consumed_at"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    state_hash: str = Field(sa_column=Column(Text, nullable=False), )
    browser_binding_hash: str = Field(sa_column=Column(Text, nullable=False), )
    nonce_hash: str = Field(sa_column=Column(Text, nullable=False), )
    pkce_verifier: str = Field(sa_column=Column(Text, nullable=False), )
    provider_id: str = Field(sa_column=Column(Text, nullable=False), )
    purpose: str = Field(sa_column=Column(Text, nullable=False), )
    expected_user_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid,
            nullable=True,
            comment=
            "NULL means no authenticated user context was expected for this authorization state.",
        ),
    )
    expected_session_id: UUID | None = Field(
        default=None,
        sa_column=Column(
            Uuid,
            nullable=True,
            comment=("NULL means no authenticated session context was expected "
                     "for this authorization state."),
        ),
    )
    redirect_path: str = Field(sa_column=Column(Text, nullable=False), )
    login_hint: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
            comment="NULL means no login hint was provided to the authorization request.",
        ),
    )
    language_code: str | None = Field(
        default=None,
        sa_column=Column(
            Text,
            nullable=True,
            comment="NULL means no public language preference was captured.",
        ),
    )
    expires_at: datetime = Field(sa_column=Column(
        UnixTimestampMillis(),
        nullable=False,
        comment="Unix timestamp in milliseconds. Business time when the state expires.",
    ), )
    consumed_at: datetime | None = Field(
        default=None,
        sa_column=Column(
            UnixTimestampMillis(),
            nullable=True,
            comment="Unix timestamp in milliseconds. NULL means the state has not been consumed.",
        ),
    )
    created_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow), )
    updated_at: datetime = Field(sa_column=Column(DateTime(timezone=True),
                                                  nullable=False,
                                                  default=utcnow,
                                                  onupdate=utcnow), )


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
