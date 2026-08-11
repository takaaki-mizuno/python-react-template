"""initial schema

Revision ID: 20260810_0001
Revises:
Create Date: 2026-08-10 00:00:00.000000

This repository had no applied migrations when this revision was created, so
the previous development-only chain was squashed into one initial schema.

"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20260810_0001"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column(
            "password_hash",
            sa.Text(),
            nullable=True,
            comment="NULL means the user can authenticate only through external identity providers.",
        ),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column(
            "registered_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business registration time.",
        ),
        sa.Column(
            "modified_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business time when the user was last modified.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_logged_in_at",
            sa.BigInteger(),
            nullable=True,
            comment=
            "Unix timestamp in milliseconds. NULL means the user has never completed a login.",
        ),
        sa.Column(
            "deleted_at",
            sa.BigInteger(),
            nullable=True,
            comment="Unix timestamp in milliseconds. NULL means the user is not logically deleted.",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(
        "uq_users_email_lower_active",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_users_registered_at_id",
        "users",
        ["registered_at", "id"],
        unique=False,
    )

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_token_hash", sa.Text(), nullable=False),
        sa.Column("csrf_token_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "issued_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business time when the session was issued.",
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_seen_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business time when the session was last seen.",
        ),
        sa.Column(
            "expires_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business time when the session expires.",
        ),
        sa.Column(
            "revoked_at",
            sa.BigInteger(),
            nullable=True,
            comment="Unix timestamp in milliseconds. NULL means the session has not been revoked.",
        ),
        sa.Column(
            "last_oidc_authenticated_at",
            sa.BigInteger(),
            nullable=True,
            comment=("Unix timestamp in milliseconds. NULL means no fresh OIDC authentication "
                     "has been recorded for this session."),
        ),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
            comment=("NULL means the client IP could not be determined or should not be stored. "
                     "Stored as PostgreSQL INET by intentional schema-guideline deviation."),
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
            comment="NULL means the request did not include a user agent.",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_sessions")),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"], unique=False)
    op.create_index(
        "uq_auth_sessions_session_token_hash",
        "auth_sessions",
        ["session_token_hash"],
        unique=True,
    )
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"], unique=False)

    op.create_table(
        "auth_audit_logs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "user_id",
            sa.Uuid(),
            nullable=True,
            comment="NULL means the user row was deleted while the audit row is retained.",
        ),
        sa.Column(
            "session_id",
            sa.Uuid(),
            nullable=True,
            comment="NULL means the session row was deleted while the audit row is retained.",
        ),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "ip_address",
            postgresql.INET(),
            nullable=True,
            comment=("NULL means the client IP could not be determined or should not be stored. "
                     "Stored as PostgreSQL INET by intentional schema-guideline deviation."),
        ),
        sa.Column(
            "user_agent",
            sa.Text(),
            nullable=True,
            comment="NULL means the request did not include a user agent.",
        ),
        sa.Column(
            "detail_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            comment="NULL means the event has no details.",
        ),
        sa.Column(
            "occurred_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business occurrence time of the audit event.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["auth_sessions.id"],
            name=op.f("fk_auth_audit_logs_session_id_auth_sessions"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_auth_audit_logs_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_auth_audit_logs")),
    )
    op.create_index(
        "ix_auth_audit_logs_user_id",
        "auth_audit_logs",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_audit_logs_session_id",
        "auth_audit_logs",
        ["session_id"],
        unique=False,
    )
    op.create_index(
        "ix_auth_audit_logs_event_type",
        "auth_audit_logs",
        ["event_type"],
        unique=False,
    )
    op.create_index(
        "ix_auth_audit_logs_occurred_at",
        "auth_audit_logs",
        ["occurred_at"],
        unique=False,
    )

    op.create_table(
        "sample_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_user_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "description",
            sa.Text(),
            nullable=True,
            comment="NULL means the item has no description.",
        ),
        sa.Column("is_completed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column(
            "registered_at",
            sa.BigInteger(),
            nullable=False,
            comment=
            "Unix timestamp in milliseconds. Business registration time used for cursor ordering.",
        ),
        sa.Column(
            "modified_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business time when the item was last modified.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_user_id"],
            ["users.id"],
            name=op.f("fk_sample_items_owner_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sample_items")),
    )
    op.create_index(
        "ix_sample_items_owner_user_id",
        "sample_items",
        ["owner_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_sample_items_owner_user_id_registered_at_id",
        "sample_items",
        ["owner_user_id", "registered_at", "id"],
        unique=False,
    )

    op.create_table(
        "auth_identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("provider_subject", sa.Text(), nullable=False),
        sa.Column(
            "email",
            sa.Text(),
            nullable=True,
            comment="NULL means the identity provider did not return an email address.",
        ),
        sa.Column(
            "is_email_verified",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("claims_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "linked_at",
            sa.BigInteger(),
            nullable=False,
            comment=
            "Unix timestamp in milliseconds. Business time when the provider identity was linked.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_logged_in_at",
            sa.BigInteger(),
            nullable=True,
            comment=
            "Unix timestamp in milliseconds. NULL means the identity has never completed a login.",
        ),
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
        sa.Column("state_hash", sa.Text(), nullable=False),
        sa.Column("browser_binding_hash", sa.Text(), nullable=False),
        sa.Column("nonce_hash", sa.Text(), nullable=False),
        sa.Column("pkce_verifier", sa.Text(), nullable=False),
        sa.Column("provider_id", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column(
            "expected_user_id",
            sa.Uuid(),
            nullable=True,
            comment=
            "NULL means no authenticated user context was expected for this authorization state.",
        ),
        sa.Column(
            "expected_session_id",
            sa.Uuid(),
            nullable=True,
            comment=
            "NULL means no authenticated session context was expected for this authorization state.",
        ),
        sa.Column("redirect_path", sa.Text(), nullable=False),
        sa.Column(
            "login_hint",
            sa.Text(),
            nullable=True,
            comment="NULL means no login hint was provided to the authorization request.",
        ),
        sa.Column(
            "expires_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business time when the state expires.",
        ),
        sa.Column(
            "consumed_at",
            sa.BigInteger(),
            nullable=True,
            comment="Unix timestamp in milliseconds. NULL means the state has not been consumed.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
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

    op.create_table(
        "user_roles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.Text(), nullable=False),
        sa.Column(
            "assigned_at",
            sa.BigInteger(),
            nullable=False,
            comment="Unix timestamp in milliseconds. Business time when the role was assigned.",
        ),
        sa.Column(
            "assigned_by_user_id",
            sa.Uuid(),
            nullable=True,
            comment="NULL means the role was assigned by a system process or bootstrap operation.",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["assigned_by_user_id"],
            ["users.id"],
            name=op.f("fk_user_roles_assigned_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_user_roles_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_roles")),
    )
    op.create_index(
        "uq_user_roles_user_id_role_code",
        "user_roles",
        ["user_id", "role_code"],
        unique=True,
    )
    op.create_index("ix_user_roles_role_code", "user_roles", ["role_code"], unique=False)
    op.create_index(
        "ix_user_roles_assigned_by_user_id",
        "user_roles",
        ["assigned_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_user_roles_assigned_by_user_id", table_name="user_roles")
    op.drop_index("ix_user_roles_role_code", table_name="user_roles")
    op.drop_index("uq_user_roles_user_id_role_code", table_name="user_roles")
    op.drop_table("user_roles")

    op.drop_index("ix_auth_oidc_states_consumed_at", table_name="auth_oidc_authorization_states")
    op.drop_index("ix_auth_oidc_states_expires_at", table_name="auth_oidc_authorization_states")
    op.drop_index("uq_auth_oidc_states_state_hash", table_name="auth_oidc_authorization_states")
    op.drop_table("auth_oidc_authorization_states")

    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_index("uq_auth_identities_provider_subject", table_name="auth_identities")
    op.drop_table("auth_identities")

    op.drop_index("ix_sample_items_owner_user_id_registered_at_id", table_name="sample_items")
    op.drop_index("ix_sample_items_owner_user_id", table_name="sample_items")
    op.drop_table("sample_items")

    op.drop_index("ix_auth_audit_logs_occurred_at", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_event_type", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_session_id", table_name="auth_audit_logs")
    op.drop_index("ix_auth_audit_logs_user_id", table_name="auth_audit_logs")
    op.drop_table("auth_audit_logs")

    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("uq_auth_sessions_session_token_hash", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_index("ix_users_registered_at_id", table_name="users")
    op.drop_index("uq_users_email_lower_active", table_name="users")
    op.drop_table("users")
