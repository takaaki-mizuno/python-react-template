from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.admin_pagination import AdminOffsetPageRequest, AdminOffsetPageResult
from app.models.admin_user import AdminUserListQuery, AdminUserRecord, AdminUserUpdateChanges
from app.models.user import User


class AdminUserRepositoryInterface(metaclass=ABCMeta):

    @abstractmethod
    async def list_users(
        self,
        query: AdminUserListQuery,
        page: AdminOffsetPageRequest,
    ) -> AdminOffsetPageResult[AdminUserRecord]:
        raise NotImplementedError

    @abstractmethod
    async def get_user(self, user_id: UUID) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def create_user(self, email: str, password_hash: str, is_active: bool) -> User:
        raise NotImplementedError

    @abstractmethod
    async def update_user(
        self,
        user_id: UUID,
        changes: AdminUserUpdateChanges,
        password_hash: str | None,
    ) -> User:
        raise NotImplementedError
