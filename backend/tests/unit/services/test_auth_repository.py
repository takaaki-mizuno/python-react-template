from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from inspect import Parameter, signature
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession
from typing_extensions import get_type_hints

from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.libraries.clock import utcnow
from app.models.auth_errors import (AuthSessionNotFoundError, EmailAlreadyRegisteredError,
                                    UserNotFoundError)
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.language import DEFAULT_LANGUAGE_CODE
from app.models.user import User
from app.services.auth_repository import AuthRepository


class FailingFlushSession:

    def __init__(self) -> None:
        self.rollback_called = False

    def add(self, _instance: object) -> None:
        pass

    async def flush(self) -> None:
        raise IntegrityError("insert users", {}, Exception("duplicate email"))

    async def commit(self) -> None:
        raise AssertionError("commit must not be used inside a transaction")

    async def rollback(self) -> None:
        self.rollback_called = True

    async def refresh(self, _instance: object) -> None:
        raise AssertionError("refresh must not run after IntegrityError")


class TransactionSessionUnitOfWork(UnitOfWorkInterface):

    def __init__(self) -> None:
        self.session = FailingFlushSession()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        yield self.session  # type: ignore[misc]

    def is_transaction_session(self, session: AsyncSession) -> bool:
        return session is self.session


class ResultStub:

    def __init__(self, value: object | None = None, rowcount: int = 0) -> None:
        self._value = value
        self.rowcount = rowcount

    def one_or_none(self) -> object | None:
        return self._value

    def all(self) -> list[object]:
        return []

    def scalar_one(self) -> object:
        return self._value


class ConnectionStub:

    async def execute(self, _statement, _params):
        return ResultStub(value=True)


class CapturingSession:

    def __init__(self, get_result: object | None = None, exec_rowcount: int = 2) -> None:
        self.statements = []
        self.added = []
        self.get_result = get_result
        self.exec_rowcount = exec_rowcount
        self.commit_calls = 0
        self.refresh_calls = 0

    async def exec(self, statement):
        self.statements.append(statement)
        return ResultStub(rowcount=self.exec_rowcount)

    async def get(self, _model, _identity):
        return self.get_result

    async def connection(self):
        return ConnectionStub()

    def add(self, instance: object) -> None:
        self.added.append(instance)

    async def commit(self) -> None:
        self.commit_calls += 1

    async def flush(self) -> None:
        raise AssertionError("flush must not be used outside a transaction")

    async def refresh(self, _instance: object) -> None:
        self.refresh_calls += 1


class CapturingUnitOfWork(UnitOfWorkInterface):

    def __init__(self, session: CapturingSession) -> None:
        self.session = session
        self.session_scope_entries = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        self.session_scope_entries += 1
        yield self.session  # type: ignore[misc]

    def is_transaction_session(self, session: AsyncSession) -> bool:
        return False


def _compiled_sql(statement) -> str:
    return str(statement.compile(dialect=postgresql.dialect()))


@pytest.mark.asyncio
async def test_create_user_does_not_rollback_integrity_error_inside_transaction() -> None:
    unit_of_work = TransactionSessionUnitOfWork()
    repository = AuthRepository(unit_of_work=unit_of_work)

    with pytest.raises(EmailAlreadyRegisteredError):
        await repository.create_user(email="user@example.com", password_hash="hash")

    assert unit_of_work.session.rollback_called is False


def test_create_user_accepts_nullable_password_hash_type_annotation():
    interface_hints = get_type_hints(AuthRepositoryInterface.create_user)
    concrete_hints = get_type_hints(AuthRepository.create_user)

    assert interface_hints["password_hash"] == str | None
    assert concrete_hints["password_hash"] == str | None


@pytest.mark.asyncio
async def test_create_user_defaults_language_code_to_ja() -> None:
    session = CapturingSession()
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    await repository.create_user(email="user@example.com", password_hash="hash")

    assert isinstance(session.added[0], User)
    assert session.added[0].language_code == DEFAULT_LANGUAGE_CODE


