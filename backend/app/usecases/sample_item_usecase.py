import base64
import binascii
import json
from datetime import datetime
from uuid import UUID

from injector import inject

from app.interfaces.services.sample_item_repository_interface import SampleItemRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.sample_item_usecase_interface import SampleItemUsecaseInterface
from app.models.sample_item import (SampleItem, SampleItemCursor, SampleItemListResult,
                                    SampleItemUpdateChanges)
from app.models.sample_item_errors import InvalidSampleItemCursorError, SampleItemNotFoundError


class SampleItemUsecase(SampleItemUsecaseInterface):

    @inject
    def __init__(
        self,
        repository: SampleItemRepositoryInterface,
        unit_of_work: UnitOfWorkInterface,
    ) -> None:
        self._repository = repository
        self._unit_of_work = unit_of_work

    async def list_items(
        self,
        owner_user_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> SampleItemListResult:
        decoded_cursor = self.decode_cursor(cursor) if cursor else None
        items = await self._repository.list_by_owner(
            owner_user_id,
            fetch_limit=limit + 1,
            cursor=decoded_cursor,
        )
        return SampleItemListResult(
            items=items[:limit],
            next_cursor=self.next_cursor_for_items(items, limit),
        )

    async def create_item(
        self,
        owner_user_id: UUID,
        title: str,
        description: str | None,
    ) -> SampleItem:
        item = SampleItem(
            owner_user_id=owner_user_id,
            title=title,
            description=description,
        )
        return await self._repository.create(item)

    async def get_item(self, owner_user_id: UUID, item_id: UUID) -> SampleItem:
        item = await self._repository.get_by_id_for_owner(item_id, owner_user_id)
        if item is None:
            raise SampleItemNotFoundError
        return item

    async def update_item(
        self,
        owner_user_id: UUID,
        item_id: UUID,
        changes: SampleItemUpdateChanges,
    ) -> SampleItem:
        if not changes.fields_set:
            return await self.get_item(owner_user_id, item_id)

        async with self._unit_of_work.transaction():
            item = await self.get_item(owner_user_id, item_id)
            if "title" in changes.fields_set:
                if changes.title is None:
                    raise ValueError("title cannot be None when included in fields_set")
                item.title = changes.title
            if "description" in changes.fields_set:
                item.description = changes.description
            if "is_completed" in changes.fields_set:
                if changes.is_completed is None:
                    raise ValueError("is_completed cannot be None when included in fields_set")
                item.is_completed = changes.is_completed
            return await self._repository.update(item)

    async def delete_item(self, owner_user_id: UUID, item_id: UUID) -> None:
        async with self._unit_of_work.transaction():
            item = await self.get_item(owner_user_id, item_id)
            await self._repository.delete(item)

    def next_cursor_for_items(self, items: list[SampleItem], limit: int) -> str | None:
        if len(items) <= limit:
            return None
        return self.encode_cursor(items[limit - 1])

    def encode_cursor(self, item: SampleItem) -> str:
        payload = {
            "created_at": item.registered_at.isoformat(),
            "id": str(item.id),
        }
        return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")

    def decode_cursor(self, cursor: str) -> SampleItemCursor:
        try:
            payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")))
            registered_at = datetime.fromisoformat(payload["created_at"])
            if registered_at.tzinfo is None:
                raise ValueError("created_at must be timezone-aware")
            return SampleItemCursor(registered_at=registered_at, id=UUID(payload["id"]))
        except (binascii.Error, KeyError, TypeError, UnicodeError, ValueError) as error:
            raise InvalidSampleItemCursorError from error
