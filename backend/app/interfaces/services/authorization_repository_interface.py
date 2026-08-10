from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.authorization import UnknownRoleAssignment, UserRoleReplacementResult


class AuthorizationRepositoryInterface(metaclass=ABCMeta):

    @abstractmethod
    async def get_user_role_codes(self, user_id: UUID) -> tuple[str, ...]:
        raise NotImplementedError

    @abstractmethod
    async def list_unknown_role_assignments(
        self,
        known_role_codes: frozenset[str],
    ) -> tuple[UnknownRoleAssignment, ...]:
        raise NotImplementedError

    @abstractmethod
    async def delete_unknown_role_assignments(self, known_role_codes: frozenset[str]) -> int:
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
