from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.services.auth_repository import AuthRepository


class FailingFlushSession:

    def __init__(self) -> None:
        self.rollback_called = False

    def add(self, _instance: object) -> None:
        pass

    async def flush(self) -> None:
        raise IntegrityError("insert users", {}, Exception("duplicate email"))

    async def commit(self) -> None:
        raise AssertionError("commit must not be used inside a transaction")

    async def rollback(self) -> None:
        self.rollback_called = True

    async def refresh(self, _instance: object) -> None:
        raise AssertionError("refresh must not run after IntegrityError")


class TransactionSessionUnitOfWork(UnitOfWorkInterface):

    def __init__(self) -> None:
        self.session = FailingFlushSession()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        yield

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        yield self.session  # type: ignore[misc]

    def is_transaction_session(self, session: AsyncSession) -> bool:
        return session is self.session


@pytest.mark.asyncio
async def test_create_user_does_not_rollback_integrity_error_inside_transaction(
) -> None:
    unit_of_work = TransactionSessionUnitOfWork()
    repository = AuthRepository(unit_of_work=unit_of_work)

    with pytest.raises(EmailAlreadyRegisteredError):
        await repository.create_user(email="user@example.com",
                                     password_hash="hash")

    assert unit_of_work.session.rollback_called is False
