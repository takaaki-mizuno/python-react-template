from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.sample_item import SampleItem, SampleItemCursor
from app.services.sample_item_repository import SampleItemRepository


class ResultStub:

    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        return self._rows[0] if self._rows else None


class SessionStub:

    def __init__(self, rows=None):
        self.rows = rows or []
        self.statements = []
        self.added = []
        self.deleted = []
        self.flush_called = False
        self.commit_called = False
        self.refreshed = []

    async def exec(self, statement):
        self.statements.append(statement)
        return ResultStub(self.rows)

    def add(self, item):
        self.added.append(item)

    async def delete(self, item):
        self.deleted.append(item)

    async def flush(self):
        self.flush_called = True

    async def commit(self):
        self.commit_called = True

    async def refresh(self, item):
        self.refreshed.append(item)


class UnitOfWorkStub(UnitOfWorkInterface):

    def __init__(self, session, in_transaction: bool = False):
        self.session = session
        self.in_transaction = in_transaction

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    @asynccontextmanager
    async def session_scope(self):
        yield self.session

    def is_transaction_session(self, session) -> bool:
        return self.in_transaction and session is self.session


def _compiled(statement) -> str:
    return str(statement.compile(compile_kwargs={"literal_binds": False}))


@pytest.mark.asyncio
async def test_list_by_owner_filters_orders_and_limits() -> None:
    owner_user_id = uuid4()
    session = SessionStub()
    repository = SampleItemRepository(unit_of_work=UnitOfWorkStub(session))

    await repository.list_by_owner(owner_user_id, fetch_limit=21, cursor=None)

    sql = _compiled(session.statements[0])
    assert "WHERE sample_items.owner_user_id = " in sql
    assert "ORDER BY sample_items.registered_at DESC, sample_items.id DESC" in sql
    assert "LIMIT " in sql


@pytest.mark.asyncio
async def test_list_by_owner_applies_desc_keyset_cursor() -> None:
    owner_user_id = uuid4()
    cursor = SampleItemCursor(
        registered_at=datetime(2026, 8, 2, 1, 2, 3, tzinfo=UTC),
        id=uuid4(),
    )
    session = SessionStub()
    repository = SampleItemRepository(unit_of_work=UnitOfWorkStub(session))

    await repository.list_by_owner(owner_user_id, fetch_limit=10, cursor=cursor)

    sql = _compiled(session.statements[0])
    assert "sample_items.registered_at < " in sql
    assert "sample_items.registered_at = " in sql
    assert "sample_items.id < " in sql


@pytest.mark.asyncio
async def test_get_by_id_for_owner_filters_id_and_owner() -> None:
    item_id = uuid4()
    owner_user_id = uuid4()
    session = SessionStub()
    repository = SampleItemRepository(unit_of_work=UnitOfWorkStub(session))

    await repository.get_by_id_for_owner(item_id, owner_user_id)

    sql = _compiled(session.statements[0])
    assert "sample_items.id = " in sql
    assert "sample_items.owner_user_id = " in sql


@pytest.mark.asyncio
async def test_create_uses_flush_inside_transaction_without_refresh() -> None:
    item = SampleItem(owner_user_id=uuid4(), title="Created")
    session = SessionStub()
    repository = SampleItemRepository(unit_of_work=UnitOfWorkStub(session, in_transaction=True))

    result = await repository.create(item)

    assert result is item
    assert session.added == [item]
    assert session.flush_called is True
    assert session.commit_called is False
    assert session.refreshed == []


@pytest.mark.asyncio
async def test_update_sets_modified_at_and_uses_commit_outside_transaction(monkeypatch) -> None:
    modified_at = datetime(2026, 8, 3, 1, 2, 3, tzinfo=UTC)
    monkeypatch.setattr("app.services.sample_item_repository.utcnow", lambda: modified_at)
    item = SampleItem(owner_user_id=uuid4(), title="Updated")
    session = SessionStub()
    repository = SampleItemRepository(unit_of_work=UnitOfWorkStub(session, in_transaction=False))

    result = await repository.update(item)

    assert result is item
    assert item.modified_at == modified_at
    assert session.added == [item]
    assert session.flush_called is False
    assert session.commit_called is True
    assert session.refreshed == []


@pytest.mark.asyncio
async def test_delete_deletes_owner_scoped_item_and_persists() -> None:
    item = SampleItem(owner_user_id=uuid4(), title="Delete")
    session = SessionStub()
    repository = SampleItemRepository(unit_of_work=UnitOfWorkStub(session, in_transaction=False))

    await repository.delete(item)

    assert session.deleted == [item]
    assert session.commit_called is True


@pytest.mark.asyncio
async def test_delete_all_for_owner_deletes_only_owner_items_and_persists() -> None:
    owner_user_id = uuid4()
    session = SessionStub()
    repository = SampleItemRepository(unit_of_work=UnitOfWorkStub(session, in_transaction=True))

    result = await repository.delete_all_for_owner(owner_user_id)

    assert result is None
    sql = _compiled(session.statements[0])
    assert "DELETE FROM sample_items" in sql
    assert "sample_items.owner_user_id = " in sql
    assert session.flush_called is True
    assert session.commit_called is False
