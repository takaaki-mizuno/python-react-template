from uuid import UUID

from injector import inject
from sqlalchemy.exc import IntegrityError
from sqlalchemy.sql.elements import ColumnElement
from sqlmodel import col, exists, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.admin_user_repository_interface import AdminUserRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.admin_pagination import AdminOffsetPageRequest, AdminOffsetPageResult
from app.models.admin_query import escape_like_search
from app.models.admin_user import AdminUserListQuery, AdminUserRecord, AdminUserUpdateChanges
from app.models.auth_errors import EmailAlreadyRegisteredError, UserNotFoundError
from app.models.authorization import UserRole
from app.models.user import User


class AdminUserRepository(AdminUserRepositoryInterface):

    @inject
    def __init__(self, unit_of_work: UnitOfWorkInterface) -> None:
        self._unit_of_work = unit_of_work

    async def _persist(self, session: AsyncSession) -> None:
        if self._unit_of_work.is_transaction_session(session):
            await session.flush()
        else:
            await session.commit()

    async def list_users(
        self,
        query: AdminUserListQuery,
        page: AdminOffsetPageRequest,
    ) -> AdminOffsetPageResult[AdminUserRecord]:
        async with self._unit_of_work.session_scope() as session:
            base_filters = self._filters(query)
            list_statement = (select(User).where(*base_filters).order_by(
                col(User.created_at).desc(),
                col(User.id).desc(),
            ).offset(page.offset).limit(page.limit))
            users = list((await session.exec(list_statement)).all())

            count_statement = select(func.count(col(User.id))).where(*base_filters)
            total = int((await session.exec(count_statement)).one())

            roles_by_user_id = await self._role_codes_for_users(session,
                                                                tuple(user.id for user in users))
            return AdminOffsetPageResult(
                items=[
                    AdminUserRecord(user=user, roles=roles_by_user_id.get(user.id, ()))
                    for user in users
                ],
                total=total,
                offset=page.offset,
                limit=page.limit,
            )

    async def get_user(self, user_id: UUID) -> User | None:
        async with self._unit_of_work.session_scope() as session:
            statement = select(User).where(
                col(User.id) == user_id,
                col(User.deleted_at).is_(None),
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def create_user(self, email: str, password_hash: str, is_active: bool) -> User:
        async with self._unit_of_work.session_scope() as session:
            user = User(email=email, password_hash=password_hash, is_active=is_active)
            session.add(user)
            try:
                await self._persist(session)
            except IntegrityError as error:
                if not self._unit_of_work.is_transaction_session(session):
                    await session.rollback()
                raise EmailAlreadyRegisteredError from error
            await session.refresh(user)
            return user

    async def update_user(
        self,
        user_id: UUID,
        changes: AdminUserUpdateChanges,
        password_hash: str | None,
    ) -> User:
        async with self._unit_of_work.session_scope() as session:
            statement = select(User).where(
                col(User.id) == user_id,
                col(User.deleted_at).is_(None),
            )
            result = await session.exec(statement)
            user = result.one_or_none()
            if user is None:
                raise UserNotFoundError(user_id)

            if "email" in changes.fields_set:
                if changes.email is None:
                    raise ValueError("email cannot be None when included in fields_set")
                user.email = changes.email
            if "password" in changes.fields_set:
                if password_hash is None:
                    raise ValueError("password_hash cannot be None when password is included")
                user.password_hash = password_hash
            if "is_active" in changes.fields_set:
                if changes.is_active is None:
                    raise ValueError("is_active cannot be None when included in fields_set")
                user.is_active = changes.is_active

            session.add(user)
            try:
                await self._persist(session)
            except IntegrityError as error:
                if not self._unit_of_work.is_transaction_session(session):
                    await session.rollback()
                raise EmailAlreadyRegisteredError from error
            await session.refresh(user)
            return user

    def _filters(self, query: AdminUserListQuery) -> list[ColumnElement[bool]]:
        filters: list[ColumnElement[bool]] = [col(User.deleted_at).is_(None)]
        if query.search is not None:
            pattern = escape_like_search(query.search.lower())
            filters.append(func.lower(col(User.email)).like(f"%{pattern}%", escape="\\"))
        if query.is_active is not None:
            filters.append(col(User.is_active).is_(query.is_active))
        if query.role is not None:
            filters.append(exists().where(
                col(UserRole.user_id) == col(User.id),
                col(UserRole.role_code) == query.role,
            ))
        return filters

    async def _role_codes_for_users(
        self,
        session: AsyncSession,
        user_ids: tuple[UUID, ...],
    ) -> dict[UUID, tuple[str, ...]]:
        if not user_ids:
            return {}
        result = await session.exec(
            select(UserRole.user_id,
                   UserRole.role_code).where(col(UserRole.user_id).in_(user_ids)).order_by(
                       col(UserRole.user_id),
                       col(UserRole.role_code),
                   ))
        roles_by_user_id: dict[UUID, list[str]] = {}
        for user_id, role_code in result.all():
            roles_by_user_id.setdefault(user_id, []).append(role_code)
        return {user_id: tuple(role_codes) for user_id, role_codes in roles_by_user_id.items()}
