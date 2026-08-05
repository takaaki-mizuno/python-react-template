import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.libraries.clock import utcnow
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.auth_repository import AuthRepository
from app.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.integration


@pytest.fixture
def async_session_factory(async_engine):
    return async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
def auth_repository(async_session_factory):
    return AuthRepository(unit_of_work=UnitOfWork(session_factory=async_session_factory))


async def test_find_user_by_email_ignores_deleted_users(auth_repository):
    user = await auth_repository.create_user("deleted@example.com", "hash")
    await auth_repository.mark_user_deleted(user.id, utcnow(), session_id=None, ip_address=None)

    assert await auth_repository.find_user_by_email("deleted@example.com") is None


async def test_find_user_by_id_for_authentication_returns_all_user_states(
    auth_repository,
    async_session,
):
    active_user = await auth_repository.create_user("active@example.com", "hash")
    deleted_user = await auth_repository.create_user("deleted-auth@example.com", "hash")
    inactive_user = await auth_repository.create_user("inactive@example.com", "hash")
    deleted_user = await auth_repository.mark_user_deleted(
        deleted_user.id,
        utcnow(),
        session_id=None,
        ip_address=None,
    )
    persisted_inactive_user = await async_session.get(User, inactive_user.id)
    persisted_inactive_user.is_active = False
    await async_session.commit()

    found_active_user = await auth_repository.find_user_by_id_for_authentication(active_user.id)
    found_deleted_user = await auth_repository.find_user_by_id_for_authentication(deleted_user.id)
    found_inactive_user = await auth_repository.find_user_by_id_for_authentication(inactive_user.id)

    assert found_active_user.id == active_user.id
    assert found_active_user.deleted_at is None
    assert found_deleted_user.id == deleted_user.id
    assert found_deleted_user.deleted_at == deleted_user.deleted_at
    assert found_inactive_user.id == inactive_user.id
    assert found_inactive_user.is_active is False
    assert await auth_repository.find_user_by_id_for_authentication(uuid4()) is None


async def test_deleted_user_email_can_be_reused(auth_repository):
    deleted_user = await auth_repository.create_user("reuse@example.com", "hash")
    await auth_repository.mark_user_deleted(
        deleted_user.id,
        utcnow(),
        session_id=None,
        ip_address=None,
    )

    active_user = await auth_repository.create_user("reuse@example.com", "hash")

    assert active_user.id != deleted_user.id
    assert await auth_repository.find_user_by_email("reuse@example.com") == active_user


async def test_mark_user_deleted_concurrent_calls_audit_once(async_session_factory):
    user_repository = AuthRepository(unit_of_work=UnitOfWork(session_factory=async_session_factory))
    user = await user_repository.create_user("delete-race@example.com", "hash")
    first_repository = AuthRepository(unit_of_work=UnitOfWork(
        session_factory=async_session_factory))
    second_repository = AuthRepository(unit_of_work=UnitOfWork(
        session_factory=async_session_factory))

    await asyncio.gather(
        first_repository.mark_user_deleted(
            user.id,
            utcnow(),
            session_id=None,
            ip_address="127.0.0.1",
        ),
        second_repository.mark_user_deleted(
            user.id,
            utcnow(),
            session_id=None,
            ip_address="127.0.0.1",
        ),
    )

    async with async_session_factory() as session:
        audit_logs = (await session.exec(
            select(AuthAuditLog).where(
                AuthAuditLog.user_id == user.id,
                AuthAuditLog.event_type == AuthEventType.USER_MARKED_DELETED,
            ))).all()

    assert len(audit_logs) == 1


