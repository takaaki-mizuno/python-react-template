from typing import get_args

from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.models.user import User


def test_auth_models_are_registered_for_alembic():
    assert {"users", "auth_sessions", "auth_audit_logs"}.issubset(SQLModel.metadata.tables.keys())


def test_auth_datetime_columns_are_timezone_aware():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert users.c.created_at.type.timezone is True
    assert users.c.updated_at.type.timezone is True
    assert auth_sessions.c.expires_at.type.timezone is True
    assert auth_sessions.c.revoked_at.type.timezone is True
    assert auth_audit_logs.c.created_at.type.timezone is True


def test_auth_model_metadata_matches_auth_migration_indexes_and_defaults():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert "uq_users_email_lower" in {index.name for index in users.indexes}
    assert "uq_auth_sessions_session_token_hash" in {index.name for index in auth_sessions.indexes}
    assert "ix_auth_audit_logs_event_type" in {index.name for index in auth_audit_logs.indexes}
    assert users.c.is_active.server_default is not None


def test_user_password_hash_is_nullable_for_oauth_only_users():
    users = SQLModel.metadata.tables["users"]

    assert users.c.password_hash.nullable is True
    assert type(None) in get_args(User.model_fields["password_hash"].annotation)
