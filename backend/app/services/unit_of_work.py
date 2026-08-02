from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from contextvars import ContextVar

from injector import inject
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface

_transaction_session: ContextVar[tuple[object, AsyncSession]
                                 | None] = ContextVar(
                                     "unit_of_work_transaction_session",
                                     default=None,
                                 )


class UnitOfWork(UnitOfWorkInterface):
    """Request-scoped transaction coordinator.

    Nested ``transaction()`` calls join the current transaction; they do not
    create savepoints. Do not run parallel operations that share one transaction
    session with ``gather()`` or ``create_task()``.
    """

    @inject
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        self._session_factory = session_factory
        self._context_owner = object()

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        current = _transaction_session.get()
        if current is not None and current[0] is self._context_owner:
            yield
            return
        if current is not None:
            raise RuntimeError(
                "Cannot open a different UnitOfWork transaction "
                "inside an active transaction")

        async with self._session_factory() as session:
            token = _transaction_session.set((self._context_owner, session))
            try:
                async with session.begin():
                    yield
            finally:
                _transaction_session.reset(token)

    @asynccontextmanager
    async def session_scope(self) -> AsyncIterator[AsyncSession]:
        current = _transaction_session.get()
        if current is not None and current[0] is self._context_owner:
            yield current[1]
            return
        if current is not None:
            raise RuntimeError(
                "Cannot open a different UnitOfWork transaction "
                "inside an active transaction")

        async with self._session_factory() as session:
            yield session

    def is_transaction_session(self, session: AsyncSession) -> bool:
        current = _transaction_session.get()
        return (current is not None and current[0] is self._context_owner
                and session is current[1])
