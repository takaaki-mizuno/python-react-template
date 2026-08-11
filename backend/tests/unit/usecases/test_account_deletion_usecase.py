from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID

import pytest

from app.config.auth import AuthSettings
from app.config.oidc import OidcProviderSettings, OidcSettings
from app.libraries.clock import utcnow
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_errors import (AccountDeletionConfirmationMismatchError,
                                    AccountDeletionInvalidPasswordError,
                                    AccountDeletionOidcReauthRequiredError,
                                    AccountDeletionReauthRequiredError, RateLimitExceededError)
from app.models.auth_event_type import AuthEventType
from app.models.auth_identity import AuthIdentity
from app.models.auth_session import AuthSession
from app.models.user import User
from app.usecases.account_deletion_usecase import AccountDeletionUsecase


class UnitOfWorkStub:

    def __init__(self) -> None:
        self.in_transaction = False
        self.transaction_entries = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        self.transaction_entries += 1
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False


class AuthRepositoryStub:

    def __init__(self, unit_of_work: UnitOfWorkStub) -> None:
        self._unit_of_work = unit_of_work
        self.mark_user_deleted_calls: list[tuple[UUID, object, UUID | None, str | None, bool]] = []
        self.revoke_sessions_for_user_calls: list[tuple[UUID, object, bool]] = []
        self.delete_auth_identities_for_user_calls: list[tuple[UUID, bool]] = []
        self.identities: list[AuthIdentity] = []
        self.operation_order: list[str] = []
        self.audit_logs: list[AuthAuditLog] = []

    async def mark_user_deleted(
        self,
        user_id: UUID,
        deleted_at,
        session_id: UUID | None = None,
        ip_address: str | None = None,
    ):
        self.operation_order.append("mark_user_deleted")
        self.mark_user_deleted_calls.append(
            (user_id, deleted_at, session_id, ip_address, self._unit_of_work.in_transaction))
        return User(id=user_id, email="deleted@example.com", deleted_at=deleted_at)

    async def revoke_sessions_for_user(self, user_id: UUID, revoked_at):
        self.operation_order.append("revoke_sessions_for_user")
        self.revoke_sessions_for_user_calls.append(
            (user_id, revoked_at, self._unit_of_work.in_transaction))
        return 1

    async def find_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
        return [identity for identity in self.identities if identity.user_id == user_id]

    async def delete_auth_identities_for_user(self, user_id: UUID) -> int:
        self.operation_order.append("delete_auth_identities_for_user")
        self.delete_auth_identities_for_user_calls.append(
            (user_id, self._unit_of_work.in_transaction))
        deleted = [identity for identity in self.identities if identity.user_id == user_id]
        self.identities = [identity for identity in self.identities if identity.user_id != user_id]
        return len(deleted)

    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        self.audit_logs.append(audit_log)


class AuthorizationRepositoryStub:

    def __init__(self, unit_of_work: UnitOfWorkStub, auth_repository: AuthRepositoryStub) -> None:
        self._unit_of_work = unit_of_work
        self._auth_repository = auth_repository
        self.delete_roles_for_user_calls: list[tuple[UUID, bool]] = []

    async def delete_roles_for_user(self, user_id: UUID) -> int:
        self._auth_repository.operation_order.append("delete_roles_for_user")
        self.delete_roles_for_user_calls.append((user_id, self._unit_of_work.in_transaction))
        return 1


class SampleItemRepositoryStub:

    def __init__(self, unit_of_work: UnitOfWorkStub, auth_repository: AuthRepositoryStub) -> None:
        self._unit_of_work = unit_of_work
        self._auth_repository = auth_repository
        self.delete_all_for_owner_calls: list[tuple[UUID, bool]] = []

    async def delete_all_for_owner(self, owner_user_id: UUID) -> None:
        self._auth_repository.operation_order.append("delete_all_for_owner")
        self.delete_all_for_owner_calls.append((owner_user_id, self._unit_of_work.in_transaction))


