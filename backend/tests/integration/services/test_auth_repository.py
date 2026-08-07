import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.libraries.clock import utcnow
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.auth_event_type import AuthEventType
from app.models.auth_identity import AuthIdentity
from app.models.auth_oidc_state import AuthOidcState
from app.models.auth_session import AuthSession
from app.models.user import User
from app.services.auth_repository import (REJECTED_SESSION_REPLAY_LOCK_CLASS_ID, AuthRepository,
                                          _rejected_session_replay_lock_object_id)
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


async def test_create_and_find_auth_identity_by_provider_subject(auth_repository):
    user = await auth_repository.create_user("oidc-identity@example.com", None)
    identity = AuthIdentity(
        user_id=user.id,
        provider_id="google",
        provider_subject="google-subject-1",
        email="oidc-identity@example.com",
        email_verified=True,
        claims_json={
            "email": "oidc-identity@example.com",
            "email_verified": True
        },
    )

    created_identity = await auth_repository.create_auth_identity(identity)
    found_identity = await auth_repository.find_identity_by_provider_subject(
        "google",
        "google-subject-1",
    )
    user_identities = await auth_repository.find_identities_by_user_id(user.id)

    assert created_identity.id == found_identity.id
    assert found_identity.provider_id == "google"
    assert found_identity.provider_subject == "google-subject-1"
    assert [user_identity.id for user_identity in user_identities] == [created_identity.id]


async def test_create_auth_identity_rejects_duplicate_provider_subject(auth_repository):
    first_user = await auth_repository.create_user("first-identity@example.com", None)
    second_user = await auth_repository.create_user("second-identity@example.com", None)
    await auth_repository.create_auth_identity(
        AuthIdentity(
            user_id=first_user.id,
            provider_id="google",
            provider_subject="duplicate-provider-subject",
            email="first-identity@example.com",
        ))

    with pytest.raises(IntegrityError):
        await auth_repository.create_auth_identity(
            AuthIdentity(
                user_id=second_user.id,
                provider_id="google",
                provider_subject="duplicate-provider-subject",
                email="second-identity@example.com",
            ))


async def test_find_user_by_verified_email_for_oidc_link_requires_active_non_deleted_user(
    auth_repository,
    async_session,
):
    active_user = await auth_repository.create_user("link-target@example.com", None)
    inactive_user = await auth_repository.create_user("inactive-link@example.com", None)
    deleted_user = await auth_repository.create_user("deleted-link@example.com", None)
    inactive_user_record = await async_session.get(User, inactive_user.id)
    inactive_user_record.is_active = False
    await async_session.commit()
    await auth_repository.mark_user_deleted(
        deleted_user.id,
        utcnow(),
        session_id=None,
        ip_address=None,
    )

    assert (await
            auth_repository.find_user_by_verified_email_for_oidc_link("LINK-TARGET@example.com")
            ).id == active_user.id
    assert await auth_repository.find_user_by_verified_email_for_oidc_link(
        "inactive-link@example.com") is None
    assert await auth_repository.find_user_by_verified_email_for_oidc_link(
        "deleted-link@example.com") is None


async def test_find_user_by_email_for_oidc_collision_returns_inactive_non_deleted_user(
    auth_repository,
    async_session,
):
    active_user = await auth_repository.create_user("collision@example.com", None)
    inactive_user = await auth_repository.create_user("inactive-collision@example.com", None)
    deleted_user = await auth_repository.create_user("deleted-collision@example.com", None)
    inactive_user_record = await async_session.get(User, inactive_user.id)
    inactive_user_record.is_active = False
    await async_session.commit()
    await auth_repository.mark_user_deleted(
        deleted_user.id,
        utcnow(),
        session_id=None,
        ip_address=None,
    )

    assert (await auth_repository.find_user_by_email_for_oidc_collision("COLLISION@example.com")
            ).id == active_user.id
    assert (await
            auth_repository.find_user_by_email_for_oidc_collision("inactive-collision@example.com")
            ).id == inactive_user.id
    assert await auth_repository.find_user_by_email_for_oidc_collision(
        "deleted-collision@example.com") is None


