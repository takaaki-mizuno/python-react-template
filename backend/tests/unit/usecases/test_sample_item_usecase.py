from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.sample_item import SampleItem, SampleItemUpdateChanges
from app.models.sample_item_errors import InvalidSampleItemCursorError, SampleItemNotFoundError
from app.usecases.sample_item_usecase import SampleItemUsecase


class UnitOfWorkStub(UnitOfWorkInterface):

    def __init__(self) -> None:
        self.active = False
        self.transaction_count = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        self.transaction_count += 1
        self.active = True
        try:
            yield
        finally:
            self.active = False

    @asynccontextmanager
    async def session_scope(self):
        yield None

    def is_transaction_session(self, session) -> bool:
        return False


class RepositoryStub:

    def __init__(self, items=None, item=None, unit_of_work=None):
        self.items = items or []
        self.item = item
        self.unit_of_work = unit_of_work
        self.created = []
        self.updated = []
        self.deleted = []
        self.list_calls = []
        self.get_calls = []
        self.get_transaction_states = []
        self.update_transaction_states = []
        self.delete_transaction_states = []

    async def list_by_owner(self, owner_user_id, fetch_limit, cursor):
        self.list_calls.append((owner_user_id, fetch_limit, cursor))
        return self.items

    async def get_by_id_for_owner(self, item_id, owner_user_id):
        self.get_calls.append((item_id, owner_user_id))
        self.get_transaction_states.append(self._in_transaction())
        return self.item

    async def create(self, item):
        self.created.append(item)
        return item

    async def update(self, item):
        self.update_transaction_states.append(self._in_transaction())
        self.updated.append(item)
        return item

    async def delete(self, item):
        self.delete_transaction_states.append(self._in_transaction())
        self.deleted.append(item)

    def _in_transaction(self):
        return self.unit_of_work.active if self.unit_of_work is not None else False


def _item(owner_user_id, title="Item", created_at=None):
    return SampleItem(
        id=uuid4(),
        owner_user_id=owner_user_id,
        title=title,
        description="description",
        created_at=created_at or datetime(2026, 8, 2, 1, 2, 3, tzinfo=UTC),
        updated_at=datetime(2026, 8, 2, 1, 2, 3, tzinfo=UTC),
    )


def _usecase(repository, unit_of_work=None):
    return SampleItemUsecase(
        repository=repository,
        unit_of_work=unit_of_work or UnitOfWorkStub(),
    )


@pytest.mark.asyncio
async def test_create_item_sets_owner_user_id() -> None:
    owner_user_id = uuid4()
    repository = RepositoryStub()
    usecase = _usecase(repository)

    result = await usecase.create_item(owner_user_id, title="Created", description=None)

    assert result.owner_user_id == owner_user_id
    assert result.title == "Created"
    assert result.description is None
    assert repository.created == [result]


@pytest.mark.asyncio
async def test_list_items_fetches_limit_plus_one_and_returns_next_cursor() -> None:
    owner_user_id = uuid4()
    first = _item(owner_user_id, title="First", created_at=datetime(2026, 8, 2, 3, tzinfo=UTC))
    second = _item(owner_user_id, title="Second", created_at=datetime(2026, 8, 2, 2, tzinfo=UTC))
    repository = RepositoryStub(items=[first, second])
    usecase = _usecase(repository)

    result = await usecase.list_items(owner_user_id, limit=1, cursor=None)

    assert repository.list_calls[0] == (owner_user_id, 2, None)
    assert result.items == [first]
    assert result.next_cursor is not None


@pytest.mark.asyncio
async def test_list_items_decodes_valid_cursor() -> None:
    owner_user_id = uuid4()
    repository = RepositoryStub(items=[])
    usecase = _usecase(repository)
    cursor_item = _item(
        owner_user_id,
        created_at=datetime(2026, 8, 2, 3, 4, 5, tzinfo=UTC),
    )
    cursor = usecase.encode_cursor(cursor_item)

    await usecase.list_items(owner_user_id, limit=20, cursor=cursor)

    decoded_cursor = repository.list_calls[0][2]
    assert decoded_cursor.created_at == cursor_item.created_at
    assert decoded_cursor.id == cursor_item.id


