from sqlmodel import SQLModel

import app.models  # noqa: F401


def test_auth_models_are_registered_for_alembic():
    assert {"users", "auth_sessions",
            "auth_audit_logs"}.issubset(SQLModel.metadata.tables.keys())


def test_auth_datetime_columns_are_timezone_aware():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert users.c.created_at.type.timezone is True
    assert users.c.updated_at.type.timezone is True
    assert auth_sessions.c.expires_at.type.timezone is True
    assert auth_sessions.c.revoked_at.type.timezone is True
    assert auth_audit_logs.c.created_at.type.timezone is True
