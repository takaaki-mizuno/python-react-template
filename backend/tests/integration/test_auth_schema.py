from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlmodel import select

from app.libraries.clock import utcnow
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_session import AuthSession
from app.models.user import User

pytestmark = pytest.mark.integration

APPLICATION_TABLES = {
    "auth_audit_logs",
    "auth_identities",
    "auth_oidc_authorization_states",
    "auth_sessions",
    "sample_items",
    "user_roles",
    "users",
}

BUSINESS_TIMESTAMP_COLUMNS = {
    ("auth_audit_logs", "occurred_at"),
    ("auth_identities", "linked_at"),
    ("auth_identities", "last_logged_in_at"),
    ("auth_oidc_authorization_states", "expires_at"),
    ("auth_oidc_authorization_states", "consumed_at"),
    ("auth_sessions", "issued_at"),
    ("auth_sessions", "last_seen_at"),
    ("auth_sessions", "expires_at"),
    ("auth_sessions", "revoked_at"),
    ("auth_sessions", "last_oidc_authenticated_at"),
    ("sample_items", "registered_at"),
    ("sample_items", "modified_at"),
    ("user_roles", "assigned_at"),
    ("users", "registered_at"),
    ("users", "modified_at"),
    ("users", "last_logged_in_at"),
    ("users", "deleted_at"),
}


async def test_auth_tables_exist(async_session):
    result = await async_session.execute(
        text("""
            select table_name
            from information_schema.tables
            where table_schema = 'public'
              and table_name in ('users', 'auth_sessions', 'auth_audit_logs')
            order by table_name
            """))

    assert [row[0] for row in result.fetchall()] == [
        "auth_audit_logs",
        "auth_sessions",
        "users",
    ]


async def test_users_email_has_lower_active_unique_index(async_session):
    result = await async_session.execute(
        text("""
            select indexdef
            from pg_indexes
            where schemaname = 'public'
              and tablename = 'users'
            """))

    index_definitions = [row[0] for row in result.fetchall()]
    assert any(
        "CREATE UNIQUE INDEX uq_users_email_lower_active" in definition and "lower" in definition.
        lower() and "email" in definition.lower() and "WHERE (deleted_at IS NULL)" in definition
        for definition in index_definitions)


async def test_session_token_hash_has_unique_lookup_index(async_session):
    result = await async_session.execute(
        text("""
            select indexdef
            from pg_indexes
            where schemaname = 'public'
              and tablename = 'auth_sessions'
            """))

    index_definitions = [row[0] for row in result.fetchall()]
    assert any("UNIQUE INDEX" in definition and "session_token_hash" in definition
               for definition in index_definitions)


async def test_all_application_tables_have_id_pk_and_logging_timestamps(async_session):
    table_placeholders = ", ".join(f"'{table}'" for table in sorted(APPLICATION_TABLES))
    pk_result = await async_session.execute(
        text(f"""
            select tc.table_name, kcu.column_name
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name
             and tc.table_schema = kcu.table_schema
             and tc.table_name = kcu.table_name
            where tc.table_schema = 'public'
              and tc.table_name in ({table_placeholders})
              and tc.constraint_type = 'PRIMARY KEY'
            order by tc.table_name, kcu.ordinal_position
        """))
    assert [(row.table_name, row.column_name) for row in pk_result.fetchall()
            ] == [(table, "id") for table in sorted(APPLICATION_TABLES)]

    timestamp_result = await async_session.execute(
        text(f"""
            select table_name, column_name, data_type
            from information_schema.columns
            where table_schema = 'public'
              and table_name in ({table_placeholders})
              and column_name in ('created_at', 'updated_at')
            order by table_name, column_name
        """))
    rows = timestamp_result.fetchall()
    assert len(rows) == len(APPLICATION_TABLES) * 2
    assert all(row.data_type == "timestamp with time zone" for row in rows)


async def test_auth_timestamps_use_guideline_storage_types(async_session):
    result = await async_session.execute(
        text("""
            select table_name, column_name, data_type
            from information_schema.columns
            where table_schema = 'public'
              and (
                (table_name = 'auth_sessions'
                 and column_name in (
                   'created_at', 'issued_at', 'updated_at',
                   'last_seen_at', 'expires_at', 'revoked_at',
                   'last_oidc_authenticated_at'
                 ))
                or
                (table_name = 'auth_audit_logs'
                 and column_name in ('occurred_at', 'created_at', 'updated_at'))
                or
                (table_name = 'users'
                 and column_name in (
                   'registered_at', 'created_at', 'updated_at',
                   'modified_at', 'last_logged_in_at', 'deleted_at'
                 ))
                or
                (table_name = 'sample_items'
                 and column_name in ('registered_at', 'modified_at', 'created_at', 'updated_at'))
              )
            """))

    rows = result.fetchall()
    assert len(rows) == 20
    expected_bigint = {
        ("auth_audit_logs", "occurred_at"),
        ("auth_sessions", "issued_at"),
        ("auth_sessions", "last_seen_at"),
        ("auth_sessions", "expires_at"),
        ("auth_sessions", "revoked_at"),
        ("auth_sessions", "last_oidc_authenticated_at"),
        ("sample_items", "registered_at"),
        ("sample_items", "modified_at"),
        ("users", "registered_at"),
        ("users", "modified_at"),
        ("users", "last_logged_in_at"),
        ("users", "deleted_at"),
    }
    for row in rows:
        if (row.table_name, row.column_name) in expected_bigint:
            assert row.data_type == "bigint"
        else:
            assert row.data_type == "timestamp with time zone"


