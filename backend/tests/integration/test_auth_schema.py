from datetime import timedelta

import pytest
from sqlalchemy import text
from sqlmodel import select

from app.libraries.clock import utcnow
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_session import AuthSession
from app.models.user import User

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


async def test_auth_expiry_columns_are_timezone_aware(async_session):
    result = await async_session.execute(
        text("""
            select table_name, column_name, data_type
            from information_schema.columns
            where table_schema = 'public'
              and (
                (table_name = 'auth_sessions'
                 and column_name in (
                   'created_at', 'issued_at', 'updated_at',
                   'last_seen_at', 'expires_at', 'revoked_at'
                 ))
                or
                (table_name = 'auth_audit_logs'
                 and column_name = 'created_at')
                or
                (table_name = 'users'
                 and column_name = 'deleted_at')
              )
            """))

    rows = result.fetchall()
    assert len(rows) == 8
    assert all(row.data_type == "timestamp with time zone" for row in rows)


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
