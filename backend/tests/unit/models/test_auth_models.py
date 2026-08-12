from typing import get_args

from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.libraries.sqlalchemy_types import InetString, UnixTimestampMillis
from app.models.user import User


def test_auth_models_are_registered_for_alembic():
    assert {"users", "auth_sessions", "auth_audit_logs"}.issubset(SQLModel.metadata.tables.keys())


def test_auth_datetime_columns_are_timezone_aware():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert users.c.created_at.type.timezone is True
    assert users.c.updated_at.type.timezone is True
    assert auth_sessions.c.updated_at.type.timezone is True
    assert auth_audit_logs.c.created_at.type.timezone is True
    assert auth_audit_logs.c.updated_at.type.timezone is True


def test_auth_business_timestamp_columns_use_unix_timestamp_millis():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]
    auth_identities = SQLModel.metadata.tables["auth_identities"]

    expected_columns = (
        users.c.registered_at,
        users.c.modified_at,
        users.c.last_logged_in_at,
        users.c.deleted_at,
        auth_sessions.c.issued_at,
        auth_sessions.c.last_seen_at,
        auth_sessions.c.expires_at,
        auth_sessions.c.revoked_at,
        auth_sessions.c.last_oidc_authenticated_at,
        auth_audit_logs.c.occurred_at,
        auth_identities.c.linked_at,
        auth_identities.c.last_logged_in_at,
    )

    for column in expected_columns:
        assert isinstance(column.type, UnixTimestampMillis), column.name


def test_auth_identity_uses_prefixed_email_verified_flag():
    auth_identities = SQLModel.metadata.tables["auth_identities"]

    assert "is_email_verified" in auth_identities.c
    assert "email_verified" not in auth_identities.c


def test_auth_model_metadata_matches_auth_migration_indexes_and_defaults():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    index_names = {index.name for index in users.indexes}

    assert "uq_users_email_lower_active" in index_names
    assert "uq_auth_sessions_session_token_hash" in {index.name for index in auth_sessions.indexes}
    assert "ix_auth_audit_logs_event_type" in {index.name for index in auth_audit_logs.indexes}
    assert "ix_auth_sessions_expires_at" in {index.name for index in auth_sessions.indexes}
    assert "ix_auth_audit_logs_occurred_at" in {index.name for index in auth_audit_logs.indexes}
    assert users.c.is_active.server_default is not None


def test_user_language_code_metadata():
    users = SQLModel.metadata.tables["users"]
    constraint_names = {constraint.name for constraint in users.constraints}

    assert users.c.language_code.nullable is False
    assert str(users.c.language_code.type) == "TEXT"
    assert users.c.language_code.server_default is not None
    assert "ck_users_language_code_supported" in constraint_names


def test_user_deleted_at_and_active_email_unique_index_metadata():
    users = SQLModel.metadata.tables["users"]
    active_email_index = next(index for index in users.indexes
                              if index.name == "uq_users_email_lower_active")

    assert users.c.updated_at.onupdate is not None
    assert users.c.deleted_at.nullable is True
    assert isinstance(users.c.deleted_at.type, UnixTimestampMillis)
    assert active_email_index.unique is True
    assert "deleted_at IS NULL" in str(active_email_index.dialect_options["postgresql"]["where"])


def test_auth_session_operational_fields_metadata():
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]

    assert auth_sessions.c.issued_at.nullable is False
    assert auth_sessions.c.updated_at.nullable is False
    assert auth_sessions.c.updated_at.onupdate is not None
    assert isinstance(auth_sessions.c.ip_address.type, InetString)


def test_auth_audit_log_operational_fields_metadata():
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert isinstance(auth_audit_logs.c.ip_address.type, InetString)


def test_user_password_hash_is_nullable_for_oauth_only_users():
    users = SQLModel.metadata.tables["users"]

    assert users.c.password_hash.nullable is True
    assert type(None) in get_args(User.model_fields["password_hash"].annotation)
