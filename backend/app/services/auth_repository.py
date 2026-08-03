from datetime import UTC, datetime
from uuid import UUID

from injector import inject
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.auth_session import AuthSession
from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(UTC)


class AuthRepository(AuthRepositoryInterface):

    @inject
    def __init__(self, unit_of_work: UnitOfWorkInterface):
        self._unit_of_work = unit_of_work

    async def _persist(self, session: AsyncSession) -> None:
        if self._unit_of_work.is_transaction_session(session):
            await session.flush()
        else:
            await session.commit()

    async def create_user(self, email: str, password_hash: str | None) -> User:
        async with self._unit_of_work.session_scope() as session:
            user = User(email=email, password_hash=password_hash)
            session.add(user)
            try:
                await self._persist(session)
            except IntegrityError as error:
                if not self._unit_of_work.is_transaction_session(session):
                    await session.rollback()
                raise EmailAlreadyRegisteredError from error
            await session.refresh(user)
            return user

    async def find_user_by_email(self, normalized_email: str) -> User | None:
        async with self._unit_of_work.session_scope() as session:
            statement = select(User).where(func.lower(User.email) == normalized_email)
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_user_by_id(self, user_id: UUID) -> User | None:
        async with self._unit_of_work.session_scope() as session:
            statement = select(User).where(User.id == user_id)
            result = await session.exec(statement)
            return result.one_or_none()

    async def create_session(
        self,
        user_id: UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at: datetime,
        last_seen_at: datetime,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        async with self._unit_of_work.session_scope() as session:
            auth_session = AuthSession(
                user_id=user_id,
                session_token_hash=session_token_hash,
                csrf_token_hash=csrf_token_hash,
                created_at=created_at,
                last_seen_at=last_seen_at,
                expires_at=expires_at,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            session.add(auth_session)
            await self._persist(session)
            await session.refresh(auth_session)
            return auth_session

    async def find_active_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        now = utcnow()
        async with self._unit_of_work.session_scope() as session:
            statement = select(AuthSession).where(
                AuthSession.session_token_hash == token_hash,
                col(AuthSession.revoked_at).is_(None),
                AuthSession.expires_at > now,
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        async with self._unit_of_work.session_scope() as session:
            statement = select(AuthSession).where(AuthSession.session_token_hash == token_hash)
            result = await session.exec(statement)
            return result.one_or_none()

    async def update_session_csrf_token_hash(
        self,
        session_id: UUID,
        csrf_token_hash: str,
    ) -> AuthSession:
        async with self._unit_of_work.session_scope() as session:
            auth_session = await session.get(AuthSession, session_id)
            if auth_session is None:
                raise ValueError("Auth session not found")
            auth_session.csrf_token_hash = csrf_token_hash
            session.add(auth_session)
            await self._persist(session)
            await session.refresh(auth_session)
            return auth_session

    async def revoke_session(self, session_id: UUID) -> None:
        async with self._unit_of_work.session_scope() as session:
            auth_session = await session.get(AuthSession, session_id)
            if auth_session is None:
                return
            auth_session.revoked_at = utcnow()
            session.add(auth_session)
            await self._persist(session)

    async def touch_session(
        self,
        session_id: UUID,
        last_seen_at: datetime,
        expires_at: datetime,
    ) -> AuthSession:
        async with self._unit_of_work.session_scope() as session:
            auth_session = await session.get(AuthSession, session_id)
            if auth_session is None:
                raise ValueError("Auth session not found")
            auth_session.last_seen_at = last_seen_at
            auth_session.expires_at = expires_at
            session.add(auth_session)
            await self._persist(session)
            return auth_session

    async def record_user_login(self, user_id: UUID, login_at: datetime) -> User:
        async with self._unit_of_work.session_scope() as session:
            user = await session.get(User, user_id)
            if user is None:
                raise ValueError("User not found")
            user.last_login_at = login_at
            user.updated_at = login_at
            session.add(user)
            await self._persist(session)
            await session.refresh(user)
            return user

    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        async with self._unit_of_work.session_scope() as session:
            session.add(audit_log)
            await self._persist(session)
