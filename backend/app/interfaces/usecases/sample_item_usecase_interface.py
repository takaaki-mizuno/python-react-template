from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.sample_item import SampleItem, SampleItemListResult, SampleItemUpdateChanges


class SampleItemUsecaseInterface(metaclass=ABCMeta):

    @abstractmethod
    async def list_items(
        self,
        owner_user_id: UUID,
        limit: int,
        cursor: str | None,
    ) -> SampleItemListResult:
        raise NotImplementedError

    @abstractmethod
    async def create_item(
        self,
        owner_user_id: UUID,
        title: str,
        description: str | None,
    ) -> SampleItem:
        raise NotImplementedError

    @abstractmethod
    async def get_item(self, owner_user_id: UUID, item_id: UUID) -> SampleItem:
        raise NotImplementedError

    @abstractmethod
    async def update_item(
        self,
        owner_user_id: UUID,
        item_id: UUID,
        changes: SampleItemUpdateChanges,
    ) -> SampleItem:
        raise NotImplementedError

    @abstractmethod
    async def delete_item(self, owner_user_id: UUID, item_id: UUID) -> None:
        raise NotImplementedError
