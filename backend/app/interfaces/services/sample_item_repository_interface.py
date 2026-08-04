from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.sample_item import SampleItem, SampleItemCursor


class SampleItemRepositoryInterface(metaclass=ABCMeta):

    @abstractmethod
    async def list_by_owner(
        self,
        owner_user_id: UUID,
        fetch_limit: int,
        cursor: SampleItemCursor | None,
    ) -> list[SampleItem]:
        raise NotImplementedError

    @abstractmethod
    async def get_by_id_for_owner(
        self,
        item_id: UUID,
        owner_user_id: UUID,
    ) -> SampleItem | None:
        raise NotImplementedError

    @abstractmethod
    async def create(self, item: SampleItem) -> SampleItem:
        raise NotImplementedError

    @abstractmethod
    async def update(self, item: SampleItem) -> SampleItem:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, item: SampleItem) -> None:
        raise NotImplementedError

    @abstractmethod
    async def delete_all_for_owner(self, owner_user_id: UUID) -> None:
        raise NotImplementedError
