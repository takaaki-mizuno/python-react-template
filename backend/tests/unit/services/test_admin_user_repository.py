from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.admin_pagination import AdminOffsetPageRequest
from app.models.admin_user import AdminUserListQuery, AdminUserUpdateChanges
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.user import User
from app.services.admin_user_repository import AdminUserRepository


class ResultStub:

    def __init__(self, values=(), rowcount: int | None = None) -> None:
        self._values = values
        self.rowcount = rowcount

    def all(self):
        return self._values

    def one_or_none(self):
        return self._values[0] if self._values else None

    def one(self):
        return self._values[0]


class SessionStub:

    def __init__(self, results=(), integrity_error_on_flush: bool = False) -> None:
        self._results = list(results)
        self.integrity_error_on_flush = integrity_error_on_flush
        self.exec_calls = []
        self.added = []
        self.flushed = False
        self.committed = False
        self.rolled_back = False
        self.refreshed = []

    async def exec(self, statement):
        self.exec_calls.append(statement)
        return self._results.pop(0)

    async def get(self, model, item_id):
        del model, item_id
        result = self._results.pop(0)
        return result.one_or_none()

    def add(self, value) -> None:
        self.added.append(value)

    async def flush(self) -> None:
        self.flushed = True
        if self.integrity_error_on_flush:
            raise IntegrityError("statement", {}, Exception("duplicate"))

    async def commit(self) -> None:
        self.committed = True
        if self.integrity_error_on_flush:
            raise IntegrityError("statement", {}, Exception("duplicate"))

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, value) -> None:
        self.refreshed.append(value)


class UnitOfWorkStub:

    def __init__(self, session: SessionStub, *, in_transaction: bool = False) -> None:
        self.session = session
        self.in_transaction = in_transaction

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[SessionStub]:
        yield self.session

    def is_transaction_session(self, session) -> bool:
        return self.in_transaction and session is self.session


def _compiled(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": False}))


def _compiled_params(statement) -> dict[str, object]:
    return statement.compile(compile_kwargs={"literal_binds": False}).params


def _user(email: str = "admin@example.com") -> User:
    return User(
        id=UUID("00000000-0000-0000-0000-000000000001"),
        email=email,
        password_hash="hash",
        is_active=True,
        registered_at=datetime(2026, 1, 1, tzinfo=UTC),
        modified_at=datetime(2026, 1, 1, tzinfo=UTC),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        updated_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


@pytest.mark.asyncio
async def test_list_users_filters_deleted_search_status_role_and_paginates() -> None:
    user = _user()
    session = SessionStub([
        ResultStub([user]),
        ResultStub([1]),
        ResultStub([(user.id, "admin")]),
    ])
    repository = AdminUserRepository(unit_of_work=UnitOfWorkStub(session))

    result = await repository.list_users(
        AdminUserListQuery(search="Admin", is_active=True, role="admin"),
        AdminOffsetPageRequest(offset=20, limit=10),
    )

    list_sql = _compiled(session.exec_calls[0])
    count_sql = _compiled(session.exec_calls[1])
    list_params = _compiled_params(session.exec_calls[0])
    roles_sql = _compiled(session.exec_calls[2])
    assert "users.deleted_at IS NULL" in list_sql
    assert "lower(users.email) LIKE" in list_sql
    assert "users.is_active IS true" in list_sql
    assert "EXISTS" in list_sql
    assert "user_roles.role_code =" in list_sql
    assert "ORDER BY users.registered_at DESC, users.id DESC" in list_sql
    assert "LIMIT " in list_sql
    assert "OFFSET " in list_sql
    assert 10 in list_params.values()
    assert 20 in list_params.values()
    assert "count" in count_sql
    assert "users.deleted_at IS NULL" in count_sql
    assert "lower(users.email) LIKE" in count_sql
    assert "users.is_active IS true" in count_sql
    assert "EXISTS" in count_sql
    assert "user_roles.role_code =" in count_sql
    assert "user_roles.user_id IN" in roles_sql
    assert result.items[0].roles == ("admin", )
    assert result.total == 1


@pytest.mark.asyncio
async def test_list_users_escapes_like_wildcards_in_search_pattern() -> None:
    user = _user()
    session = SessionStub([
        ResultStub([user]),
        ResultStub([1]),
        ResultStub([(user.id, "admin")]),
    ])
    repository = AdminUserRepository(unit_of_work=UnitOfWorkStub(session))

    await repository.list_users(
        AdminUserListQuery(search="foo_bar%"),
        AdminOffsetPageRequest(offset=0, limit=20),
    )

    list_sql = _compiled(session.exec_calls[0])
    list_params = _compiled_params(session.exec_calls[0])
    assert "ESCAPE" in list_sql
    assert "%foo\\_bar\\%%" in list_params.values()


@pytest.mark.asyncio
async def test_get_user_returns_none_for_missing_or_deleted_user() -> None:
    session = SessionStub([ResultStub([])])
    repository = AdminUserRepository(unit_of_work=UnitOfWorkStub(session))

    result = await repository.get_user(uuid4())

    assert result is None
    assert "users.deleted_at IS NULL" in _compiled(session.exec_calls[0])


@pytest.mark.asyncio
async def test_create_user_accepts_is_active_and_refreshes() -> None:
    session = SessionStub()
    repository = AdminUserRepository(unit_of_work=UnitOfWorkStub(session, in_transaction=True))

    user = await repository.create_user("admin@example.com", "hash", is_active=False)

    assert user.email == "admin@example.com"
    assert user.password_hash == "hash"
    assert user.is_active is False
    assert session.added == [user]
    assert session.flushed is True
    assert session.committed is False
    assert session.refreshed == [user]


@pytest.mark.asyncio
async def test_create_user_converts_integrity_error_to_duplicate_email() -> None:
    session = SessionStub(integrity_error_on_flush=True)
    repository = AdminUserRepository(unit_of_work=UnitOfWorkStub(session))

    with pytest.raises(EmailAlreadyRegisteredError):
        await repository.create_user("admin@example.com", "hash", is_active=True)

    assert session.rolled_back is True


@pytest.mark.asyncio
async def test_update_user_updates_requested_fields_and_modified_at(monkeypatch) -> None:
    modified_at = datetime(2026, 1, 2, tzinfo=UTC)
    monkeypatch.setattr("app.services.admin_user_repository.utcnow", lambda: modified_at)
    user = _user()
    session = SessionStub([ResultStub([user])])
    repository = AdminUserRepository(unit_of_work=UnitOfWorkStub(session, in_transaction=True))

    result = await repository.update_user(
        user.id,
        AdminUserUpdateChanges(
            email="new@example.com",
            is_active=False,
            roles=("admin", ),
            fields_set=frozenset({"email", "is_active", "roles"}),
        ),
        password_hash=None,
    )

    assert result.email == "new@example.com"
    assert result.is_active is False
    assert result.modified_at == modified_at
    assert result.password_hash == "hash"
    assert session.added == [user]
    assert session.flushed is True
    assert "users.deleted_at IS NULL" in _compiled(session.exec_calls[0])
