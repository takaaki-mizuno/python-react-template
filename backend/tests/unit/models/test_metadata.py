from sqlalchemy import DateTime, String, Text
from sqlmodel import SQLModel

import app.models  # noqa: F401
from app.libraries.sqlalchemy_types import InetString, UnixTimestampMillis

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


def test_all_table_models_use_id_primary_key():
    for table_name, table in SQLModel.metadata.tables.items():
        assert table.primary_key.columns.keys() == ["id"], table_name


def test_all_table_models_have_logging_timestamps():
    for table_name, table in SQLModel.metadata.tables.items():
        for column_name in ("created_at", "updated_at"):
            assert column_name in table.c, f"{table_name}.{column_name}"
            column_type = table.c[column_name].type
            assert isinstance(column_type, DateTime), f"{table_name}.{column_name}"
            assert column_type.timezone is True, f"{table_name}.{column_name}"


def test_nullable_columns_document_null_semantics():
    for table in SQLModel.metadata.tables.values():
        for column in table.c:
            if column.nullable:
                assert column.comment, f"{table.name}.{column.name}"


def test_business_timestamps_document_millisecond_units():
    for table in SQLModel.metadata.tables.values():
        for column in table.c:
            if isinstance(column.type, UnixTimestampMillis):
                assert column.comment is not None
                assert "Unix timestamp in milliseconds." in column.comment


def test_textual_columns_use_text_not_varchar():
    offenders = []
    for table in SQLModel.metadata.tables.values():
        for column in table.c:
            if isinstance(column.type, String) and not isinstance(column.type, Text):
                offenders.append(f"{table.name}.{column.name}: {column.type!r}")

    assert offenders == []


def test_foreign_key_columns_have_leading_indexes():
    for table in SQLModel.metadata.tables.values():
        indexed_column_names = {
            index.columns.keys()[0]
            for index in table.indexes if index.columns.keys()
        }
        for column in table.c:
            if column.foreign_keys:
                assert column.name in indexed_column_names, f"{table.name}.{column.name}"


def test_oidc_expected_context_columns_are_unindexed_soft_references():
    states = SQLModel.metadata.tables["auth_oidc_authorization_states"]
    index_names = {index.name for index in states.indexes}

    for column_name in ("expected_user_id", "expected_session_id"):
        assert not states.c[column_name].foreign_keys
        assert states.c[column_name].comment

    assert "ix_auth_oidc_states_expected_user_id" not in index_names
    assert "ix_auth_oidc_states_expected_session_id" not in index_names
    assert "ix_auth_oidc_authorization_states_expected_user_id" not in index_names
    assert "ix_auth_oidc_authorization_states_expected_session_id" not in index_names


def test_ip_address_columns_keep_postgresql_inet_intentional_deviation():
    auth_sessions = SQLModel.metadata.tables["auth_sessions"]
    auth_audit_logs = SQLModel.metadata.tables["auth_audit_logs"]

    assert isinstance(auth_sessions.c.ip_address.type, InetString)
    assert isinstance(auth_audit_logs.c.ip_address.type, InetString)


def test_authorization_foreign_keys_have_deterministic_names():
    user_roles = SQLModel.metadata.tables["user_roles"]

    assert {constraint.name
            for constraint in user_roles.foreign_key_constraints} == {
                "fk_user_roles_assigned_by_user_id_users",
                "fk_user_roles_user_id_users",
            }


def test_authorization_table_shape_matches_plan():
    user_roles = SQLModel.metadata.tables["user_roles"]

    assert isinstance(user_roles.c.role_code.type, Text)
    assert user_roles.primary_key.columns.keys() == ["id"]
    assert "role_id" not in user_roles.c
    index_names = {index.name for index in user_roles.indexes}
    assert "uq_user_roles_user_id_role_code" in index_names
    assert "ix_user_roles_role_code" in index_names
    assert "ix_user_roles_assigned_by_user_id" in index_names