async def test_business_timestamps_are_bigint_with_milliseconds_comments(async_session):
    result = await async_session.execute(
        text("""
            select c.table_name,
                   c.column_name,
                   c.data_type,
                   col_description(format('%I.%I', c.table_schema, c.table_name)::regclass::oid,
                                   c.ordinal_position) as comment
            from information_schema.columns c
            where c.table_schema = 'public'
            order by c.table_name, c.column_name
        """))

    rows = {
        (row.table_name, row.column_name): (row.data_type, row.comment)
        for row in result.fetchall()
    }
    for table_name, column_name in BUSINESS_TIMESTAMP_COLUMNS:
        data_type, comment = rows[(table_name, column_name)]
        assert data_type == "bigint"
        assert "Unix timestamp in milliseconds." in comment


async def test_nullable_columns_have_comments(async_session):
    table_placeholders = ", ".join(f"'{table}'" for table in sorted(APPLICATION_TABLES))
    result = await async_session.execute(
        text(f"""
            select c.table_name,
                   c.column_name,
                   col_description(format('%I.%I', c.table_schema, c.table_name)::regclass::oid,
                                   c.ordinal_position) as comment
            from information_schema.columns c
            where c.table_schema = 'public'
              and c.table_name in ({table_placeholders})
              and c.is_nullable = 'YES'
            order by c.table_name, c.column_name
        """))

    rows = result.fetchall()
    assert rows
    assert all(row.comment for row in rows)


async def test_textual_columns_use_text_not_varchar(async_session):
    table_placeholders = ", ".join(f"'{table}'" for table in sorted(APPLICATION_TABLES))
    result = await async_session.execute(
        text(f"""
            select table_name, column_name, data_type
            from information_schema.columns
            where table_schema = 'public'
              and table_name in ({table_placeholders})
              and data_type in ('character varying', 'character')
            order by table_name, column_name
        """))

    assert result.fetchall() == []


async def test_timestamp_columns_have_no_database_defaults(async_session):
    table_placeholders = ", ".join(f"'{table}'" for table in sorted(APPLICATION_TABLES))
    result = await async_session.execute(
        text(f"""
            select table_name, column_name, column_default
            from information_schema.columns
            where table_schema = 'public'
              and table_name in ({table_placeholders})
              and (
                column_name in ('created_at', 'updated_at')
                or data_type = 'bigint'
              )
            order by table_name, column_name
        """))

    assert all(row.column_default is None for row in result.fetchall())


async def test_user_roles_schema_matches_code_managed_rbac(async_session):
    pk_result = await async_session.execute(
        text("""
            select kcu.column_name
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name
             and tc.table_schema = kcu.table_schema
             and tc.table_name = kcu.table_name
            where tc.table_schema = 'public'
              and tc.table_name = 'user_roles'
              and tc.constraint_type = 'PRIMARY KEY'
            order by kcu.ordinal_position
        """))
    assert [row.column_name for row in pk_result.fetchall()] == ["id"]

    index_result = await async_session.execute(
        text("""
            select indexname, indexdef
            from pg_indexes
            where schemaname = 'public'
              and tablename = 'user_roles'
        """))
    indexes = {row.indexname: row.indexdef for row in index_result.fetchall()}
    assert "uq_user_roles_user_id_role_code" in indexes
    assert "UNIQUE" in indexes["uq_user_roles_user_id_role_code"]
    assert "user_id" in indexes["uq_user_roles_user_id_role_code"]
    assert "role_code" in indexes["uq_user_roles_user_id_role_code"]
    assert "ix_user_roles_role_code" in indexes
    assert "ix_user_roles_assigned_by_user_id" in indexes


