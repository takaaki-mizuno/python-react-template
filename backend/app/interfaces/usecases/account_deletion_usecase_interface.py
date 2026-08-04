from abc import ABCMeta, abstractmethod

from app.models.auth_context import AuthenticatedSessionContext


class AccountDeletionUsecaseInterface(metaclass=ABCMeta):

    @abstractmethod
    async def delete_account(
        self,
        auth_context: AuthenticatedSessionContext,
        confirm_email: str,
        password: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        raise NotImplementedError