class RateLimiterStub:

    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.is_allowed_calls: list[tuple[str, str]] = []
        self.account_deletion_allowed_calls: list[tuple[str, str]] = []
        self.failure_records: list[tuple[str, str, bool]] = []
        self.success_records: list[tuple[str, str]] = []

    def is_allowed(self, ip_address: str, normalized_email: str) -> bool:
        self.is_allowed_calls.append((ip_address, normalized_email))
        return self.allowed

    def is_account_deletion_reauth_allowed(
        self,
        ip_address: str,
        normalized_email: str,
    ) -> bool:
        self.account_deletion_allowed_calls.append((ip_address, normalized_email))
        return self.allowed

    def record_failure(
        self,
        ip_address: str,
        normalized_email: str,
        include_email_bucket: bool = True,
    ) -> None:
        self.failure_records.append((ip_address, normalized_email, include_email_bucket))

    def record_success(self, ip_address: str, normalized_email: str) -> None:
        self.success_records.append((ip_address, normalized_email))


class PasswordHashExecutorStub:

    def __init__(self, verify_result: bool = True) -> None:
        self.verify_result = verify_result
        self.verify_calls: list[tuple[str, str]] = []

    async def verify(self, raw_password: str, hashed_password: str) -> bool:
        self.verify_calls.append((raw_password, hashed_password))
        return self.verify_result


def _auth_context(
    email: str = "user@example.com",
    password_hash: str | None = "hashed-password",
    last_oidc_authenticated_at=None,
) -> AuthenticatedSessionContext:
    now = utcnow()
    user = User(email=email, password_hash=password_hash, is_active=True)
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
        last_oidc_authenticated_at=last_oidc_authenticated_at,
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset(),
        permissions=frozenset(),
    )


def _usecase(
    *,
    unit_of_work: UnitOfWorkStub | None = None,
    rate_limiter: RateLimiterStub | None = None,
    password_hash_executor: PasswordHashExecutorStub | None = None,
) -> tuple[
        AccountDeletionUsecase,
        UnitOfWorkStub,
        AuthRepositoryStub,
        SampleItemRepositoryStub,
        RateLimiterStub,
        PasswordHashExecutorStub,
]:
    unit_of_work = unit_of_work or UnitOfWorkStub()
    auth_repository = AuthRepositoryStub(unit_of_work)
    authorization_repository = AuthorizationRepositoryStub(unit_of_work, auth_repository)
    sample_repository = SampleItemRepositoryStub(unit_of_work, auth_repository)
    rate_limiter = rate_limiter or RateLimiterStub()
    password_hash_executor = password_hash_executor or PasswordHashExecutorStub()
    usecase = AccountDeletionUsecase(
        auth_repository=auth_repository,
        authorization_repository=authorization_repository,
        sample_item_repository=sample_repository,
        unit_of_work=unit_of_work,
        auth_rate_limiter=rate_limiter,
        auth_settings=AuthSettings(_env_file=None),
        oidc_settings=OidcSettings(
            providers=(OidcProviderSettings(
                provider_id="google",
                display_name="Google",
                issuer="https://accounts.example.com",
                client_id="client-id",
                client_secret="client-secret",
                callback_path="/api/auth/oidc/google/callback",
            ), ),
            AUTH_OIDC_REDIRECT_BASE_URL="https://app.example.com",
        ),
        password_hash_executor=password_hash_executor,
    )
    return (
        usecase,
        unit_of_work,
        auth_repository,
        sample_repository,
        rate_limiter,
        password_hash_executor,
    )


