from uuid import UUID

from injector import inject
from sqlalchemy import delete, or_
from sqlalchemy.dialects.postgresql import insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.libraries.clock import utcnow
from app.models.authorization import (Permission, PermissionDefinition, Role, RoleDefinition,
                                      RolePermission, RoleWithPermissions, UserAuthorization,
                                      UserRole, UserRoleReplacementResult)
from app.models.authorization_errors import PermissionNotFoundError, RoleNotFoundError
from app.models.user import User


class AuthorizationRepository(AuthorizationRepositoryInterface):

    @inject
    def __init__(self, unit_of_work: UnitOfWorkInterface) -> None:
        self._unit_of_work = unit_of_work

    async def _persist(self, session: AsyncSession) -> None:
        if self._unit_of_work.is_transaction_session(session):
            await session.flush()
        else:
            await session.commit()

    async def upsert_permission_definition(self, definition: PermissionDefinition) -> None:
        now = utcnow()
        async with self._unit_of_work.session_scope() as session:
            insert_statement = insert(Permission).values(
                code=definition.code,
                display_name=definition.display_name,
                description=definition.description,
                created_at=now,
                updated_at=now,
            )
            statement = insert_statement.on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "display_name": insert_statement.excluded.display_name,
                    "description": insert_statement.excluded.description,
                    "updated_at": now,
                },
                where=or_(
                    col(Permission.display_name).is_distinct_from(
                        insert_statement.excluded.display_name),
                    col(Permission.description).is_distinct_from(
                        insert_statement.excluded.description),
                ),
            )
            await session.exec(statement)
            await self._persist(session)

    async def upsert_role_definition(self, definition: RoleDefinition) -> None:
        now = utcnow()
        async with self._unit_of_work.session_scope() as session:
            insert_statement = insert(Role).values(
                code=definition.code,
                display_name=definition.display_name,
                description=definition.description,
                created_at=now,
                updated_at=now,
            )
            statement = insert_statement.on_conflict_do_update(
                index_elements=["code"],
                set_={
                    "display_name": insert_statement.excluded.display_name,
                    "description": insert_statement.excluded.description,
                    "updated_at": now,
                },
                where=or_(
                    col(Role.display_name).is_distinct_from(insert_statement.excluded.display_name),
                    col(Role.description).is_distinct_from(insert_statement.excluded.description),
                ),
            )
            await session.exec(statement)
            await self._persist(session)

    async def replace_role_permissions(
        self,
        role_code: str,
        permission_codes: tuple[str, ...],
    ) -> None:
        normalized_codes = tuple(dict.fromkeys(permission_codes))
        async with self._unit_of_work.session_scope() as session:
            role = await self._get_role(session, role_code)
            if role is None:
                raise RoleNotFoundError(frozenset({role_code}))
            permissions = await self._permissions_by_code(session, normalized_codes)
            missing_permission_codes = frozenset(normalized_codes) - frozenset(permissions)
            if missing_permission_codes:
                raise PermissionNotFoundError(missing_permission_codes)
            await session.exec(delete(RolePermission).where(col(RolePermission.role_id) == role.id))
            for permission in permissions.values():
                session.add(RolePermission(role_id=role.id, permission_id=permission.id))
            await self._persist(session)

    async def list_roles_with_permissions(self) -> list[RoleWithPermissions]:
        async with self._unit_of_work.session_scope() as session:
            roles = list((await session.exec(select(Role).order_by(Role.code))).all())
            results: list[RoleWithPermissions] = []
            for role in roles:
                permission_rows = await session.exec(
                    select(Permission.code).join(
                        RolePermission,
                        col(RolePermission.permission_id) == col(Permission.id),
                    ).where(col(RolePermission.role_id) == role.id).order_by(Permission.code))
                results.append(
                    RoleWithPermissions(
                        code=role.code,
                        display_name=role.display_name,
                        description=role.description,
                        permissions=tuple(permission_rows.all()),
                    ))
            return results

    async def list_permissions(self) -> list[PermissionDefinition]:
        async with self._unit_of_work.session_scope() as session:
            permissions = list((await
                                session.exec(select(Permission).order_by(Permission.code))).all())
            return [
                PermissionDefinition(
                    code=permission.code,
                    display_name=permission.display_name,
                    description=permission.description,
                ) for permission in permissions
            ]

    async def get_user_authorization(self, user_id: UUID) -> UserAuthorization | None:
        async with self._unit_of_work.session_scope() as session:
            user = await session.get(User, user_id)
            if user is None or user.deleted_at is not None:
                return None
            return await self._get_authorization_for_existing_user(session, user_id)

    async def get_existing_user_authorization(self, user_id: UUID) -> UserAuthorization:
        async with self._unit_of_work.session_scope() as session:
            return await self._get_authorization_for_existing_user(session, user_id)

    async def replace_user_roles(
        self,
        user_id: UUID,
        role_codes: tuple[str, ...],
        assigned_by_user_id: UUID | None,
    ) -> UserRoleReplacementResult:
        target_codes = tuple(dict.fromkeys(role_codes))
        async with self._unit_of_work.session_scope() as session:
            roles_by_code = await self._roles_by_code(session, target_codes)
            missing_role_codes = frozenset(target_codes) - frozenset(roles_by_code)
            if missing_role_codes:
                raise RoleNotFoundError(missing_role_codes)

            existing_role_codes = await self._role_codes_for_user(session, user_id)
            existing_set = frozenset(existing_role_codes)
            target_set = frozenset(target_codes)
            revoked = tuple(sorted(existing_set - target_set))
            granted = tuple(sorted(target_set - existing_set))

            if revoked:
                persisted_roles = await self._roles_by_code(session, revoked)
                revoked_ids = [role.id for role in persisted_roles.values()]
                await session.exec(
                    delete(UserRole).where(
                        col(UserRole.user_id) == user_id,
                        col(UserRole.role_id).in_(revoked_ids)))
            for code in granted:
                session.add(
                    UserRole(
                        user_id=user_id,
                        role_id=roles_by_code[code].id,
                        assigned_at=utcnow(),
                        assigned_by_user_id=assigned_by_user_id,
                    ))

            current_permissions = await self._permission_codes_for_roles(session, target_codes)
            await self._persist(session)
            return UserRoleReplacementResult(
                user_id=user_id,
                granted_role_codes=granted,
                revoked_role_codes=revoked,
                current_role_codes=tuple(sorted(target_set)),
                current_permission_codes=tuple(sorted(current_permissions)),
            )

    async def delete_roles_for_user(self, user_id: UUID) -> int:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(delete(UserRole).where(col(UserRole.user_id) == user_id))
            await self._persist(session)
            return int(result.rowcount or 0)

    async def _get_authorization_for_existing_user(
        self,
        session: AsyncSession,
        user_id: UUID,
    ) -> UserAuthorization:
        roles = await self._role_codes_for_user(session, user_id)
        permissions = await self._permission_codes_for_roles(session, roles)
        return UserAuthorization(
            user_id=user_id,
            roles=frozenset(roles),
            permissions=frozenset(permissions),
        )

    async def _get_role(self, session: AsyncSession, role_code: str) -> Role | None:
        result = await session.exec(select(Role).where(Role.code == role_code))
        return result.one_or_none()

    async def _roles_by_code(
        self,
        session: AsyncSession,
        role_codes: tuple[str, ...],
    ) -> dict[str, Role]:
        if not role_codes:
            return {}
        result = await session.exec(select(Role).where(col(Role.code).in_(role_codes)))
        return {role.code: role for role in result.all()}

    async def _permissions_by_code(
        self,
        session: AsyncSession,
        permission_codes: tuple[str, ...],
    ) -> dict[str, Permission]:
        if not permission_codes:
            return {}
        result = await session.exec(
            select(Permission).where(col(Permission.code).in_(permission_codes)))
        return {permission.code: permission for permission in result.all()}

    async def _role_codes_for_user(self, session: AsyncSession, user_id: UUID) -> tuple[str, ...]:
        result = await session.exec(
            select(Role.code).join(UserRole,
                                   col(UserRole.role_id) == col(Role.id)).where(
                                       col(UserRole.user_id) == user_id).order_by(Role.code))
        return tuple(result.all())

    async def _permission_codes_for_roles(
        self,
        session: AsyncSession,
        role_codes: tuple[str, ...],
    ) -> tuple[str, ...]:
        if not role_codes:
            return ()
        result = await session.exec(
            select(Permission.code).join(
                RolePermission,
                col(RolePermission.permission_id) == col(Permission.id),
            ).join(Role,
                   col(Role.id) == col(RolePermission.role_id)).where(
                       col(Role.code).in_(role_codes)).distinct().order_by(Permission.code))
        return tuple(result.all())
