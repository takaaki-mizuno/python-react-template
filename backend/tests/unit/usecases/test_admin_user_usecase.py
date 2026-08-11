from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.models.admin_pagination import AdminOffsetPageResult
from app.models.admin_user import AdminUserListQuery, AdminUserRecord, AdminUserUpdateChanges
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_errors import UserNotFoundError, WeakPasswordError
from app.models.auth_session import AuthSession
from app.models.authorization import UserRoleReplacementResult
from app.models.authorization_errors import RoleNotFoundError
from app.models.user import User
from app.usecases.admin_user_usecase import AdminUserUsecase

UsecaseFixture = tuple[
    AdminUserUsecase,
    "AdminUserRepositoryStub",
    "AuthorizationRepositoryStub",
    "AuthRepositoryStub",
    "SampleItemRepositoryStub",
    "UnitOfWorkStub",
]


class UnitOfWorkStub:

    def __init__(self) -> None:
        self.transaction_entries = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        self.transaction_entries += 1
        yield


class AdminUserRepositoryStub:

    def __init__(self, user: User | None = None, list_roles: tuple[str, ...] = ("admin", )) -> None:
        self.user = user
        self.list_roles = list_roles
        self.created = []
        self.updated = []
        self.list_query = None

    async def list_users(self, query, page):
        self.list_query = (query, page)
        if self.user is None:
            return AdminOffsetPageResult(items=[], total=0, offset=page.offset, limit=page.limit)
        return AdminOffsetPageResult(
            items=[AdminUserRecord(user=self.user, roles=self.list_roles)],
            total=1,
            offset=page.offset,
            limit=page.limit,
        )

    async def get_user(self, user_id):
        del user_id
        return self.user

    async def create_user(self, email, password_hash, is_active):
        user = User(
            id=UUID("00000000-0000-0000-0000-000000000003"),
            email=email,
            password_hash=password_hash,
            is_active=is_active,
            registered_at=datetime(2026, 1, 1, tzinfo=UTC),
            modified_at=datetime(2026, 1, 1, tzinfo=UTC),
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
            updated_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
        self.user = user
        self.created.append((email, password_hash, is_active))
        return user

    async def update_user(self, user_id, changes, password_hash):
        self.updated.append((user_id, changes, password_hash))
        if self.user is None:
            raise UserNotFoundError(user_id)
        if "email" in changes.fields_set and changes.email is not None:
            self.user.email = changes.email
        if "is_active" in changes.fields_set and changes.is_active is not None:
            self.user.is_active = changes.is_active
        if "password" in changes.fields_set:
            self.user.password_hash = password_hash
        return self.user


class AuthorizationRepositoryStub:

    def __init__(self, existing_roles: tuple[str, ...] = ()) -> None:
        self.existing_roles = existing_roles
        self.replacements = []
        self.deleted_roles_for_user = []

    async def get_user_role_codes(self, user_id):
        del user_id
        return self.existing_roles

    async def replace_user_roles(self, user_id, role_codes, assigned_by_user_id):
        self.replacements.append((user_id, role_codes, assigned_by_user_id))
        existing_roles = self.existing_roles
        self.existing_roles = tuple(sorted(role_codes))
        return UserRoleReplacementResult(
            user_id=user_id,
            granted_role_codes=tuple(sorted(set(role_codes) - set(existing_roles))),
            revoked_role_codes=tuple(sorted(set(existing_roles) - set(role_codes))),
            current_role_codes=tuple(sorted(role_codes)),
        )

    async def delete_roles_for_user(self, user_id):
        self.deleted_roles_for_user.append(user_id)
        return 1


class AuthRepositoryStub:

    def __init__(self) -> None:
        self.audit_logs = []
        self.revoked_sessions = []
        self.deleted_identities = []
        self.marked_deleted = []

    async def create_audit_log(self, audit_log):
        self.audit_logs.append(audit_log)

    async def revoke_sessions_for_user(self, user_id, revoked_at):
        self.revoked_sessions.append((user_id, revoked_at))
        return 1

    async def delete_auth_identities_for_user(self, user_id):
        self.deleted_identities.append(user_id)
        return 1

    async def mark_user_deleted(self, user_id, deleted_at, *, session_id, ip_address):
        self.marked_deleted.append((user_id, deleted_at, session_id, ip_address))
        return User(
            id=user_id,
            email="deleted@example.com",
            password_hash="hash",
            is_active=True,
            deleted_at=deleted_at,
        )


class SampleItemRepositoryStub:

    def __init__(self) -> None:
        self.deleted_owners = []

    async def delete_all_for_owner(self, owner_user_id):
        self.deleted_owners.append(owner_user_id)


class PasswordHashExecutorStub:

    async def hash(self, raw_password):
        return f"hashed:{raw_password}"


class LoggerStub:

    def warning(self, *args, **kwargs):
        del args, kwargs


def _user(user_id: UUID | None = None, *, is_active: bool = True) -> User:
    return User(
        id=user_id or UUID("00000000-0000-0000-0000-000000000001"),
        email="admin@example.com",
        password_hash="hash",
        is_active=is_active,
        registered_at=datetime(2026, 1, 1, tzinfo=UTC),
        modified_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def _auth_context() -> AuthenticatedSessionContext:
    user = _user(UUID("00000000-0000-0000-0000-000000000002"))
    session = AuthSession(
        id=UUID("00000000-0000-0000-0000-000000000010"),
        user_id=user.id,
        session_token_hash="session",
        csrf_token_hash="csrf",
        expires_at=datetime(2026, 2, 1, tzinfo=UTC),
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset({"admin"}),
        permissions=frozenset({"admin:access"}),
    )


def _usecase(
        *,
        user: User | None = None,
        existing_roles: tuple[str, ...] = (),
        list_roles: tuple[str, ...] = ("admin", ),
) -> UsecaseFixture:
    admin_repository = AdminUserRepositoryStub(user, list_roles)
    authorization_repository = AuthorizationRepositoryStub(existing_roles)
    auth_repository = AuthRepositoryStub()
    sample_repository = SampleItemRepositoryStub()
    unit_of_work = UnitOfWorkStub()
    usecase = AdminUserUsecase(
        admin_user_repository=admin_repository,
        auth_repository=auth_repository,
        authorization_repository=authorization_repository,
        sample_item_repository=sample_repository,
        unit_of_work=unit_of_work,
        password_hash_executor=PasswordHashExecutorStub(),
        logger=LoggerStub(),
    )
    return (
        usecase,
        admin_repository,
        authorization_repository,
        auth_repository,
        sample_repository,
        unit_of_work,
    )


@pytest.mark.asyncio
async def test_list_users_filters_unknown_roles_from_public_records() -> None:
    target = _user()
    usecase, _, _, _, _, _ = _usecase(
        user=target,
        list_roles=("admin", "retired-role"),
    )

    result = await usecase.list_users(query=AdminUserListQuery(), offset=0, limit=20)

    assert result.items[0].roles == ("admin", )


@pytest.mark.asyncio
async def test_create_user_hashes_password_assigns_roles_and_records_audit() -> None:
    (
        usecase,
        admin_repository,
        authorization_repository,
        auth_repository,
        _,
        unit_of_work,
    ) = _usecase()

    detail = await usecase.create_user(
        actor_context=_auth_context(),
        email="New@Example.com",
        password="Password@123!",
        is_active=True,
        roles=("admin", "admin"),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert detail.user.email == "new@example.com"
    assert admin_repository.created == [("new@example.com", "hashed:Password@123!", True)]
    assert authorization_repository.replacements == [(detail.user.id, ("admin", ),
                                                      _auth_context().user.id)]
    assert detail.roles == ("admin", )
    assert detail.permissions == ("admin:access", )
    assert [log.event_type for log in auth_repository.audit_logs] == [
        "user_created_by_admin",
        "role_granted",
    ]
    assert auth_repository.audit_logs[0].detail_json["changedFields"] == [
        "email",
        "password",
        "isActive",
        "roles",
    ]
    assert auth_repository.audit_logs[1].detail_json["resultingRoles"] == ["admin"]
    assert unit_of_work.transaction_entries == 1


@pytest.mark.asyncio
async def test_create_user_rejects_weak_password_before_writing() -> None:
    usecase, admin_repository, authorization_repository, _, _, _ = _usecase()

    with pytest.raises(WeakPasswordError):
        await usecase.create_user(
            actor_context=_auth_context(),
            email="new@example.com",
            password="short",
            is_active=True,
            roles=(),
            ip_address=None,
            user_agent=None,
        )

    assert admin_repository.created == []
    assert authorization_repository.replacements == []


@pytest.mark.asyncio
async def test_update_user_replaces_roles_revokes_sessions_for_password_and_inactive() -> None:
    target = _user()
    usecase, admin_repository, authorization_repository, auth_repository, _, _ = _usecase(
        user=target,
        existing_roles=("member", ),
    )

    detail = await usecase.update_user(
        actor_context=_auth_context(),
        user_id=target.id,
        changes=AdminUserUpdateChanges(
            password="Password@123!",
            is_active=False,
            roles=("admin", "admin"),
            fields_set=frozenset({"password", "is_active", "roles"}),
        ),
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert admin_repository.updated[0][2] == "hashed:Password@123!"
    assert authorization_repository.replacements == [(target.id, ("admin", ),
                                                      _auth_context().user.id)]
    assert auth_repository.revoked_sessions
    assert detail.roles == ("admin", )
    assert [log.event_type for log in auth_repository.audit_logs] == [
        "role_granted",
        "role_revoked",
        "user_updated_by_admin",
    ]
    assert auth_repository.audit_logs[-1].detail_json["changedFields"] == [
        "password",
        "isActive",
        "roles",
    ]


@pytest.mark.asyncio
async def test_update_user_email_only_does_not_revoke_sessions() -> None:
    target = _user()
    usecase, _, _, auth_repository, _, _ = _usecase(user=target)

    await usecase.update_user(
        actor_context=_auth_context(),
        user_id=target.id,
        changes=AdminUserUpdateChanges(
            email="changed@example.com",
            fields_set=frozenset({"email"}),
        ),
        ip_address=None,
        user_agent=None,
    )

    assert auth_repository.revoked_sessions == []


@pytest.mark.asyncio
async def test_update_user_empty_patch_is_noop_without_transaction_or_audit() -> None:
    target = _user()
    usecase, admin_repository, _, auth_repository, _, unit_of_work = _usecase(
        user=target,
        existing_roles=("admin", ),
    )

    detail = await usecase.update_user(
        actor_context=_auth_context(),
        user_id=target.id,
        changes=AdminUserUpdateChanges(fields_set=frozenset()),
        ip_address=None,
        user_agent=None,
    )

    assert detail.user is target
    assert detail.roles == ("admin", )
    assert admin_repository.updated == []
    assert auth_repository.audit_logs == []
    assert unit_of_work.transaction_entries == 0


@pytest.mark.asyncio
async def test_update_user_rejects_unknown_roles_before_writing() -> None:
    target = _user()
    usecase, admin_repository, authorization_repository, _, _, _ = _usecase(user=target)

    with pytest.raises(RoleNotFoundError):
        await usecase.update_user(
            actor_context=_auth_context(),
            user_id=target.id,
            changes=AdminUserUpdateChanges(
                roles=("missing", ),
                fields_set=frozenset({"roles"}),
            ),
            ip_address=None,
            user_agent=None,
        )

    assert admin_repository.updated == []
    assert authorization_repository.replacements == []


@pytest.mark.asyncio
async def test_delete_user_cleans_owned_resources_and_records_admin_audit() -> None:
    target = _user()
    usecase, _, authorization_repository, auth_repository, sample_repository, _ = _usecase(
        user=target)

    await usecase.delete_user(
        actor_context=_auth_context(),
        user_id=target.id,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert sample_repository.deleted_owners == [target.id]
    assert authorization_repository.deleted_roles_for_user == [target.id]
    assert auth_repository.deleted_identities == [target.id]
    assert auth_repository.marked_deleted[0][0] == target.id
    assert auth_repository.revoked_sessions[0][0] == target.id
    assert auth_repository.audit_logs[-1].event_type == "user_deleted_by_admin"


@pytest.mark.asyncio
async def test_get_user_raises_for_deleted_or_missing_user() -> None:
    usecase, _, _, _, _, _ = _usecase(user=None)

    with pytest.raises(UserNotFoundError):
        await usecase.get_user(uuid4())
