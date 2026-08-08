from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import UUID, uuid4

import pytest

from app.libraries.clock import utcnow
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.authorization import UserAuthorization, UserRoleReplacementResult
from app.models.authorization_errors import AuthorizationUserNotFoundError
from app.models.user import User
from app.usecases.authorization_usecase import AuthorizationUsecase


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

    def __init__(self, target_user: User | None) -> None:
        self.target_user = target_user
        self.audit_logs: list[AuthAuditLog] = []

    async def find_user_by_id_for_authentication(self, _user_id: UUID) -> User | None:
        return self.target_user

    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        self.audit_logs.append(audit_log)


class AuthorizationRepositoryStub:

    def __init__(self, result: UserRoleReplacementResult | None = None) -> None:
        self.result = result
        self.replace_calls: list[tuple[UUID, tuple[str, ...], UUID | None]] = []
        self.authorization: UserAuthorization | None = None

    async def list_roles_with_permissions(self):
        return []

    async def list_permissions(self):
        return []

    async def get_user_authorization(self, user_id: UUID):
        if self.authorization is None:
            return None
        return UserAuthorization(
            user_id=user_id,
            roles=self.authorization.roles,
            permissions=self.authorization.permissions,
        )

    async def replace_user_roles(
        self,
        user_id: UUID,
        role_codes: tuple[str, ...],
        assigned_by_user_id: UUID | None,
    ) -> UserRoleReplacementResult:
        self.replace_calls.append((user_id, role_codes, assigned_by_user_id))
        return self.result or UserRoleReplacementResult(
            user_id=user_id,
            granted_role_codes=(),
            revoked_role_codes=(),
            current_role_codes=role_codes,
            current_permission_codes=(),
        )


@pytest.mark.asyncio
async def test_replace_user_roles_allows_inactive_user_and_records_audit() -> None:
    actor_context = _context("admin@example.com")
    target_user = User(id=uuid4(),
                       email="target@example.com",
                       password_hash="hash",
                       is_active=False)
    result = UserRoleReplacementResult(
        user_id=target_user.id,
        granted_role_codes=("admin", ),
        revoked_role_codes=("viewer", ),
        current_role_codes=("admin", ),
        current_permission_codes=("admin:access", ),
    )
    auth_repository = AuthRepositoryStub(target_user)
    authorization_repository = AuthorizationRepositoryStub(result)
    unit_of_work = UnitOfWorkStub()
    usecase = AuthorizationUsecase(auth_repository, authorization_repository, unit_of_work)

    actual = await usecase.replace_user_roles(
        actor_context,
        target_user.id,
        ("admin", "admin"),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert actual is result
    assert authorization_repository.replace_calls == [(target_user.id, ("admin", ),
                                                       actor_context.user.id)]
    assert unit_of_work.transaction_entries == 1
    assert [log.event_type for log in auth_repository.audit_logs] == [
        AuthEventType.ROLE_GRANTED,
        AuthEventType.ROLE_REVOKED,
    ]
    assert auth_repository.audit_logs[0].user_id == actor_context.user.id
    assert auth_repository.audit_logs[0].detail_json["targetUserId"] == str(target_user.id)


@pytest.mark.asyncio
async def test_replace_user_roles_rejects_deleted_user() -> None:
    target_user = User(id=uuid4(), email="target@example.com", password_hash="hash")
    target_user.deleted_at = utcnow()
    usecase = AuthorizationUsecase(
        AuthRepositoryStub(target_user),
        AuthorizationRepositoryStub(),
        UnitOfWorkStub(),
    )

    with pytest.raises(AuthorizationUserNotFoundError):
        await usecase.replace_user_roles(
            _context("admin@example.com"),
            target_user.id,
            ("admin", ),
            ip_address=None,
            user_agent=None,
        )


def _context(email: str) -> AuthenticatedSessionContext:
    now = utcnow()
    user = User(id=uuid4(), email=email, password_hash="hash")
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset({"admin"}),
        permissions=frozenset({"admin:access"}),
    )
