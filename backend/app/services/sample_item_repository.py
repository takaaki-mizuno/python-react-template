from uuid import UUID

from injector import inject
from sqlmodel import col, or_, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.sample_item_repository_interface import SampleItemRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.sample_item import SampleItem, SampleItemCursor


class SampleItemRepository(SampleItemRepositoryInterface):

    @inject
    def __init__(self, unit_of_work: UnitOfWorkInterface) -> None:
        self._unit_of_work = unit_of_work

    async def _persist(self, session: AsyncSession) -> None:
        if self._unit_of_work.is_transaction_session(session):
            await session.flush()
        else:
            await session.commit()

    async def list_by_owner(
        self,
        owner_user_id: UUID,
        fetch_limit: int,
        cursor: SampleItemCursor | None,
    ) -> list[SampleItem]:
        async with self._unit_of_work.session_scope() as session:
            created_at_col = col(SampleItem.created_at)
            id_col = col(SampleItem.id)
            statement = select(SampleItem).where(col(SampleItem.owner_user_id) == owner_user_id)
            if cursor is not None:
                statement = statement.where(
                    or_(
                        created_at_col < cursor.created_at,
                        (created_at_col == cursor.created_at) & (id_col < cursor.id),
                    ))
            statement = statement.order_by(
                created_at_col.desc(),
                id_col.desc(),
            ).limit(fetch_limit)
            result = await session.exec(statement)
            return list(result.all())

    async def get_by_id_for_owner(
        self,
        item_id: UUID,
        owner_user_id: UUID,
    ) -> SampleItem | None:
        async with self._unit_of_work.session_scope() as session:
            statement = select(SampleItem).where(
                col(SampleItem.id) == item_id,
                col(SampleItem.owner_user_id) == owner_user_id,
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def create(self, item: SampleItem) -> SampleItem:
        async with self._unit_of_work.session_scope() as session:
            session.add(item)
            await self._persist(session)
            return item

    async def update(self, item: SampleItem) -> SampleItem:
        async with self._unit_of_work.session_scope() as session:
            session.add(item)
            await self._persist(session)
            return item

    async def delete(self, item: SampleItem) -> None:
        async with self._unit_of_work.session_scope() as session:
            await session.delete(item)
            await self._persist(session)