async def test_mark_user_deleted_sequential_calls_keep_first_deleted_at_and_audit_once(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("delete-once@example.com", "hash")
    first_deleted_at = utcnow()
    second_deleted_at = first_deleted_at + timedelta(seconds=1)

    first_result = await auth_repository.mark_user_deleted(
        user.id,
        first_deleted_at,
        session_id=None,
        ip_address="127.0.0.1",
    )
    second_result = await auth_repository.mark_user_deleted(
        user.id,
        second_deleted_at,
        session_id=None,
        ip_address="127.0.0.1",
    )

    audit_logs = (await async_session.execute(
        select(AuthAuditLog).where(
            AuthAuditLog.user_id == user.id,
            AuthAuditLog.event_type == AuthEventType.USER_MARKED_DELETED,
        ))).scalars().all()

    assert first_result.deleted_at == first_deleted_at
    assert second_result.deleted_at == first_deleted_at
    assert len(audit_logs) == 1


async def test_mark_user_deleted_returns_updated_user_inside_transaction(async_session_factory, ):
    unit_of_work = UnitOfWork(session_factory=async_session_factory)
    repository = AuthRepository(unit_of_work=unit_of_work)
    user = await repository.create_user("delete-in-transaction@example.com", "hash")
    deleted_at = utcnow()

    async with unit_of_work.transaction():
        loaded_user = await repository.find_user_by_id_for_authentication(user.id)
        assert loaded_user is not None
        assert loaded_user.deleted_at is None

        deleted_user = await repository.mark_user_deleted(
            user.id,
            deleted_at,
            session_id=None,
            ip_address="127.0.0.1",
        )

    assert deleted_user.deleted_at == deleted_at


async def test_active_user_email_duplicates_are_rejected(auth_repository):
    await auth_repository.create_user("duplicate@example.com", "hash")

    with pytest.raises(EmailAlreadyRegisteredError):
        await auth_repository.create_user("DUPLICATE@example.com", "hash")


async def test_revoke_sessions_for_user_only_revokes_active_sessions_for_target_user(
    auth_repository, ):
    user = await auth_repository.create_user("session-owner@example.com", "hash")
    other_user = await auth_repository.create_user("other-session-owner@example.com", "hash")
    now = utcnow()
    target_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="target-session",
        csrf_token_hash="target-csrf",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )
    already_revoked_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="already-revoked-session",
        csrf_token_hash="already-revoked-csrf",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )
    await auth_repository.revoke_session(already_revoked_session.id)
    other_session = await auth_repository.create_session(
        user_id=other_user.id,
        session_token_hash="other-session",
        csrf_token_hash="other-csrf",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )

    revoked_count = await auth_repository.revoke_sessions_for_user(user.id, now)

    assert revoked_count == 1
    assert (await auth_repository.find_session_by_token_hash(target_session.session_token_hash
                                                             )).revoked_at == now
    assert (await
            auth_repository.find_session_by_token_hash(already_revoked_session.session_token_hash
                                                       )).revoked_at is not None
    assert (await auth_repository.find_session_by_token_hash(other_session.session_token_hash
                                                             )).revoked_at is None


async def test_delete_expired_sessions_only_deletes_rows_before_threshold(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("prune-sessions@example.com", "hash")
    now = utcnow()
    old_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="old-session",
        csrf_token_hash="old-csrf",
        created_at=now - timedelta(days=3),
        issued_at=now - timedelta(days=3),
        last_seen_at=now - timedelta(days=3),
        expires_at=now - timedelta(days=2),
        ip_address=None,
        user_agent=None,
    )
    fresh_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="fresh-session",
        csrf_token_hash="fresh-csrf",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=1),
        ip_address=None,
        user_agent=None,
    )

    deleted_count = await auth_repository.delete_expired_sessions(now - timedelta(days=1))

    assert deleted_count == 1
    remaining_ids = (await async_session.execute(select(AuthSession.id))).scalars().all()
    assert old_session.id not in remaining_ids
    assert fresh_session.id in remaining_ids


async def test_delete_audit_logs_created_before_only_deletes_old_rows(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("prune-audit@example.com", "hash")
    now = utcnow()
    old_log = AuthAuditLog(
        user_id=user.id,
        session_id=None,
        event_type="login_failed",
        created_at=now - timedelta(days=3),
    )
    fresh_log = AuthAuditLog(
        user_id=user.id,
        session_id=None,
        event_type="login_success",
        created_at=now,
    )
    async_session.add(old_log)
    async_session.add(fresh_log)
    await async_session.commit()

    deleted_count = await auth_repository.delete_audit_logs_created_before(now - timedelta(days=1))

    assert deleted_count == 1
    remaining_ids = (await async_session.execute(select(AuthAuditLog.id))).scalars().all()
    assert old_log.id not in remaining_ids
    assert fresh_log.id in remaining_ids