@pytest.mark.asyncio
async def test_create_user_accepts_language_code() -> None:
    session = CapturingSession()
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    await repository.create_user(email="user@example.com", password_hash="hash", language_code="en")

    assert isinstance(session.added[0], User)
    assert session.added[0].language_code == "en"


@pytest.mark.asyncio
async def test_update_user_language_updates_language_and_modified_at() -> None:
    modified_at = utcnow()
    user = User(email="user@example.com", password_hash="hash", language_code="ja")
    session = CapturingSession(get_result=user)
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    updated_user = await repository.update_user_language(user.id, "en", modified_at)

    assert updated_user.language_code == "en"
    assert updated_user.modified_at == modified_at
    assert session.added == [user]


def test_repository_exposes_only_authentication_specific_user_id_lookup():
    assert hasattr(AuthRepositoryInterface, "find_user_by_id_for_authentication")
    assert hasattr(AuthRepository, "find_user_by_id_for_authentication")
    assert not hasattr(AuthRepositoryInterface, "find_user_by_id")
    assert not hasattr(AuthRepository, "find_user_by_id")


def test_repository_exposes_explicit_session_pruning_method_name():
    assert hasattr(AuthRepositoryInterface, "delete_sessions_expired_before")
    assert hasattr(AuthRepository, "delete_sessions_expired_before")
    assert not hasattr(AuthRepositoryInterface, "delete_expired_sessions")
    assert not hasattr(AuthRepository, "delete_expired_sessions")


def test_mark_user_deleted_requires_audit_context_keywords():
    interface_signature = signature(AuthRepositoryInterface.mark_user_deleted)
    concrete_signature = signature(AuthRepository.mark_user_deleted)

    for target_signature in (interface_signature, concrete_signature):
        assert target_signature.parameters["session_id"].kind == Parameter.KEYWORD_ONLY
        assert target_signature.parameters["session_id"].default is Parameter.empty
        assert target_signature.parameters["ip_address"].kind == Parameter.KEYWORD_ONLY
        assert target_signature.parameters["ip_address"].default is Parameter.empty


@pytest.mark.asyncio
async def test_find_user_by_email_filters_deleted_users_in_statement() -> None:
    session = CapturingSession()
    unit_of_work = CapturingUnitOfWork(session)
    repository = AuthRepository(unit_of_work=unit_of_work)

    await repository.find_user_by_email("user@example.com")

    compiled_sql = _compiled_sql(session.statements[0])
    assert "lower(users.email)" in compiled_sql
    assert "users.deleted_at IS NULL" in compiled_sql
    assert unit_of_work.session_scope_entries == 1


@pytest.mark.asyncio
async def test_find_user_by_id_for_authentication_does_not_filter_deleted_users() -> None:
    session = CapturingSession()
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    await repository.find_user_by_id_for_authentication(uuid4())

    compiled_sql = _compiled_sql(session.statements[0])
    assert "users.id" in compiled_sql
    assert "users.deleted_at IS NULL" not in compiled_sql


@pytest.mark.asyncio
async def test_find_identities_by_user_id_orders_stably_by_linked_at_and_id() -> None:
    session = CapturingSession()
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    await repository.find_identities_by_user_id(uuid4())

    compiled_sql = _compiled_sql(session.statements[0])
    assert "ORDER BY auth_identities.linked_at, auth_identities.id" in compiled_sql


@pytest.mark.asyncio
async def test_record_user_login_raises_user_not_found_for_deleted_user() -> None:
    user_id = uuid4()
    user = User(id=user_id, email="deleted@example.com", deleted_at=utcnow())
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(CapturingSession(user)))

    with pytest.raises(UserNotFoundError):
        await repository.record_user_login(user_id, utcnow())


@pytest.mark.asyncio
async def test_mark_user_deleted_raises_user_not_found_for_missing_user() -> None:
    user_id = uuid4()
    repository = AuthRepository(
        unit_of_work=CapturingUnitOfWork(CapturingSession(None, exec_rowcount=0)))

    with pytest.raises(UserNotFoundError):
        await repository.mark_user_deleted(user_id, utcnow(), session_id=None, ip_address=None)


