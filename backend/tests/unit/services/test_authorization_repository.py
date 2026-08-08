from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from app.models.authorization import Role
from app.models.authorization_errors import PermissionNotFoundError
from app.services.authorization_repository import AuthorizationRepository


class ResultStub:

    def __init__(self, values) -> None:
        self._values = values

    def one_or_none(self):
        if not self._values:
            return None
        return self._values[0]

    def all(self):
        return self._values


class SessionStub:

    def __init__(self, results) -> None:
        self._results = list(results)

    async def exec(self, _statement):
        return self._results.pop(0)


class UnitOfWorkStub:

    def __init__(self, session) -> None:
        self._session = session

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[SessionStub]:
        yield self._session

    def is_transaction_session(self, _session) -> bool:
        return False


@pytest.mark.asyncio
async def test_replace_role_permissions_raises_permission_not_found_for_missing_permissions():
    session = SessionStub([
        ResultStub([Role(code="admin", display_name="Admin")]),
        ResultStub([]),
    ])
    repository = AuthorizationRepository(unit_of_work=UnitOfWorkStub(session))

    with pytest.raises(PermissionNotFoundError) as exc_info:
        await repository.replace_role_permissions("admin", ("missing:permission", ))

    assert exc_info.value.permission_codes == frozenset({"missing:permission"})
