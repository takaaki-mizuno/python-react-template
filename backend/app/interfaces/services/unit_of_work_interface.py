from abc import ABCMeta, abstractmethod
from contextlib import AbstractAsyncContextManager

from sqlmodel.ext.asyncio.session import AsyncSession


class UnitOfWorkInterface(metaclass=ABCMeta):

    @abstractmethod
    def transaction(self) -> AbstractAsyncContextManager[None]:
        raise NotImplementedError

    @abstractmethod
    def session_scope(self) -> AbstractAsyncContextManager[AsyncSession]:
        raise NotImplementedError

    @abstractmethod
    def is_transaction_session(self, session: AsyncSession) -> bool:
        raise NotImplementedError