@pytest.mark.asyncio
async def test_confirm_email_mismatch_does_not_start_transaction() -> None:
    usecase, unit_of_work, auth_repository, sample_repository, _, _ = _usecase()

    with pytest.raises(AccountDeletionConfirmationMismatchError):
        await usecase.delete_account(
            auth_context=_auth_context(),
            confirm_email="other@example.com",
            password=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert unit_of_work.transaction_entries == 0
    assert sample_repository.delete_all_for_owner_calls == []
    assert auth_repository.mark_user_deleted_calls == []
    assert auth_repository.revoke_sessions_for_user_calls == []


@pytest.mark.asyncio
async def test_password_user_requires_password() -> None:
    usecase, unit_of_work, auth_repository, sample_repository, _, _ = _usecase()

    with pytest.raises(AccountDeletionReauthRequiredError):
        await usecase.delete_account(
            auth_context=_auth_context(password_hash="hashed-password"),
            confirm_email="user@example.com",
            password=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert unit_of_work.transaction_entries == 0
    assert sample_repository.delete_all_for_owner_calls == []
    assert auth_repository.mark_user_deleted_calls == []


@pytest.mark.asyncio
async def test_password_user_treats_empty_password_as_missing_without_rate_limit_failure() -> None:
    rate_limiter = RateLimiterStub()
    password_hash_executor = PasswordHashExecutorStub()
    usecase, unit_of_work, auth_repository, _, _, _ = _usecase(
        rate_limiter=rate_limiter,
        password_hash_executor=password_hash_executor,
    )

    with pytest.raises(AccountDeletionReauthRequiredError):
        await usecase.delete_account(
            auth_context=_auth_context(password_hash="hashed-password"),
            confirm_email="user@example.com",
            password="",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert password_hash_executor.verify_calls == []
    assert rate_limiter.failure_records == []
    assert unit_of_work.transaction_entries == 0
    assert auth_repository.mark_user_deleted_calls == []


@pytest.mark.asyncio
async def test_wrong_password_records_failure_and_raises_dedicated_error() -> None:
    rate_limiter = RateLimiterStub()
    password_hash_executor = PasswordHashExecutorStub(verify_result=False)
    usecase, unit_of_work, auth_repository, _, _, _ = _usecase(
        rate_limiter=rate_limiter,
        password_hash_executor=password_hash_executor,
    )
    auth_context = _auth_context(email="User@Example.COM", password_hash="hashed-password")

    with pytest.raises(AccountDeletionInvalidPasswordError):
        await usecase.delete_account(
            auth_context=auth_context,
            confirm_email=" user@example.com ",
            password="wrong-password",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert password_hash_executor.verify_calls == [("wrong-password", "hashed-password")]
    assert rate_limiter.failure_records == [("127.0.0.1", "user@example.com", False)]
    assert rate_limiter.success_records == []
    assert len(auth_repository.audit_logs) == 1
    audit_log = auth_repository.audit_logs[0]
    assert audit_log.user_id == auth_context.user.id
    assert audit_log.session_id == auth_context.session.id
    assert audit_log.event_type == AuthEventType.ACCOUNT_DELETION_REAUTH_FAILED
    assert audit_log.ip_address == "127.0.0.1"
    assert audit_log.user_agent == "pytest"
    assert unit_of_work.transaction_entries == 0


@pytest.mark.asyncio
async def test_oauth_only_user_requires_oidc_reauth_when_auth_time_missing() -> None:
    usecase, unit_of_work, auth_repository, sample_repository, _, _ = _usecase()
    auth_context = _auth_context(password_hash=None, last_oidc_authenticated_at=None)
    auth_repository.identities.append(
        AuthIdentity(
            user_id=auth_context.user.id,
            provider_id="google",
            provider_subject="subject-1",
            email=auth_context.user.email,
            is_email_verified=True,
            claims_json={"sub": "subject-1"},
        ))

    with pytest.raises(AccountDeletionOidcReauthRequiredError) as excinfo:
        await usecase.delete_account(
            auth_context=auth_context,
            confirm_email="user@example.com",
            password=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert excinfo.value.linked_providers == [{
        "providerId": "google",
        "displayName": "Google",
    }]
    assert unit_of_work.transaction_entries == 0
    assert sample_repository.delete_all_for_owner_calls == []
    assert auth_repository.mark_user_deleted_calls == []


@pytest.mark.asyncio
async def test_oauth_only_user_requires_oidc_reauth_when_auth_time_is_stale() -> None:
    usecase, unit_of_work, auth_repository, sample_repository, _, _ = _usecase()
    auth_context = _auth_context(
        password_hash=None,
        last_oidc_authenticated_at=utcnow() - timedelta(minutes=10),
    )

    with pytest.raises(AccountDeletionOidcReauthRequiredError) as excinfo:
        await usecase.delete_account(
            auth_context=auth_context,
            confirm_email="user@example.com",
            password=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert excinfo.value.linked_providers == []
    assert unit_of_work.transaction_entries == 0
    assert sample_repository.delete_all_for_owner_calls == []
    assert auth_repository.mark_user_deleted_calls == []


@pytest.mark.asyncio
async def test_oauth_only_user_can_delete_with_fresh_oidc_reauth_without_password_or_rate_limit(
) -> None:
    usecase, _, auth_repository, sample_repository, rate_limiter, password_hash_executor = (
        _usecase())
    auth_context = _auth_context(password_hash=None, last_oidc_authenticated_at=utcnow())

    await usecase.delete_account(
        auth_context=auth_context,
        confirm_email="user@example.com",
        password=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert password_hash_executor.verify_calls == []
    assert rate_limiter.account_deletion_allowed_calls == []
    assert sample_repository.delete_all_for_owner_calls[0][0] == auth_context.user.id
    assert auth_repository.mark_user_deleted_calls[0][0] == auth_context.user.id
    assert auth_repository.delete_auth_identities_for_user_calls[0][0] == auth_context.user.id


@pytest.mark.asyncio
async def test_rate_limit_is_checked_before_password_verification() -> None:
    rate_limiter = RateLimiterStub(allowed=False)
    password_hash_executor = PasswordHashExecutorStub()
    usecase, unit_of_work, auth_repository, _, _, _ = _usecase(
        rate_limiter=rate_limiter,
        password_hash_executor=password_hash_executor,
    )

    with pytest.raises(RateLimitExceededError) as excinfo:
        await usecase.delete_account(
            auth_context=_auth_context(),
            confirm_email="user@example.com",
            password="Password123!",
            ip_address=None,
            user_agent="pytest",
        )

    assert (excinfo.value.retry_after_seconds == AuthSettings(
        _env_file=None).AUTH_RATE_LIMIT_WINDOW_SECONDS)
    assert rate_limiter.account_deletion_allowed_calls == [("unknown", "user@example.com")]
    assert password_hash_executor.verify_calls == []
    assert unit_of_work.transaction_entries == 0
    assert auth_repository.mark_user_deleted_calls == []


@pytest.mark.asyncio
async def test_success_deletes_owned_data_marks_user_and_revokes_sessions_in_one_transaction(
) -> None:
    usecase, _, auth_repository, sample_repository, _, _ = _usecase()
    auth_context = _auth_context(email=" User@Example.COM ")

    await usecase.delete_account(
        auth_context=auth_context,
        confirm_email="user@example.com",
        password="Password123!",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert auth_repository.operation_order == [
        "delete_all_for_owner",
        "delete_roles_for_user",
        "delete_auth_identities_for_user",
        "mark_user_deleted",
        "revoke_sessions_for_user",
    ]
    assert sample_repository.delete_all_for_owner_calls == [(auth_context.user.id, True)]
    assert auth_repository.delete_auth_identities_for_user_calls == [(auth_context.user.id, True)]
    marked_user_id, deleted_at, session_id, ip_address, marked_in_transaction = (
        auth_repository.mark_user_deleted_calls[0])
    revoked_user_id, revoked_at, revoked_in_transaction = (
        auth_repository.revoke_sessions_for_user_calls[0])
    assert marked_user_id == auth_context.user.id
    assert revoked_user_id == auth_context.user.id
    assert session_id == auth_context.session.id
    assert ip_address == "127.0.0.1"
    assert deleted_at is revoked_at
    assert marked_in_transaction is True
    assert revoked_in_transaction is True
