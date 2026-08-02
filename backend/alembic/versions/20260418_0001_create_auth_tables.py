"""create auth tables

Revision ID: 20260418_0001
Revises:
Create Date: 2026-04-18 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260418_0001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=True),
        sa.Column("is_active",
                  sa.Boolean(),
                  server_default=sa.true(),
                  nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_auth_sessions_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_auth_sessions"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index(
        "uq_auth_sessions_session_token_hash",
        "auth_sessions",
        ["session_token_hash"],
        unique=True,
    )

    op.create_table(
        "auth_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("ip_address", sa.String(length=45), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("detail_json",
                  postgresql.JSONB(astext_type=sa.Text()),
                  nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            name="fk_auth_audit_logs_session_id_auth_sessions",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"],
                                name="fk_auth_audit_logs_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_auth_audit_logs"),
    )
    op.create_index("ix_auth_audit_logs_user_id", "auth_audit_logs",
                    ["user_id"])
    op.create_index("ix_auth_audit_logs_session_id", "auth_audit_logs",
                    ["session_id"])
    op.create_index("ix_auth_audit_logs_event_type", "auth_audit_logs",
                    ["event_type"])


def downgrade() -> None:
    op.drop_index("ix_auth_audit_logs_event_type",
                  table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_session_id",
                  table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_user_id", table_name="auth_audit_logs")
    op.drop_table("auth_audit_logs")
    op.drop_index("uq_auth_sessions_session_token_hash",
                  table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("uq_users_email_lower", table_name="users")
    op.drop_table("users")
