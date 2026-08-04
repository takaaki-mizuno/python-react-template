from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models.sample_item import SampleItem
from app.services.auth_repository import AuthRepository
from app.services.sample_item_repository import SampleItemRepository
from app.services.unit_of_work import UnitOfWork


def _session_factory(async_engine):
    return async_sessionmaker(bind=async_engine, class_=AsyncSession, expire_on_commit=False)


async def test_delete_all_for_owner_keeps_other_users_items(async_engine, async_session) -> None:
    session_factory = _session_factory(async_engine)
    unit_of_work = UnitOfWork(session_factory=session_factory)
    auth_repository = AuthRepository(unit_of_work=unit_of_work)
    sample_repository = SampleItemRepository(unit_of_work=unit_of_work)
    user_a = await auth_repository.create_user("owner-a@example.com", "hash")
    user_b = await auth_repository.create_user("owner-b@example.com", "hash")
    item_a = await sample_repository.create(SampleItem(owner_user_id=user_a.id, title="A"))
    item_b = await sample_repository.create(SampleItem(owner_user_id=user_b.id, title="B"))

    await sample_repository.delete_all_for_owner(user_a.id)

    remaining_ids = (await async_session.execute(select(SampleItem.id))).scalars().all()
    assert item_a.id not in remaining_ids
    assert item_b.id in remaining_ids
