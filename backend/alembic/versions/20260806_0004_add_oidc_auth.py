"""add oidc auth

Revision ID: 20260806_0004
Revises: 20260803_0003
Create Date: 2026-08-06 00:00:00.000000

Downgrade warning: this revision stores OIDC provider identities and pending
authorization states. Downgrading drops those tables and removes OIDC freshness
from auth sessions, which permanently deletes those bindings and pending flows.

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260806_0004"
down_revision: str | Sequence[str] | None = "20260803_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("email_verified", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("claims_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_identities_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_identities")),
    )
    op.create_index(
        "uq_auth_identities_provider_subject",
        "auth_identities",
        ["provider_id", "provider_subject"],
        unique=True,
    )
    op.create_index(
        "ix_auth_identities_user_id",
        "auth_identities",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "auth_oidc_authorization_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("browser_binding_hash", sa.String(length=64), nullable=False),
        sa.Column("nonce_hash", sa.String(length=64), nullable=False),
        sa.Column("pkce_verifier", sa.String(length=128), nullable=False),
        sa.Column("provider_id", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=64), nullable=False),
        sa.Column("expected_user_id", sa.Uuid(), nullable=True),
        sa.Column("expected_session_id", sa.Uuid(), nullable=True),
        sa.Column("redirect_path", sa.String(length=2048), nullable=False),
        sa.Column("login_hint", sa.String(length=320), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_oidc_authorization_states")),
    )
    op.create_index(
        "uq_auth_oidc_states_state_hash",
        "auth_oidc_authorization_states",
        ["state_hash"],
        unique=True,
    )
    op.create_index(
        "ix_auth_oidc_states_expires_at",
        "auth_oidc_authorization_states",
        ["expires_at"],
        unique=False,
    )
    op.create_index(
        "ix_auth_oidc_states_consumed_at",
        "auth_oidc_authorization_states",
        ["consumed_at"],
        unique=False,
    )

    op.add_column(
        "auth_sessions",
        sa.Column("last_oidc_auth_time_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("auth_sessions", "last_oidc_auth_time_at")

    op.drop_index("ix_auth_oidc_states_consumed_at", table_name="auth_oidc_authorization_states")
    op.drop_index("ix_auth_oidc_states_expires_at", table_name="auth_oidc_authorization_states")
    op.drop_index("uq_auth_oidc_states_state_hash", table_name="auth_oidc_authorization_states")
    op.drop_table("auth_oidc_authorization_states")

    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_index("uq_auth_identities_provider_subject", table_name="auth_identities")
    op.drop_table("auth_identities")
