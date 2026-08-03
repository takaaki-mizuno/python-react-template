from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.user import User
from app.services.auth_repository import AuthRepository
from app.services.unit_of_work import UnitOfWork

pytestmark = pytest.mark.integration


@pytest.fixture
def session_factory(async_engine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


@pytest.fixture
def unit_of_work(session_factory: async_sessionmaker[AsyncSession], ) -> UnitOfWork:
    return UnitOfWork(session_factory=session_factory)


class SecondRepository:

    def __init__(self, unit_of_work: UnitOfWorkInterface) -> None:
        self._unit_of_work = unit_of_work
        self.sessions: list[AsyncSession] = []

    async def capture_session(self) -> AsyncSession:
        async with self._unit_of_work.session_scope() as session:
            self.sessions.append(session)
            return session

    async def find_user_by_email(self, email: str) -> User | None:
        async with self._unit_of_work.session_scope() as session:
            self.sessions.append(session)
            result = await session.exec(select(User).where(User.email == email))
            return result.one_or_none()


async def _find_user(
    session_factory: async_sessionmaker[AsyncSession],
    email: str,
) -> User | None:
    async with session_factory() as session:
        result = await session.exec(select(User).where(User.email == email))
        return result.one_or_none()


@pytest.mark.asyncio
async def test_transaction_reuses_same_session_for_nested_scopes(
    unit_of_work: UnitOfWork, ) -> None:
    async with unit_of_work.transaction():
        async with unit_of_work.session_scope() as first_session:
            assert unit_of_work.is_transaction_session(first_session) is True
        async with unit_of_work.session_scope() as second_session:
            assert second_session is first_session


@pytest.mark.asyncio
async def test_repositories_share_session_inside_one_transaction(
    unit_of_work: UnitOfWork, ) -> None:
    auth_repository = AuthRepository(unit_of_work=unit_of_work)
    second_repository = SecondRepository(unit_of_work)
    email = f"{uuid4()}@example.com"

    async with unit_of_work.transaction():
        first_session = await second_repository.capture_session()
        await auth_repository.create_user(email=email, password_hash="hash")
        found_user = await second_repository.find_user_by_email(email)

    assert found_user is not None
    assert second_repository.sessions == [first_session, first_session]


@pytest.mark.asyncio
async def test_session_scope_outside_transaction_is_not_transaction_session(
    unit_of_work: UnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = f"{uuid4()}@example.com"

    async with unit_of_work.session_scope() as session:
        session.add(User(email=email, password_hash="hash"))
        assert unit_of_work.is_transaction_session(session) is False

    assert await _find_user(session_factory, email) is None


@pytest.mark.asyncio
async def test_repository_persists_outside_transaction(
    unit_of_work: UnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = f"{uuid4()}@example.com"
    repository = AuthRepository(unit_of_work=unit_of_work)

    created_user = await repository.create_user(email=email, password_hash="hash")

    persisted_user = await _find_user(session_factory, email)
    assert persisted_user is not None
    assert persisted_user.id == created_user.id


@pytest.mark.asyncio
async def test_repository_converts_create_user_integrity_error_outside_transaction(
    unit_of_work: UnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = f"{uuid4()}@example.com"
    repository = AuthRepository(unit_of_work=unit_of_work)

    await repository.create_user(email=email, password_hash="hash")
    with pytest.raises(EmailAlreadyRegisteredError):
        await repository.create_user(email=email, password_hash="hash")

    async with session_factory() as session:
        result = await session.exec(select(User).where(User.email == email))
        assert len(result.all()) == 1


@pytest.mark.asyncio
async def test_distinct_unit_of_work_instances_do_not_share_context_session(
    session_factory: async_sessionmaker[AsyncSession], ) -> None:
    first_unit_of_work = UnitOfWork(session_factory=session_factory)
    second_unit_of_work = UnitOfWork(session_factory=session_factory)

    async with first_unit_of_work.transaction():
        async with first_unit_of_work.session_scope() as first_session:
            with pytest.raises(RuntimeError, match="different UnitOfWork transaction"):
                async with second_unit_of_work.session_scope():
                    pass

            with pytest.raises(RuntimeError, match="different UnitOfWork transaction"):
                async with second_unit_of_work.transaction():
                    pass

            async with first_unit_of_work.session_scope() as restored_session:
                assert restored_session is first_session


@pytest.mark.asyncio
async def test_distinct_unit_of_work_instances_can_run_sequential_transactions(
    session_factory: async_sessionmaker[AsyncSession], ) -> None:
    first_unit_of_work = UnitOfWork(session_factory=session_factory)
    second_unit_of_work = UnitOfWork(session_factory=session_factory)

    async with first_unit_of_work.transaction():
        async with first_unit_of_work.session_scope() as first_session:
            assert first_unit_of_work.is_transaction_session(first_session)

    async with second_unit_of_work.transaction():
        async with second_unit_of_work.session_scope() as second_session:
            assert second_unit_of_work.is_transaction_session(second_session)
            assert second_session is not first_session


@pytest.mark.asyncio
async def test_nested_transaction_reuses_outer_session(unit_of_work: UnitOfWork, ) -> None:
    async with unit_of_work.transaction():
        async with unit_of_work.session_scope() as outer_session:
            pass
        async with unit_of_work.transaction():
            async with unit_of_work.session_scope() as nested_session:
                assert nested_session is outer_session


@pytest.mark.asyncio
async def test_transaction_rolls_back_and_resets_contextvar(
    unit_of_work: UnitOfWork,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    email = f"{uuid4()}@example.com"

    with pytest.raises(RuntimeError):
        async with unit_of_work.transaction():
            async with unit_of_work.session_scope() as session:
                session.add(User(email=email, password_hash="hash"))
                await session.flush()
            raise RuntimeError("force rollback")

    assert await _find_user(session_factory, email) is None
    async with unit_of_work.session_scope() as session:
        assert unit_of_work.is_transaction_session(session) is False


@pytest.mark.asyncio
async def test_new_transaction_does_not_reuse_previous_session(unit_of_work: UnitOfWork, ) -> None:
    async with unit_of_work.transaction():
        async with unit_of_work.session_scope() as first_session:
            pass

    async with unit_of_work.transaction():
        async with unit_of_work.session_scope() as second_session:
            pass

    assert second_session is not first_session