async def test_foreign_key_columns_have_leading_indexes(async_session):
    expected_indexes = {
        "auth_audit_logs": {"ix_auth_audit_logs_user_id", "ix_auth_audit_logs_session_id"},
        "auth_identities": {"ix_auth_identities_user_id"},
        "auth_sessions": {"ix_auth_sessions_user_id"},
        "sample_items": {"ix_sample_items_owner_user_id"},
        "user_roles": {
            "uq_user_roles_user_id_role_code",
            "ix_user_roles_assigned_by_user_id",
        },
    }
    for table_name, index_names in expected_indexes.items():
        result = await async_session.execute(
            text("""
                select indexname
                from pg_indexes
                where schemaname = 'public'
                  and tablename = :table_name
            """),
            {"table_name": table_name},
        )
        existing_index_names = {row.indexname for row in result.fetchall()}
        assert index_names <= existing_index_names


async def test_oidc_expected_context_columns_are_soft_references(async_session):
    constraint_result = await async_session.execute(
        text("""
            select kcu.constraint_name, kcu.column_name
            from information_schema.table_constraints tc
            join information_schema.key_column_usage kcu
              on tc.constraint_name = kcu.constraint_name
             and tc.table_schema = kcu.table_schema
             and tc.table_name = kcu.table_name
            where tc.table_schema = 'public'
              and tc.table_name = 'auth_oidc_authorization_states'
              and tc.constraint_type = 'FOREIGN KEY'
              and kcu.column_name in ('expected_user_id', 'expected_session_id')
        """))
    assert constraint_result.fetchall() == []

    index_result = await async_session.execute(
        text("""
            select indexname
            from pg_indexes
            where schemaname = 'public'
              and tablename = 'auth_oidc_authorization_states'
        """))
    index_names = {row.indexname for row in index_result.fetchall()}
    assert "ix_auth_oidc_states_expected_user_id" not in index_names
    assert "ix_auth_oidc_states_expected_session_id" not in index_names
    assert "ix_auth_oidc_authorization_states_expected_user_id" not in index_names
    assert "ix_auth_oidc_authorization_states_expected_session_id" not in index_names

    comment_result = await async_session.execute(
        text("""
            select c.column_name,
                   col_description(format('%I.%I', c.table_schema, c.table_name)::regclass::oid,
                                   c.ordinal_position) as comment
            from information_schema.columns c
            where c.table_schema = 'public'
              and c.table_name = 'auth_oidc_authorization_states'
              and c.column_name in ('expected_user_id', 'expected_session_id')
            order by c.column_name
        """))
    assert all(row.comment for row in comment_result.fetchall())


async def test_auth_identity_uses_prefixed_email_verified_column(async_session):
    result = await async_session.execute(
        text("""
            select column_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name = 'auth_identities'
              and column_name in ('is_email_verified', 'email_verified')
            order by column_name
        """))

    assert [row.column_name for row in result.fetchall()] == ["is_email_verified"]


async def test_auth_ip_columns_are_inet(async_session):
    result = await async_session.execute(
        text("""
            select table_name, column_name, udt_name
            from information_schema.columns
            where table_schema = 'public'
              and table_name in ('auth_sessions', 'auth_audit_logs')
              and column_name = 'ip_address'
            order by table_name
            """))

    rows = result.fetchall()
    assert [(row.table_name, row.column_name, row.udt_name) for row in rows] == [
        ("auth_audit_logs", "ip_address", "inet"),
        ("auth_sessions", "ip_address", "inet"),
    ]

    comment_result = await async_session.execute(
        text("""
            select c.table_name,
                   col_description(format('%I.%I', c.table_schema, c.table_name)::regclass::oid,
                                   c.ordinal_position) as comment
            from information_schema.columns c
            where c.table_schema = 'public'
              and c.table_name in ('auth_sessions', 'auth_audit_logs')
              and c.column_name = 'ip_address'
            order by c.table_name
        """))
    comments = [row.comment for row in comment_result.fetchall()]
    assert all("Stored as PostgreSQL INET by intentional schema-guideline deviation." in comment
               for comment in comments)


async def test_auth_ip_addresses_roundtrip_as_strings(async_session):
    user = User(email="inet@example.com", password_hash="hashed")
    now = utcnow()
    async_session.add(user)
    await async_session.flush()

    auth_session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=now,
        issued_at=now,
        updated_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        ip_address="192.0.2.1",
    )
    async_session.add(auth_session)
    await async_session.flush()

    audit_log = AuthAuditLog(
        user_id=user.id,
        session_id=auth_session.id,
        event_type="login_success",
        ip_address="2001:db8::1",
    )
    async_session.add(audit_log)
    await async_session.commit()

    session_ip = (await async_session.execute(
        select(AuthSession.ip_address).where(AuthSession.id == auth_session.id))).scalar_one()
    audit_ip = (await async_session.execute(
        select(AuthAuditLog.ip_address).where(AuthAuditLog.id == audit_log.id))).scalar_one()

    assert session_ip == "192.0.2.1"
    assert isinstance(session_ip, str)
    assert audit_ip == "2001:db8::1"
    assert isinstance(audit_ip, str)