@pytest.mark.asyncio
async def test_mark_user_deleted_does_not_audit_when_user_already_deleted() -> None:
    user_id = uuid4()
    first_deleted_at = utcnow() - timedelta(minutes=5)
    second_deleted_at = utcnow()
    user = User(
        id=user_id,
        email="deleted@example.com",
        password_hash="hashed",
        deleted_at=first_deleted_at,
    )
    session = CapturingSession(user, exec_rowcount=0)
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    deleted_user = await repository.mark_user_deleted(
        user_id,
        second_deleted_at,
        session_id=None,
        ip_address=None,
    )

    assert deleted_user.deleted_at == first_deleted_at
    assert all(
        getattr(instance, "event_type", None) != AuthEventType.USER_MARKED_DELETED
        for instance in session.added)


@pytest.mark.asyncio
async def test_mark_user_deleted_records_required_audit_log() -> None:
    user_id = uuid4()
    deleted_at = utcnow()
    user = User(id=user_id, email="delete@example.com")
    session = CapturingSession(user, exec_rowcount=1)
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))
    session_id = uuid4()

    await repository.mark_user_deleted(
        user_id,
        deleted_at,
        session_id=session_id,
        ip_address="127.0.0.1",
    )

    delete_sql = _compiled_sql(session.statements[0])
    audit_log = next(instance for instance in session.added if instance is not user)
    assert "modified_at" in delete_sql
    assert audit_log.user_id == user_id
    assert audit_log.session_id == session_id
    assert audit_log.event_type == AuthEventType.USER_MARKED_DELETED
    assert audit_log.ip_address == "127.0.0.1"
    assert audit_log.occurred_at == deleted_at


@pytest.mark.asyncio
async def test_touch_session_raises_auth_session_not_found_for_missing_session() -> None:
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(CapturingSession(None)))
    now = utcnow()

    with pytest.raises(AuthSessionNotFoundError):
        await repository.touch_session(uuid4(), now, now + timedelta(minutes=5))


@pytest.mark.asyncio
async def test_update_session_csrf_token_hash_raises_auth_session_not_found() -> None:
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(CapturingSession(None)))

    with pytest.raises(AuthSessionNotFoundError):
        await repository.update_session_csrf_token_hash(uuid4(), "csrf-hash")


@pytest.mark.asyncio
async def test_delete_sessions_expired_before_uses_session_scope_and_expires_threshold() -> None:
    session = CapturingSession()
    unit_of_work = CapturingUnitOfWork(session)
    repository = AuthRepository(unit_of_work=unit_of_work)

    deleted_count = await repository.delete_sessions_expired_before(utcnow())

    compiled_sql = _compiled_sql(session.statements[0])
    assert deleted_count == 2
    assert "DELETE FROM auth_sessions" in compiled_sql
    assert "auth_sessions.expires_at <" in compiled_sql
    assert unit_of_work.session_scope_entries == 1


@pytest.mark.asyncio
async def test_delete_audit_logs_occurred_before_uses_session_scope_and_occurred_threshold(
) -> None:
    session = CapturingSession()
    unit_of_work = CapturingUnitOfWork(session)
    repository = AuthRepository(unit_of_work=unit_of_work)

    deleted_count = await repository.delete_audit_logs_occurred_before(utcnow())

    compiled_sql = _compiled_sql(session.statements[0])
    assert deleted_count == 2
    assert "DELETE FROM auth_audit_logs" in compiled_sql
    assert "auth_audit_logs.occurred_at <" in compiled_sql
    assert unit_of_work.session_scope_entries == 1


@pytest.mark.asyncio
async def test_rejected_session_replay_uses_stable_latest_audit_order() -> None:
    auth_session = AuthSession(
        user_id=uuid4(),
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        ip_address=None,
        user_agent=None,
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=5),
    )
    session = CapturingSession()
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    await repository.record_rejected_session_replay(
        auth_session,
        ip_address=None,
        user_agent=None,
        replayed_at=utcnow(),
        window_seconds=60,
    )

    compiled_sql = _compiled_sql(session.statements[0])
    assert "ORDER BY auth_audit_logs.occurred_at DESC, auth_audit_logs.id DESC" in compiled_sql