async def test_record_oidc_login_updates_user_identity_and_session_auth_time(auth_repository, ):
    user = await auth_repository.create_user("oidc-login@example.com", None)
    now = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="oidc-login-session",
        csrf_token_hash="oidc-login-csrf",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )
    identity = await auth_repository.create_auth_identity(
        AuthIdentity(
            user_id=user.id,
            provider_id="google",
            provider_subject="google-login-subject",
            email="oidc-login@example.com",
            email_verified=True,
        ))
    login_at = now + timedelta(seconds=10)
    provider_auth_time = now - timedelta(minutes=1)

    await auth_repository.record_oidc_login(
        user_id=user.id,
        identity_id=identity.id,
        session_id=auth_session.id,
        login_at=login_at,
        provider_auth_time=provider_auth_time,
    )

    updated_user = await auth_repository.find_user_by_id_for_authentication(user.id)
    updated_identity = await auth_repository.find_identity_by_provider_subject(
        "google",
        "google-login-subject",
    )
    updated_session = await auth_repository.find_session_by_token_hash("oidc-login-session")
    assert updated_user.last_login_at == login_at
    assert updated_identity.last_login_at == login_at
    assert updated_session.last_oidc_auth_time_at == provider_auth_time


async def test_record_oidc_login_without_auth_time_does_not_mark_session_fresh(auth_repository, ):
    user = await auth_repository.create_user("oidc-login-no-auth-time@example.com", None)
    now = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="oidc-login-no-auth-time-session",
        csrf_token_hash="oidc-login-no-auth-time-csrf",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )
    identity = await auth_repository.create_auth_identity(
        AuthIdentity(
            user_id=user.id,
            provider_id="google",
            provider_subject="google-login-no-auth-time-subject",
            email="oidc-login-no-auth-time@example.com",
            email_verified=True,
        ))

    await auth_repository.record_oidc_login(
        user_id=user.id,
        identity_id=identity.id,
        session_id=auth_session.id,
        login_at=now,
        provider_auth_time=None,
    )

    updated_session = await auth_repository.find_session_by_token_hash(
        "oidc-login-no-auth-time-session")
    assert updated_session.last_oidc_auth_time_at is None


async def test_record_oidc_reauth_updates_session_only(auth_repository):
    user = await auth_repository.create_user("oidc-reauth@example.com", None)
    now = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="oidc-reauth-session",
        csrf_token_hash="oidc-reauth-csrf",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )
    identity = await auth_repository.create_auth_identity(
        AuthIdentity(
            user_id=user.id,
            provider_id="google",
            provider_subject="google-reauth-subject",
            email="oidc-reauth@example.com",
            email_verified=True,
        ))
    login_at = now - timedelta(hours=1)
    await auth_repository.record_oidc_login(
        user_id=user.id,
        identity_id=identity.id,
        session_id=auth_session.id,
        login_at=login_at,
        provider_auth_time=None,
    )
    provider_auth_time = now - timedelta(seconds=30)

    await auth_repository.record_oidc_reauth(
        session_id=auth_session.id,
        auth_time=provider_auth_time,
        reauthenticated_at=now,
    )

    updated_user = await auth_repository.find_user_by_id_for_authentication(user.id)
    updated_identity = await auth_repository.find_identity_by_provider_subject(
        "google",
        "google-reauth-subject",
    )
    updated_session = await auth_repository.find_session_by_token_hash("oidc-reauth-session")
    assert updated_user.last_login_at == login_at
    assert updated_identity.last_login_at == login_at
    assert updated_session.last_oidc_auth_time_at == provider_auth_time


async def test_delete_auth_identities_for_user_only_deletes_target_user(auth_repository):
    target_user = await auth_repository.create_user("delete-identities@example.com", None)
    other_user = await auth_repository.create_user("keep-identities@example.com", None)
    await auth_repository.create_auth_identity(
        AuthIdentity(
            user_id=target_user.id,
            provider_id="google",
            provider_subject="delete-identity-subject",
            email="delete-identities@example.com",
        ))
    other_identity = await auth_repository.create_auth_identity(
        AuthIdentity(
            user_id=other_user.id,
            provider_id="google",
            provider_subject="keep-identity-subject",
            email="keep-identities@example.com",
        ))

    deleted_count = await auth_repository.delete_auth_identities_for_user(target_user.id)

    assert deleted_count == 1
    assert await auth_repository.find_identities_by_user_id(target_user.id) == []
    assert [
        identity.id for identity in await auth_repository.find_identities_by_user_id(other_user.id)
    ] == [other_identity.id]


