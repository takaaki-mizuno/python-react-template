from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.auth_context import AuthenticatedSessionContext
from app.models.authorization import (PermissionDefinition, RoleWithPermissions, UserAuthorization,
                                      UserRoleReplacementResult)


class AuthorizationUsecaseInterface(metaclass=ABCMeta):

    @abstractmethod
    async def list_roles(self) -> list[RoleWithPermissions]:
        raise NotImplementedError

    @abstractmethod
    async def list_permissions(self) -> list[PermissionDefinition]:
        raise NotImplementedError

    @abstractmethod
    async def get_user_authorization(self, user_id: UUID) -> UserAuthorization:
        raise NotImplementedError

    @abstractmethod
    async def replace_user_roles(
        self,
        actor_context: AuthenticatedSessionContext,
        target_user_id: UUID,
        role_codes: tuple[str, ...],
        ip_address: str | None,
        user_agent: str | None,
    ) -> UserRoleReplacementResult:
        raise NotImplementedError
