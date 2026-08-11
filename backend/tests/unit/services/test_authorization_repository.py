from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest

from app.models.authorization import UnknownRoleAssignment
from app.services.authorization_repository import AuthorizationRepository


class ResultStub:

    def __init__(self, values=(), rowcount: int | None = None) -> None:
        self._values = values
        self.rowcount = rowcount

    def all(self):
        return self._values


class SessionStub:

    def __init__(self, results) -> None:
        self._results = list(results)
        self.exec_calls = []
        self.added = []
        self.commit_calls = 0

    async def exec(self, statement):
        self.exec_calls.append(statement)
        return self._results.pop(0)

    def add(self, value) -> None:
        self.added.append(value)

    async def commit(self) -> None:
        self.commit_calls += 1


class UnitOfWorkStub:

    def __init__(self, session) -> None:
        self._session = session

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[SessionStub]:
        yield self._session

    def is_transaction_session(self, _session) -> bool:
        return False


@pytest.mark.asyncio
async def test_replace_user_roles_stores_role_codes_without_catalog_lookup() -> None:
    user_id = uuid4()
    actor_id = uuid4()
    session = SessionStub([
        ResultStub(["viewer"]),
        ResultStub(rowcount=1),
        ResultStub(rowcount=1),
    ])
    repository = AuthorizationRepository(unit_of_work=UnitOfWorkStub(session))

    result = await repository.replace_user_roles(
        user_id,
        ("admin", "admin"),
        assigned_by_user_id=actor_id,
    )

    assert result.granted_role_codes == ("admin", )
    assert result.revoked_role_codes == ("viewer", )
    assert result.current_role_codes == ("admin", )
    assert session.added[0].user_id == user_id
    assert session.added[0].role_code == "admin"
    assert session.added[0].assigned_by_user_id == actor_id
    assert "UPDATE users SET modified_at=" in str(session.exec_calls[2])
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_list_unknown_role_assignments_maps_rows() -> None:
    user_id = uuid4()
    session = SessionStub([ResultStub([(user_id, "deleted-role")])])
    repository = AuthorizationRepository(unit_of_work=UnitOfWorkStub(session))

    assignments = await repository.list_unknown_role_assignments(frozenset({"admin"}))

    assert assignments == (UnknownRoleAssignment(user_id=user_id, role_code="deleted-role"), )


@pytest.mark.asyncio
async def test_delete_unknown_role_assignments_returns_rowcount() -> None:
    session = SessionStub([ResultStub(rowcount=2)])
    repository = AuthorizationRepository(unit_of_work=UnitOfWorkStub(session))

    deleted_count = await repository.delete_unknown_role_assignments(frozenset({"admin"}))

    assert deleted_count == 2
    assert session.commit_calls == 1


@pytest.mark.asyncio
async def test_delete_unknown_role_assignments_rejects_empty_known_role_set() -> None:
    session = SessionStub([])
    repository = AuthorizationRepository(unit_of_work=UnitOfWorkStub(session))

    with pytest.raises(ValueError, match="known_role_codes must not be empty"):
        await repository.delete_unknown_role_assignments(frozenset())

    assert session.exec_calls == []
    assert session.commit_calls == 0
