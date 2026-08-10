from sqlmodel import SQLModel

import app.models  # noqa: F401

EXPECTED_TABLE_MODELS = {
    "users",
    "auth_sessions",
    "auth_audit_logs",
    "auth_identities",
    "auth_oidc_authorization_states",
    "sample_items",
    "user_roles",
}


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
    auth_identities = SQLModel.metadata.tables["auth_identities"]

    assert {constraint.name
            for constraint in auth_sessions.foreign_key_constraints
            } == {"fk_auth_sessions_user_id_users"}
    assert {constraint.name
            for constraint in auth_audit_logs.foreign_key_constraints} == {
                "fk_auth_audit_logs_user_id_users",
                "fk_auth_audit_logs_session_id_auth_sessions",
            }
    assert {constraint.name
            for constraint in auth_identities.foreign_key_constraints
            } == {"fk_auth_identities_user_id_users"}


def test_app_models_init_imports_all_table_models_for_alembic_metadata():
    assert set(SQLModel.metadata.tables) == EXPECTED_TABLE_MODELS
    assert len(SQLModel.metadata.tables) == len(EXPECTED_TABLE_MODELS)


def test_auth_operational_columns_are_registered_for_alembic_metadata():
    users = SQLModel.metadata.tables["users"]
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]

    assert "deleted_at" in users.c
    assert "issued_at" in auth_sessions.c
    assert "updated_at" in auth_sessions.c


def test_authorization_foreign_keys_have_deterministic_names():
    user_roles = SQLModel.metadata.tables["user_roles"]

    assert {constraint.name
            for constraint in user_roles.foreign_key_constraints} == {
                "fk_user_roles_assigned_by_user_id_users",
                "fk_user_roles_user_id_users",
            }


def test_authorization_table_shape_matches_plan():
    user_roles = SQLModel.metadata.tables["user_roles"]

    assert user_roles.c.role_code.type.length == 64
    assert user_roles.primary_key.columns.keys() == ["user_id", "role_code"]
    assert "role_id" not in user_roles.c
    assert {index.name for index in user_roles.indexes} == {"ix_user_roles_role_code"}
