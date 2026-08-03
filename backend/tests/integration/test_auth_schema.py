import pytest
from sqlalchemy import text

pytestmark = pytest.mark.integration


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


async def test_users_email_has_lower_unique_index(async_session):
    result = await async_session.execute(
        text("""
            select indexdef
            from pg_indexes
            where schemaname = 'public'
              and tablename = 'users'
            """))

    index_definitions = [row[0] for row in result.fetchall()]
    assert any("CREATE UNIQUE INDEX uq_users_email_lower" in definition
               and "lower" in definition.lower() and "email" in definition.lower()
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


async def test_auth_expiry_columns_are_timezone_aware(async_session):
    result = await async_session.execute(
        text("""
            select table_name, column_name, data_type
            from information_schema.columns
            where table_schema = 'public'
              and (
                (table_name = 'auth_sessions'
                 and column_name in (
                   'created_at', 'last_seen_at', 'expires_at', 'revoked_at'
                 ))
                or
                (table_name = 'auth_audit_logs'
                 and column_name = 'created_at')
              )
            """))

    rows = result.fetchall()
    assert len(rows) == 5
    assert all(row.data_type == "timestamp with time zone" for row in rows)
