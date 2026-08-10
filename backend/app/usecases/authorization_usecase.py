from logging import Logger
from uuid import UUID

from injector import inject

from app.config.authorization import (permission_catalog_by_code, resolve_user_authorization,
                                      role_catalog_by_code, roles_with_permissions)
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.authorization_usecase_interface import AuthorizationUsecaseInterface
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_event_type import AuthEventType
from app.models.authorization import (PermissionDefinition, RoleWithPermissions, UserAuthorization,
                                      UserRoleReplacementResult)
from app.models.authorization_errors import AuthorizationUserNotFoundError, RoleNotFoundError


class AuthorizationUsecase(AuthorizationUsecaseInterface):

    @inject
    def __init__(
        self,
        auth_repository: AuthRepositoryInterface,
        authorization_repository: AuthorizationRepositoryInterface,
        unit_of_work: UnitOfWorkInterface,
        logger: Logger,
    ) -> None:
        self._auth_repository = auth_repository
        self._authorization_repository = authorization_repository
        self._unit_of_work = unit_of_work
        self._logger = logger

    async def list_roles(self) -> list[RoleWithPermissions]:
        return roles_with_permissions()

    async def list_permissions(self) -> list[PermissionDefinition]:
        return [permission for _, permission in sorted(permission_catalog_by_code().items())]

    async def get_user_authorization(self, user_id: UUID) -> UserAuthorization:
        user = await self._auth_repository.find_user_by_id_for_authentication(user_id)
        if user is None or user.deleted_at is not None:
            raise AuthorizationUserNotFoundError(user_id)
        role_codes = await self._authorization_repository.get_user_role_codes(user_id)
        return resolve_user_authorization(user_id, role_codes, self._logger)

    async def replace_user_roles(
        self,
        actor_context: AuthenticatedSessionContext,
        target_user_id: UUID,
        role_codes: tuple[str, ...],
        ip_address: str | None,
        user_agent: str | None,
    ) -> UserRoleReplacementResult:
        normalized_role_codes = tuple(dict.fromkeys(role_codes))
        missing_role_codes = frozenset(normalized_role_codes) - frozenset(role_catalog_by_code())
        if missing_role_codes:
            raise RoleNotFoundError(missing_role_codes)
        async with self._unit_of_work.transaction():
            user = await self._auth_repository.find_user_by_id_for_authentication(target_user_id)
            if user is None or user.deleted_at is not None:
                raise AuthorizationUserNotFoundError(target_user_id)
            result = await self._authorization_repository.replace_user_roles(
                target_user_id,
                normalized_role_codes,
                actor_context.user.id,
            )
            for role_code in result.granted_role_codes:
                await self._record_role_audit(
                    actor_context,
                    target_user_id,
                    AuthEventType.ROLE_GRANTED,
                    role_code,
                    result.current_role_codes,
                    ip_address,
                    user_agent,
                )
            for role_code in result.revoked_role_codes:
                await self._record_role_audit(
                    actor_context,
                    target_user_id,
                    AuthEventType.ROLE_REVOKED,
                    role_code,
                    result.current_role_codes,
                    ip_address,
                    user_agent,
                )
            return result

    async def _record_role_audit(
        self,
        actor_context: AuthenticatedSessionContext,
        target_user_id: UUID,
        event_type: AuthEventType,
        role_code: str,
        resulting_roles: tuple[str, ...],
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        await self._auth_repository.create_audit_log(
            AuthAuditLog(
                user_id=actor_context.user.id,
                session_id=actor_context.session.id,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
                detail_json={
                    "actorUserId": str(actor_context.user.id),
                    "targetUserId": str(target_user_id),
                    "roleCode": role_code,
                    "resultingRoles": list(resulting_roles),
                },
            ))
