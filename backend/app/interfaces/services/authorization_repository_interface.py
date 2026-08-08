from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.authorization import (PermissionDefinition, RoleDefinition, RoleWithPermissions,
                                      UserAuthorization, UserRoleReplacementResult)


class AuthorizationRepositoryInterface(metaclass=ABCMeta):

    @abstractmethod
    async def upsert_permission_definition(self, definition: PermissionDefinition) -> None:
        raise NotImplementedError

    @abstractmethod
    async def upsert_role_definition(self, definition: RoleDefinition) -> None:
        raise NotImplementedError

    @abstractmethod
    async def replace_role_permissions(
        self,
        role_code: str,
        permission_codes: tuple[str, ...],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def list_roles_with_permissions(self) -> list[RoleWithPermissions]:
        raise NotImplementedError

    @abstractmethod
    async def list_permissions(self) -> list[PermissionDefinition]:
        raise NotImplementedError

    @abstractmethod
    async def get_user_authorization(self, user_id: UUID) -> UserAuthorization | None:
        raise NotImplementedError

    @abstractmethod
    async def get_existing_user_authorization(self, user_id: UUID) -> UserAuthorization:
        raise NotImplementedError

    @abstractmethod
    async def replace_user_roles(
        self,
        user_id: UUID,
        role_codes: tuple[str, ...],
        assigned_by_user_id: UUID | None,
    ) -> UserRoleReplacementResult:
        raise NotImplementedError

    @abstractmethod
    async def delete_roles_for_user(self, user_id: UUID) -> int:
        raise NotImplementedError
