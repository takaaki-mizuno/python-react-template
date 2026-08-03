"""phase5 auth operational fields

Revision ID: 20260803_0003
Revises: 20260802_0002
Create Date: 2026-08-03 14:27:04.212824

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260803_0003"
down_revision: Union[str, Sequence[str], None] = "20260802_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _drop_try_inet_function() -> None:
    op.execute("DROP FUNCTION IF EXISTS _phase5_try_inet(text)")


def _create_try_inet_function() -> None:
    op.execute("""
        CREATE OR REPLACE FUNCTION _phase5_try_inet(value text)
        RETURNS inet
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RETURN NULLIF(value, '')::inet;
        EXCEPTION WHEN others THEN
            RETURN NULL;
        END;
        $$;
        """)


def _null_invalid_inet_values(table_name: str) -> None:
    op.execute(
        sa.text(f"""
            UPDATE {table_name}
            SET ip_address = _phase5_try_inet(ip_address)::text
            WHERE ip_address IS NOT NULL
            """))


def upgrade() -> None:
    _create_try_inet_function()
    try:
        _null_invalid_inet_values("auth_audit_logs")
        _null_invalid_inet_values("auth_sessions")
    finally:
        _drop_try_inet_function()

    op.alter_column(
        "auth_audit_logs",
        "ip_address",
        existing_type=sa.VARCHAR(length=45),
        type_=postgresql.INET(),
        existing_nullable=True,
        postgresql_using="ip_address::inet",
    )
    op.create_index(
        "ix_auth_audit_logs_created_at",
        "auth_audit_logs",
        ["created_at"],
        unique=False,
    )
    op.drop_constraint(
        op.f("fk_auth_audit_logs_user_id_users"),
        "auth_audit_logs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_auth_audit_logs_session_id_auth_sessions"),
        "auth_audit_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_auth_audit_logs_user_id_users"),
        "auth_audit_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        op.f("fk_auth_audit_logs_session_id_auth_sessions"),
        "auth_audit_logs",
        "auth_sessions",
        ["session_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.add_column(
        "auth_sessions",
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "auth_sessions",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE auth_sessions SET issued_at = created_at WHERE issued_at IS NULL")
    op.execute("UPDATE auth_sessions SET updated_at = last_seen_at WHERE updated_at IS NULL")
    op.alter_column("auth_sessions", "issued_at", nullable=False)
    op.alter_column("auth_sessions", "updated_at", nullable=False)
    op.alter_column(
        "auth_sessions",
        "ip_address",
        existing_type=sa.VARCHAR(length=64),
        type_=postgresql.INET(),
        existing_nullable=True,
        postgresql_using="ip_address::inet",
    )
    op.create_index(
        "ix_auth_sessions_expires_at",
        "auth_sessions",
        ["expires_at"],
        unique=False,
    )
    op.drop_constraint(op.f("fk_auth_sessions_user_id_users"), "auth_sessions", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_auth_sessions_user_id_users"),
        "auth_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.add_column("users", sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_index(op.f("uq_users_email_lower"), table_name="users")
    op.create_index(
        "uq_users_email_lower_active",
        "users",
        [sa.literal_column("lower(email)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_users_email_lower_active", table_name="users")
    op.create_index(
        op.f("uq_users_email_lower"),
        "users",
        [sa.literal_column("lower(email)")],
        unique=True,
    )
    op.drop_column("users", "deleted_at")

    op.drop_constraint(op.f("fk_auth_sessions_user_id_users"), "auth_sessions", type_="foreignkey")
    op.create_foreign_key(
        op.f("fk_auth_sessions_user_id_users"),
        "auth_sessions",
        "users",
        ["user_id"],
        ["id"],
    )
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.alter_column(
        "auth_sessions",
        "ip_address",
        existing_type=postgresql.INET(),
        type_=sa.VARCHAR(length=64),
        existing_nullable=True,
        postgresql_using="ip_address::text",
    )
    op.drop_column("auth_sessions", "updated_at")
    op.drop_column("auth_sessions", "issued_at")

    op.drop_constraint(
        op.f("fk_auth_audit_logs_session_id_auth_sessions"),
        "auth_audit_logs",
        type_="foreignkey",
    )
    op.drop_constraint(
        op.f("fk_auth_audit_logs_user_id_users"),
        "auth_audit_logs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        op.f("fk_auth_audit_logs_session_id_auth_sessions"),
        "auth_audit_logs",
        "auth_sessions",
        ["session_id"],
        ["id"],
    )
    op.create_foreign_key(
        op.f("fk_auth_audit_logs_user_id_users"),
        "auth_audit_logs",
        "users",
        ["user_id"],
        ["id"],
    )
    op.drop_index("ix_auth_audit_logs_created_at", table_name="auth_audit_logs")
    op.alter_column(
        "auth_audit_logs",
        "ip_address",
        existing_type=postgresql.INET(),
        type_=sa.VARCHAR(length=45),
        existing_nullable=True,
        postgresql_using="ip_address::text",
    )
