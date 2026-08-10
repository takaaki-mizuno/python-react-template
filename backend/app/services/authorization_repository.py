from uuid import UUID

from injector import inject
from sqlalchemy import delete
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.libraries.clock import utcnow
from app.models.authorization import UnknownRoleAssignment, UserRole, UserRoleReplacementResult


class AuthorizationRepository(AuthorizationRepositoryInterface):

    @inject
    def __init__(self, unit_of_work: UnitOfWorkInterface) -> None:
        self._unit_of_work = unit_of_work

    async def _persist(self, session: AsyncSession) -> None:
        if self._unit_of_work.is_transaction_session(session):
            await session.flush()
        else:
            await session.commit()

    async def get_user_role_codes(self, user_id: UUID) -> tuple[str, ...]:
        async with self._unit_of_work.session_scope() as session:
            return await self._role_codes_for_user(session, user_id)

    async def list_unknown_role_assignments(
        self,
        known_role_codes: frozenset[str],
    ) -> tuple[UnknownRoleAssignment, ...]:
        async with self._unit_of_work.session_scope() as session:
            statement = select(UserRole.user_id, UserRole.role_code).order_by(
                UserRole.role_code,
                col(UserRole.user_id),
            )
            if known_role_codes:
                statement = statement.where(~col(UserRole.role_code).in_(known_role_codes))
            rows = (await session.exec(statement)).all()
            return tuple(UnknownRoleAssignment(user_id=row[0], role_code=row[1]) for row in rows)

    async def delete_unknown_role_assignments(self, known_role_codes: frozenset[str]) -> int:
        if not known_role_codes:
            raise ValueError("known_role_codes must not be empty")
        async with self._unit_of_work.session_scope() as session:
            statement = delete(UserRole)
            statement = statement.where(~col(UserRole.role_code).in_(known_role_codes))
            result = await session.exec(statement)
            await self._persist(session)
            return int(result.rowcount or 0)

    async def replace_user_roles(
        self,
        user_id: UUID,
        role_codes: tuple[str, ...],
        assigned_by_user_id: UUID | None,
    ) -> UserRoleReplacementResult:
        target_codes = tuple(dict.fromkeys(role_codes))
        async with self._unit_of_work.session_scope() as session:
            existing_role_codes = await self._role_codes_for_user(session, user_id)
            existing_set = frozenset(existing_role_codes)
            target_set = frozenset(target_codes)
            revoked = tuple(sorted(existing_set - target_set))
            granted = tuple(sorted(target_set - existing_set))

            if revoked:
                await session.exec(
                    delete(UserRole).where(
                        col(UserRole.user_id) == user_id,
                        col(UserRole.role_code).in_(revoked)))
            for code in granted:
                session.add(
                    UserRole(
                        user_id=user_id,
                        role_code=code,
                        assigned_at=utcnow(),
                        assigned_by_user_id=assigned_by_user_id,
                    ))

            await self._persist(session)
            return UserRoleReplacementResult(
                user_id=user_id,
                granted_role_codes=granted,
                revoked_role_codes=revoked,
                current_role_codes=tuple(sorted(target_set)),
            )

    async def delete_roles_for_user(self, user_id: UUID) -> int:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(delete(UserRole).where(col(UserRole.user_id) == user_id))
            await self._persist(session)
            return int(result.rowcount or 0)

    async def _role_codes_for_user(self, session: AsyncSession, user_id: UUID) -> tuple[str, ...]:
        result = await session.exec(
            select(UserRole.role_code).where(col(UserRole.user_id) == user_id).order_by(
                UserRole.role_code))
        return tuple(result.all())