async def test_find_identities_by_user_id_ignores_deleted_users(auth_repository):
    user = await auth_repository.create_user("deleted-identity-owner@example.com", None)
    await auth_repository.create_auth_identity(
        AuthIdentity(
            user_id=user.id,
            provider_id="google",
            provider_subject="deleted-owner-subject",
            email="deleted-identity-owner@example.com",
        ))

    await auth_repository.mark_user_deleted(
        user.id,
        utcnow(),
        session_id=None,
        ip_address=None,
    )

    assert await auth_repository.find_identities_by_user_id(user.id) == []


async def test_oidc_authorization_state_is_consumed_once(auth_repository):
    now = utcnow()
    state = await auth_repository.create_oidc_authorization_state(
        AuthOidcState(
            state_hash="state-hash-1",
            browser_binding_hash="browser-binding-hash-1",
            nonce_hash="nonce-hash-1",
            pkce_verifier="pkce-verifier-1",
            provider_id="google",
            purpose="login",
            redirect_path="/",
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        ))

    consumed_result = await auth_repository.consume_oidc_authorization_state(
        state_hash="state-hash-1",
        browser_binding_hash="browser-binding-hash-1",
        consumed_at=now,
    )
    replay_result = await auth_repository.consume_oidc_authorization_state(
        state_hash="state-hash-1",
        browser_binding_hash="browser-binding-hash-1",
        consumed_at=now,
    )

    assert consumed_result.status == "consumed"
    assert consumed_result.state.id == state.id
    assert replay_result.status == "already_consumed"
    assert replay_result.state.id == state.id


async def test_oidc_authorization_state_consume_reports_mismatch_and_expiry(auth_repository):
    now = utcnow()
    await auth_repository.create_oidc_authorization_state(
        AuthOidcState(
            state_hash="expired-state-hash",
            browser_binding_hash="expired-browser-binding-hash",
            nonce_hash="expired-nonce-hash",
            pkce_verifier="expired-pkce-verifier",
            provider_id="google",
            purpose="login",
            redirect_path="/",
            expires_at=now - timedelta(seconds=1),
            created_at=now - timedelta(minutes=10),
        ))
    await auth_repository.create_oidc_authorization_state(
        AuthOidcState(
            state_hash="binding-state-hash",
            browser_binding_hash="expected-browser-binding-hash",
            nonce_hash="binding-nonce-hash",
            pkce_verifier="binding-pkce-verifier",
            provider_id="google",
            purpose="login",
            redirect_path="/",
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        ))

    missing_result = await auth_repository.consume_oidc_authorization_state(
        state_hash="missing-state-hash",
        browser_binding_hash="browser-binding-hash",
        consumed_at=now,
    )
    expired_result = await auth_repository.consume_oidc_authorization_state(
        state_hash="expired-state-hash",
        browser_binding_hash="expired-browser-binding-hash",
        consumed_at=now,
    )
    mismatch_result = await auth_repository.consume_oidc_authorization_state(
        state_hash="binding-state-hash",
        browser_binding_hash="actual-browser-binding-hash",
        consumed_at=now,
    )

    assert missing_result.status == "state_mismatch"
    assert missing_result.state is None
    assert expired_result.status == "expired"
    assert expired_result.state is not None
    assert mismatch_result.status == "browser_binding_mismatch"
    assert mismatch_result.state is not None


async def test_delete_oidc_states_expired_before_only_deletes_old_rows(
    auth_repository,
    async_session,
):
    now = utcnow()
    old_state = await auth_repository.create_oidc_authorization_state(
        AuthOidcState(
            state_hash="old-prune-state-hash",
            browser_binding_hash="old-prune-browser-binding-hash",
            nonce_hash="old-prune-nonce-hash",
            pkce_verifier="old-prune-pkce-verifier",
            provider_id="google",
            purpose="login",
            redirect_path="/",
            expires_at=now - timedelta(days=2),
            created_at=now - timedelta(days=3),
        ))
    fresh_state = await auth_repository.create_oidc_authorization_state(
        AuthOidcState(
            state_hash="fresh-prune-state-hash",
            browser_binding_hash="fresh-prune-browser-binding-hash",
            nonce_hash="fresh-prune-nonce-hash",
            pkce_verifier="fresh-prune-pkce-verifier",
            provider_id="google",
            purpose="login",
            redirect_path="/",
            expires_at=now + timedelta(minutes=5),
            created_at=now,
        ))
    consumed_state = await auth_repository.create_oidc_authorization_state(
        AuthOidcState(
            state_hash="consumed-prune-state-hash",
            browser_binding_hash="consumed-prune-browser-binding-hash",
            nonce_hash="consumed-prune-nonce-hash",
            pkce_verifier="consumed-prune-pkce-verifier",
            provider_id="google",
            purpose="login",
            redirect_path="/",
            expires_at=now + timedelta(minutes=5),
            consumed_at=now - timedelta(days=2),
            created_at=now - timedelta(days=3),
        ))

    deleted_count = await auth_repository.delete_oidc_states_expired_before(now - timedelta(days=1))

    assert deleted_count == 2
    remaining_ids = (await async_session.execute(select(AuthOidcState.id))).scalars().all()
    assert old_state.id not in remaining_ids
    assert consumed_state.id not in remaining_ids
    assert fresh_state.id in remaining_ids


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


