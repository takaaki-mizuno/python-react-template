from abc import ABCMeta, abstractmethod
from datetime import datetime
from uuid import UUID

from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_session import AuthSession
from app.models.user import User


class AuthRepositoryInterface(metaclass=ABCMeta):

    @abstractmethod
    async def create_user(self, email: str, password_hash: str | None) -> User:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_email(self, normalized_email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_id(self, user_id: UUID) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def create_session(
        self,
        user_id: UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at: datetime,
        last_seen_at: datetime,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def find_active_session_by_token_hash(
            self, token_hash: str) -> AuthSession | None:
        raise NotImplementedError

    @abstractmethod
    async def find_session_by_token_hash(
            self, token_hash: str) -> AuthSession | None:
        raise NotImplementedError

    @abstractmethod
    async def update_session_csrf_token_hash(
        self,
        session_id: UUID,
        csrf_token_hash: str,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def revoke_session(self, session_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def touch_session(
        self,
        session_id: UUID,
        last_seen_at: datetime,
        expires_at: datetime,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def record_user_login(self, user_id: UUID,
                                login_at: datetime) -> User:
        raise NotImplementedError

    @abstractmethod
    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        raise NotImplementedError
