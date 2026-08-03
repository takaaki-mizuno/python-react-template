from sqlmodel import SQLModel

import app.models  # noqa: F401


def test_sqlmodel_metadata_uses_naming_convention():
    assert SQLModel.metadata.naming_convention == {
        "ix": "ix_%(table_name)s_%(column_0_N_name)s",
        "uq": "uq_%(table_name)s_%(column_0_N_name)s",
        "ck": "ck_%(table_name)s_%(constraint_name)s",
        "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
        "pk": "pk_%(table_name)s",
    }


def test_auth_foreign_keys_have_deterministic_names():
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert {constraint.name
            for constraint in auth_sessions.foreign_key_constraints
            } == {"fk_auth_sessions_user_id_users"}
    assert {constraint.name
            for constraint in auth_audit_logs.foreign_key_constraints} == {
                "fk_auth_audit_logs_user_id_users",
                "fk_auth_audit_logs_session_id_auth_sessions",
            }
