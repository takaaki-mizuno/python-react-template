from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.admin_pagination import AdminOffsetPageResult
from app.models.admin_user import (AdminUserDetail, AdminUserListQuery, AdminUserRecord,
                                   AdminUserUpdateChanges)
from app.models.auth_context import AuthenticatedSessionContext


class AdminUserUsecaseInterface(metaclass=ABCMeta):

    @abstractmethod
    async def list_users(
        self,
        query: AdminUserListQuery,
        offset: int,
        limit: int,
    ) -> AdminOffsetPageResult[AdminUserRecord]:
        raise NotImplementedError

    @abstractmethod
    async def create_user(
        self,
        actor_context: AuthenticatedSessionContext,
        email: str,
        password: str,
        is_active: bool,
        roles: tuple[str, ...],
        ip_address: str | None,
        user_agent: str | None,
    ) -> AdminUserDetail:
        raise NotImplementedError

    @abstractmethod
    async def get_user(self, user_id: UUID) -> AdminUserDetail:
        raise NotImplementedError

    @abstractmethod
    async def update_user(
        self,
        actor_context: AuthenticatedSessionContext,
        user_id: UUID,
        changes: AdminUserUpdateChanges,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AdminUserDetail:
        raise NotImplementedError

    @abstractmethod
    async def delete_user(
        self,
        actor_context: AuthenticatedSessionContext,
        user_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        raise NotImplementedError