async def test_delete_sessions_expired_before_only_deletes_rows_before_threshold(
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

    deleted_count = await auth_repository.delete_sessions_expired_before(now - timedelta(days=1))

    assert deleted_count == 1
    remaining_ids = (await async_session.execute(select(AuthSession.id))).scalars().all()
    assert old_session.id not in remaining_ids
    assert fresh_session.id in remaining_ids


async def test_delete_sessions_expired_before_keeps_audit_log_with_null_session_id(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("prune-linked-audit@example.com", "hash")
    now = utcnow()
    old_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="linked-old-session",
        csrf_token_hash="linked-old-csrf",
        created_at=now - timedelta(days=3),
        issued_at=now - timedelta(days=3),
        last_seen_at=now - timedelta(days=3),
        expires_at=now - timedelta(days=2),
        ip_address=None,
        user_agent=None,
    )
    audit_log = AuthAuditLog(
        user_id=user.id,
        session_id=old_session.id,
        event_type=AuthEventType.LOGIN_SUCCESS,
        created_at=now - timedelta(days=2),
    )
    async_session.add(audit_log)
    await async_session.commit()

    deleted_count = await auth_repository.delete_sessions_expired_before(now - timedelta(days=1))

    assert deleted_count == 1
    linked_session_id = (await async_session.execute(
        select(AuthAuditLog.session_id).where(AuthAuditLog.id == audit_log.id))).scalar_one()
    assert linked_session_id is None


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


async def test_record_rejected_session_replay_aggregates_within_window(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("bounded-replay@example.com", "hash")
    now = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="bounded-replay-session",
        csrf_token_hash="bounded-replay-csrf",
        created_at=now - timedelta(minutes=20),
        issued_at=now - timedelta(minutes=20),
        last_seen_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )

    await auth_repository.record_rejected_session_replay(
        auth_session,
        ip_address="127.0.0.1",
        user_agent="first-agent",
        replayed_at=now,
        window_seconds=300,
    )
    await auth_repository.record_rejected_session_replay(
        auth_session,
        ip_address="127.0.0.2",
        user_agent="second-agent",
        replayed_at=now + timedelta(seconds=30),
        window_seconds=300,
    )

    audit_logs = (await async_session.execute(
        select(AuthAuditLog).where(
            AuthAuditLog.session_id == auth_session.id,
            AuthAuditLog.event_type == AuthEventType.SESSION_REJECTED,
        ))).scalars().all()
    assert len(audit_logs) == 1
    assert audit_logs[0].user_id == user.id
    assert audit_logs[0].ip_address == "127.0.0.1"
    assert audit_logs[0].user_agent == "first-agent"
    assert audit_logs[0].detail_json == {
        "distinct_ip_count": 2,
        "last_ip_address": "127.0.0.2",
        "last_user_agent": "second-agent",
        "replay_count": 2,
        "recent_ip_addresses": ["127.0.0.1", "127.0.0.2"],
        "window_seconds": 300,
        "last_replayed_at": (now + timedelta(seconds=30)).isoformat(),
    }


async def test_record_rejected_session_replay_skips_when_session_lock_is_busy(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("bounded-replay-busy-lock@example.com", "hash")
    now = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="bounded-replay-busy-lock-session",
        csrf_token_hash="bounded-replay-busy-lock-csrf",
        created_at=now - timedelta(minutes=20),
        issued_at=now - timedelta(minutes=20),
        last_seen_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )

    await async_session.execute(
        text("SELECT pg_advisory_xact_lock(:class_id, :object_id)"),
        {
            "class_id": REJECTED_SESSION_REPLAY_LOCK_CLASS_ID,
            "object_id": _rejected_session_replay_lock_object_id(auth_session.id),
        },
    )
    await asyncio.wait_for(
        auth_repository.record_rejected_session_replay(
            auth_session,
            ip_address="127.0.0.1",
            user_agent="busy-agent",
            replayed_at=now,
            window_seconds=300,
        ),
        timeout=0.5,
    )

    audit_count = (await async_session.execute(select(AuthAuditLog.id))).scalars().all()
    assert audit_count == []


async def test_record_rejected_session_replay_does_not_reuse_raw_rejection_anchor(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("bounded-replay-raw-anchor@example.com", "hash")
    now = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="bounded-replay-raw-anchor-session",
        csrf_token_hash="bounded-replay-raw-anchor-csrf",
        created_at=now - timedelta(minutes=20),
        issued_at=now - timedelta(minutes=20),
        last_seen_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )
    async_session.add(
        AuthAuditLog(
            user_id=user.id,
            session_id=auth_session.id,
            event_type=AuthEventType.SESSION_REJECTED,
            ip_address="127.0.0.1",
            user_agent="initial-rejection",
            created_at=now - timedelta(seconds=30),
        ))
    await async_session.commit()

    await auth_repository.record_rejected_session_replay(
        auth_session,
        ip_address="127.0.0.2",
        user_agent="replay-agent",
        replayed_at=now,
        window_seconds=300,
    )

    audit_logs = (await async_session.execute(
        select(AuthAuditLog).where(
            AuthAuditLog.session_id == auth_session.id,
            AuthAuditLog.event_type == AuthEventType.SESSION_REJECTED,
        ).order_by(AuthAuditLog.created_at))).scalars().all()
    assert len(audit_logs) == 2
    assert audit_logs[0].detail_json is None
    assert audit_logs[1].detail_json["replay_count"] == 1


async def test_record_rejected_session_replay_creates_new_row_after_window(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("bounded-replay-window@example.com", "hash")
    first_replay_at = utcnow() - timedelta(minutes=10)
    second_replay_at = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="bounded-replay-window-session",
        csrf_token_hash="bounded-replay-window-csrf",
        created_at=first_replay_at - timedelta(minutes=20),
        issued_at=first_replay_at - timedelta(minutes=20),
        last_seen_at=first_replay_at - timedelta(minutes=20),
        expires_at=first_replay_at - timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )

    await auth_repository.record_rejected_session_replay(
        auth_session,
        ip_address="127.0.0.1",
        user_agent="first-agent",
        replayed_at=first_replay_at,
        window_seconds=300,
    )
    await auth_repository.record_rejected_session_replay(
        auth_session,
        ip_address="127.0.0.2",
        user_agent="second-agent",
        replayed_at=second_replay_at,
        window_seconds=300,
    )

    audit_logs = (await async_session.execute(
        select(AuthAuditLog).where(
            AuthAuditLog.session_id == auth_session.id,
            AuthAuditLog.event_type == AuthEventType.SESSION_REJECTED,
        ).order_by(AuthAuditLog.created_at))).scalars().all()
    assert [audit_log.detail_json["replay_count"] for audit_log in audit_logs] == [1, 1]
    assert [audit_log.created_at for audit_log in audit_logs] == [
        first_replay_at,
        second_replay_at,
    ]


async def test_record_rejected_session_replay_keeps_single_row_under_concurrency(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("bounded-replay-concurrent@example.com", "hash")
    now = utcnow()
    auth_session = await auth_repository.create_session(
        user_id=user.id,
        session_token_hash="bounded-replay-concurrent-session",
        csrf_token_hash="bounded-replay-concurrent-csrf",
        created_at=now - timedelta(minutes=20),
        issued_at=now - timedelta(minutes=20),
        last_seen_at=now - timedelta(minutes=20),
        expires_at=now - timedelta(minutes=10),
        ip_address=None,
        user_agent=None,
    )

    await asyncio.gather(*[
        auth_repository.record_rejected_session_replay(
            auth_session,
            ip_address=f"127.0.0.{index}",
            user_agent=f"agent-{index}",
            replayed_at=now + timedelta(seconds=index),
            window_seconds=300,
        ) for index in range(1, 6)
    ])

    audit_logs = (await async_session.execute(
        select(AuthAuditLog).where(
            AuthAuditLog.session_id == auth_session.id,
            AuthAuditLog.event_type == AuthEventType.SESSION_REJECTED,
        ))).scalars().all()
    assert len(audit_logs) == 1
    assert 1 <= audit_logs[0].detail_json["replay_count"] <= 5
