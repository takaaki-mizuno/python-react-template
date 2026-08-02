from abc import ABCMeta, abstractmethod

from app.models.auth_context import (AuthenticatedSessionContext,
                                     IssuedAuthSession)
from app.models.auth_csrf import SessionCsrfStatus


class AuthUsecaseInterface(metaclass=ABCMeta):

    @abstractmethod
    async def issue_csrf_token(self, session_token: str | None = None) -> str:
        raise NotImplementedError

    @abstractmethod
    async def validate_session_csrf(
        self,
        session_token: str,
        csrf_token: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> SessionCsrfStatus:
        raise NotImplementedError

    @abstractmethod
    async def register(
        self,
        email: str,
        password: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedAuthSession:
        raise NotImplementedError

    @abstractmethod
    async def login(
        self,
        email: str,
        password: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedAuthSession:
        raise NotImplementedError

    @abstractmethod
    async def authenticate_session(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthenticatedSessionContext | None:
        raise NotImplementedError

    @abstractmethod
    async def logout(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        raise NotImplementedError
