from logging import Logger
from uuid import UUID

from injector import inject

from app.config.authorization import resolve_user_authorization, role_catalog_by_code
from app.interfaces.services.admin_user_repository_interface import AdminUserRepositoryInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.sample_item_repository_interface import SampleItemRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.admin_user_usecase_interface import AdminUserUsecaseInterface
from app.libraries.clock import utcnow
from app.libraries.password_hasher import PasswordHashExecutor, validate_password_policy
from app.models.admin_pagination import AdminOffsetPageRequest, AdminOffsetPageResult
from app.models.admin_user import (AdminUserDetail, AdminUserListQuery, AdminUserRecord,
                                   AdminUserUpdateChanges)
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_errors import UserNotFoundError, WeakPasswordError
from app.models.auth_event_type import AuthEventType
from app.models.authorization_errors import RoleNotFoundError
from app.models.user import User
from app.usecases.authorization_audit import role_audit_detail


class AdminUserUsecase(AdminUserUsecaseInterface):

    @inject
    def __init__(
        self,
        admin_user_repository: AdminUserRepositoryInterface,
        auth_repository: AuthRepositoryInterface,
        authorization_repository: AuthorizationRepositoryInterface,
        sample_item_repository: SampleItemRepositoryInterface,
        unit_of_work: UnitOfWorkInterface,
        password_hash_executor: PasswordHashExecutor,
        logger: Logger,
    ) -> None:
        self._admin_user_repository = admin_user_repository
        self._auth_repository = auth_repository
        self._authorization_repository = authorization_repository
        self._sample_item_repository = sample_item_repository
        self._unit_of_work = unit_of_work
        self._password_hash_executor = password_hash_executor
        self._logger = logger

    async def list_users(
        self,
        query: AdminUserListQuery,
        offset: int,
        limit: int,
    ) -> AdminOffsetPageResult[AdminUserRecord]:
        if query.role is not None:
            self._validate_roles((query.role, ))
        result = await self._admin_user_repository.list_users(
            query,
            AdminOffsetPageRequest(offset=offset, limit=limit),
        )
        return AdminOffsetPageResult(
            items=[
                AdminUserRecord(
                    user=record.user,
                    roles=self._known_role_codes(record.user.id, record.roles),
                ) for record in result.items
            ],
            total=result.total,
            offset=result.offset,
            limit=result.limit,
        )

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
        normalized_email = email.strip().lower()
        normalized_roles = self._normalize_and_validate_roles(roles)
        password_hash = await self._hash_valid_password(password)

        async with self._unit_of_work.transaction():
            user = await self._admin_user_repository.create_user(
                normalized_email,
                password_hash,
                is_active,
            )
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=actor_context.user.id,
                    session_id=actor_context.session.id,
                    event_type=AuthEventType.USER_CREATED_BY_ADMIN,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    detail_json={
                        "actor_user_id": str(actor_context.user.id),
                        "target_user_id": str(user.id),
                        "changed_fields": ["email", "password", "is_active", "roles"],
                    },
                ))
            await self._replace_roles_with_audit(
                actor_context,
                user.id,
                normalized_roles,
                ip_address,
                user_agent,
            )
            return await self._detail_for_user(user)

    async def get_user(self, user_id: UUID) -> AdminUserDetail:
        user = await self._admin_user_repository.get_user(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        return await self._detail_for_user(user)

    async def update_user(
        self,
        actor_context: AuthenticatedSessionContext,
        user_id: UUID,
        changes: AdminUserUpdateChanges,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AdminUserDetail:
        if not changes.fields_set:
            return await self.get_user(user_id)
        normalized_roles = None
        if "roles" in changes.fields_set:
            if changes.roles is None:
                raise ValueError("roles cannot be None when included in fields_set")
            normalized_roles = self._normalize_and_validate_roles(changes.roles)

        password_hash = None
        if "password" in changes.fields_set:
            if changes.password is None:
                raise ValueError("password cannot be None when included in fields_set")
            password_hash = await self._hash_valid_password(changes.password)

        normalized_changes = AdminUserUpdateChanges(
            email=changes.email.strip().lower() if changes.email is not None else None,
            password=changes.password,
            is_active=changes.is_active,
            roles=normalized_roles,
            fields_set=changes.fields_set,
        )
        revoked_at = utcnow()
        async with self._unit_of_work.transaction():
            user = await self._admin_user_repository.update_user(
                user_id,
                normalized_changes,
                password_hash,
            )
            if normalized_roles is not None:
                await self._replace_roles_with_audit(
                    actor_context,
                    user.id,
                    normalized_roles,
                    ip_address,
                    user_agent,
                )
            if "password" in changes.fields_set or ("is_active" in changes.fields_set
                                                    and changes.is_active is False):
                await self._auth_repository.revoke_sessions_for_user(user.id, revoked_at)
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=actor_context.user.id,
                    session_id=actor_context.session.id,
                    event_type=AuthEventType.USER_UPDATED_BY_ADMIN,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    detail_json={
                        "actor_user_id": str(actor_context.user.id),
                        "target_user_id": str(user.id),
                        "changed_fields": self._audit_fields(changes.fields_set),
                    },
                ))
            return await self._detail_for_user(user)

    async def delete_user(
        self,
        actor_context: AuthenticatedSessionContext,
        user_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        user = await self._admin_user_repository.get_user(user_id)
        if user is None:
            raise UserNotFoundError(user_id)
        deleted_at = utcnow()
        async with self._unit_of_work.transaction():
            # Keep this list aligned with AccountDeletionUsecase when adding user-owned resources.
            await self._sample_item_repository.delete_all_for_owner(user.id)
            await self._authorization_repository.delete_roles_for_user(user.id)
            await self._auth_repository.delete_auth_identities_for_user(user.id)
            await self._auth_repository.mark_user_deleted(
                user.id,
                deleted_at,
                session_id=actor_context.session.id,
                ip_address=ip_address,
            )
            await self._auth_repository.revoke_sessions_for_user(user.id, deleted_at)
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=actor_context.user.id,
                    session_id=actor_context.session.id,
                    event_type=AuthEventType.USER_DELETED_BY_ADMIN,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    detail_json={
                        "actor_user_id": str(actor_context.user.id),
                        "target_user_id": str(user.id),
                    },
                ))

    async def _detail_for_user(self, user: User) -> AdminUserDetail:
        role_codes = await self._authorization_repository.get_user_role_codes(user.id)
        authorization = resolve_user_authorization(user.id, role_codes, self._logger)
        return AdminUserDetail(
            user=user,
            roles=tuple(sorted(authorization.roles)),
            permissions=tuple(sorted(authorization.permissions)),
        )

    def _known_role_codes(self, user_id: UUID, role_codes: tuple[str, ...]) -> tuple[str, ...]:
        authorization = resolve_user_authorization(user_id, role_codes, self._logger)
        return tuple(sorted(authorization.roles))

    async def _hash_valid_password(self, password: str) -> str:
        is_valid_password, error_message = validate_password_policy(password)
        if not is_valid_password:
            raise WeakPasswordError(error_message or "Invalid password")
        return await self._password_hash_executor.hash(password)

    async def _replace_roles_with_audit(
        self,
        actor_context: AuthenticatedSessionContext,
        target_user_id: UUID,
        role_codes: tuple[str, ...],
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        result = await self._authorization_repository.replace_user_roles(
            target_user_id,
            role_codes,
            actor_context.user.id,
        )
        for role_code in result.granted_role_codes:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=actor_context.user.id,
                    session_id=actor_context.session.id,
                    event_type=AuthEventType.ROLE_GRANTED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    detail_json=role_audit_detail(
                        source=None,
                        actor_user_id=actor_context.user.id,
                        target_user_id=target_user_id,
                        role_code=role_code,
                        resulting_roles=result.current_role_codes,
                    ),
                ))
        for role_code in result.revoked_role_codes:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=actor_context.user.id,
                    session_id=actor_context.session.id,
                    event_type=AuthEventType.ROLE_REVOKED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                    detail_json=role_audit_detail(
                        source=None,
                        actor_user_id=actor_context.user.id,
                        target_user_id=target_user_id,
                        role_code=role_code,
                        resulting_roles=result.current_role_codes,
                    ),
                ))

    def _normalize_and_validate_roles(self, role_codes: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(role_codes))
        self._validate_roles(normalized)
        return normalized

    def _validate_roles(self, role_codes: tuple[str, ...]) -> None:
        missing_role_codes = frozenset(role_codes) - frozenset(role_catalog_by_code())
        if missing_role_codes:
            raise RoleNotFoundError(missing_role_codes)

    def _audit_fields(self, fields_set: frozenset[str]) -> list[str]:
        field_names = {
            "email": "email",
            "password": "password",
            "is_active": "is_active",
            "roles": "roles",
        }
        return [field_names[field] for field in field_names if field in fields_set]