@pytest.mark.asyncio
async def test_list_items_rejects_invalid_cursor() -> None:
    usecase = _usecase(RepositoryStub())

    with pytest.raises(InvalidSampleItemCursorError):
        await usecase.list_items(uuid4(), limit=20, cursor="not-base64")


@pytest.mark.asyncio
async def test_get_update_delete_raise_not_found() -> None:
    usecase = _usecase(RepositoryStub(item=None))
    owner_user_id = uuid4()
    item_id = uuid4()

    with pytest.raises(SampleItemNotFoundError):
        await usecase.get_item(owner_user_id, item_id)
    with pytest.raises(SampleItemNotFoundError):
        await usecase.update_item(owner_user_id, item_id, SampleItemUpdateChanges())
    with pytest.raises(SampleItemNotFoundError):
        await usecase.delete_item(owner_user_id, item_id)


@pytest.mark.asyncio
async def test_update_item_applies_only_fields_set_and_allows_description_clear() -> None:
    owner_user_id = uuid4()
    item = _item(owner_user_id)
    repository = RepositoryStub(item=item)
    usecase = _usecase(repository)

    result = await usecase.update_item(
        owner_user_id,
        item.id,
        SampleItemUpdateChanges(
            title="Updated",
            description=None,
            is_completed=True,
            fields_set=frozenset({"title", "description", "is_completed"}),
        ),
    )

    assert result.title == "Updated"
    assert result.description is None
    assert result.is_completed is True
    assert repository.updated == [item]


@pytest.mark.asyncio
async def test_update_item_uses_one_transaction_for_read_modify_write() -> None:
    owner_user_id = uuid4()
    item = _item(owner_user_id)
    unit_of_work = UnitOfWorkStub()
    repository = RepositoryStub(item=item, unit_of_work=unit_of_work)
    usecase = _usecase(repository, unit_of_work)

    await usecase.update_item(
        owner_user_id,
        item.id,
        SampleItemUpdateChanges(title="Updated", fields_set=frozenset({"title"})),
    )

    assert unit_of_work.transaction_count == 1
    assert repository.get_transaction_states == [True]
    assert repository.update_transaction_states == [True]


@pytest.mark.asyncio
async def test_delete_item_uses_one_transaction_for_read_delete() -> None:
    owner_user_id = uuid4()
    item = _item(owner_user_id)
    unit_of_work = UnitOfWorkStub()
    repository = RepositoryStub(item=item, unit_of_work=unit_of_work)
    usecase = _usecase(repository, unit_of_work)

    await usecase.delete_item(owner_user_id, item.id)

    assert unit_of_work.transaction_count == 1
    assert repository.get_transaction_states == [True]
    assert repository.delete_transaction_states == [True]


@pytest.mark.asyncio
async def test_update_item_rejects_none_for_non_nullable_changes() -> None:
    owner_user_id = uuid4()
    item = _item(owner_user_id)
    repository = RepositoryStub(item=item)
    usecase = _usecase(repository)

    with pytest.raises(ValueError):
        await usecase.update_item(
            owner_user_id,
            item.id,
            SampleItemUpdateChanges(title=None, fields_set=frozenset({"title"})),
        )

    with pytest.raises(ValueError):
        await usecase.update_item(
            owner_user_id,
            item.id,
            SampleItemUpdateChanges(is_completed=None, fields_set=frozenset({"is_completed"})),
        )

    assert item.title == "Item"
    assert item.is_completed is False
    assert repository.updated == []


@pytest.mark.asyncio
async def test_update_item_empty_changes_is_noop() -> None:
    owner_user_id = uuid4()
    item = _item(owner_user_id)
    repository = RepositoryStub(item=item)
    usecase = _usecase(repository)

    result = await usecase.update_item(owner_user_id, item.id, SampleItemUpdateChanges())

    assert result is item
    assert repository.updated == []


def test_next_cursor_uses_last_visible_item_only_when_has_more() -> None:
    owner_user_id = uuid4()
    first = _item(owner_user_id, created_at=datetime(2026, 8, 2, 3, tzinfo=UTC))
    second = _item(owner_user_id, created_at=first.created_at - timedelta(hours=1))
    usecase = _usecase(RepositoryStub(items=[first, second]))

    cursor = usecase.next_cursor_for_items([first, second], limit=1)

    assert cursor == usecase.encode_cursor(first)
    assert usecase.next_cursor_for_items([first], limit=1) is None
