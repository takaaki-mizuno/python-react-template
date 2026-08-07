from datetime import datetime, timedelta
from uuid import UUID

from injector import inject
from sqlalchemy import delete, text, type_coerce, update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.libraries.clock import utcnow
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_errors import (AuthSessionNotFoundError, EmailAlreadyRegisteredError,
                                    UserNotFoundError)
from app.models.auth_event_type import AuthEventType
from app.models.auth_identity import AuthIdentity
from app.models.auth_oidc_state import AuthOidcState, AuthOidcStateConsumeResult
from app.models.auth_session import AuthSession
from app.models.user import User

REJECTED_SESSION_REPLAY_LOCK_CLASS_ID = 0x41555253
RECENT_REPLAY_IP_LIMIT = 10


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
            statement = select(User).where(
                func.lower(User.email) == normalized_email,
                col(User.deleted_at).is_(None),
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_user_by_verified_email_for_oidc_link(self, email: str) -> User | None:
        normalized_email = email.strip().lower()
        async with self._unit_of_work.session_scope() as session:
            statement = select(User).where(
                func.lower(User.email) == normalized_email,
                col(User.deleted_at).is_(None),
                col(User.is_active).is_(True),
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_user_by_email_for_oidc_collision(self, email: str) -> User | None:
        normalized_email = email.strip().lower()
        async with self._unit_of_work.session_scope() as session:
            statement = select(User).where(
                func.lower(User.email) == normalized_email,
                col(User.deleted_at).is_(None),
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_user_by_id_for_authentication(self, user_id: UUID) -> User | None:
        async with self._unit_of_work.session_scope() as session:
            statement = select(User).where(User.id == user_id)
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_identity_by_provider_subject(
        self,
        provider_id: str,
        provider_subject: str,
    ) -> AuthIdentity | None:
        async with self._unit_of_work.session_scope() as session:
            statement = select(AuthIdentity).where(
                AuthIdentity.provider_id == provider_id,
                AuthIdentity.provider_subject == provider_subject,
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                select(AuthIdentity).join(User,
                                          col(AuthIdentity.user_id) == col(User.id)).where(
                                              AuthIdentity.user_id == user_id,
                                              col(User.deleted_at).is_(None),
                                          ).order_by(col(AuthIdentity.created_at)))
            return list(result.all())

    async def create_auth_identity(self, identity: AuthIdentity) -> AuthIdentity:
        async with self._unit_of_work.session_scope() as session:
            session.add(identity)
            await self._persist(session)
            await session.refresh(identity)
            return identity

    async def delete_auth_identities_for_user(self, user_id: UUID) -> int:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                delete(AuthIdentity).where(col(AuthIdentity.user_id) == user_id))
            await self._persist(session)
            return int(result.rowcount or 0)

    async def create_session(
        self,
        user_id: UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at: datetime,
        issued_at: datetime,
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
                issued_at=issued_at,
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
                raise AuthSessionNotFoundError(session_id)
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
                raise AuthSessionNotFoundError(session_id)
            auth_session.last_seen_at = last_seen_at
            auth_session.expires_at = expires_at
            session.add(auth_session)
            await self._persist(session)
            return auth_session

    async def record_user_login(self, user_id: UUID, login_at: datetime) -> User:
        async with self._unit_of_work.session_scope() as session:
            user = await session.get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise UserNotFoundError(user_id)
            user.last_login_at = login_at
            user.updated_at = login_at
            session.add(user)
            await self._persist(session)
            await session.refresh(user)
            return user

    async def record_oidc_login(
        self,
        user_id: UUID,
        identity_id: UUID,
        session_id: UUID,
        login_at: datetime,
        provider_auth_time: datetime | None,
    ) -> None:
        async with self._unit_of_work.session_scope() as session:
            user = await session.get(User, user_id)
            if user is None or user.deleted_at is not None:
                raise UserNotFoundError(user_id)
            auth_session = await session.get(AuthSession, session_id)
            if auth_session is None:
                raise AuthSessionNotFoundError(session_id)

            user.last_login_at = login_at
            user.updated_at = login_at
            await session.exec(
                update(AuthIdentity).where(
                    col(AuthIdentity.id) == identity_id,
                    col(AuthIdentity.user_id) == user_id,
                ).values(last_login_at=login_at, updated_at=login_at))
            if provider_auth_time is not None:
                auth_session.last_oidc_auth_time_at = provider_auth_time
                session.add(auth_session)
            session.add(user)
            await self._persist(session)

    async def record_oidc_reauth(
        self,
        session_id: UUID,
        auth_time: datetime,
        reauthenticated_at: datetime,
    ) -> None:
        del reauthenticated_at
        async with self._unit_of_work.session_scope() as session:
            auth_session = await session.get(AuthSession, session_id)
            if auth_session is None:
                raise AuthSessionNotFoundError(session_id)
            auth_session.last_oidc_auth_time_at = auth_time
            session.add(auth_session)
            await self._persist(session)

    async def mark_user_deleted(
        self,
        user_id: UUID,
        deleted_at: datetime,
        *,
        session_id: UUID | None,
        ip_address: str | None,
    ) -> User:
        """Mark a user deleted once and record exactly one deletion audit event."""
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                update(User).where(
                    col(User.id) == user_id,
                    col(User.deleted_at).is_(None),
                ).values(deleted_at=deleted_at, updated_at=deleted_at))
            if int(result.rowcount or 0) == 0:
                existing_user = await session.get(User, user_id)
                if existing_user is None:
                    raise UserNotFoundError(user_id)
                return existing_user

            session.add(
                AuthAuditLog(
                    user_id=user_id,
                    session_id=session_id,
                    event_type=AuthEventType.USER_MARKED_DELETED,
                    ip_address=ip_address,
                    created_at=deleted_at,
                ))
            await self._persist(session)
            deleted_user = await session.get(User, user_id)
            if deleted_user is None:
                # Defensive guard for an inconsistent rowcount / identity map state.
                raise UserNotFoundError(user_id)
            return deleted_user

    async def revoke_sessions_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        """Internal contract for account deletion, role revocation, and password change."""
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                update(AuthSession).where(
                    col(AuthSession.user_id) == user_id,
                    col(AuthSession.revoked_at).is_(None),
                ).values(revoked_at=revoked_at))
            await self._persist(session)
            return int(result.rowcount or 0)

    async def delete_sessions_expired_before(self, expired_before: datetime) -> int:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                delete(AuthSession).where(col(AuthSession.expires_at) < expired_before))
            await self._persist(session)
            return int(result.rowcount or 0)

    async def delete_audit_logs_created_before(self, created_before: datetime) -> int:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                delete(AuthAuditLog).where(col(AuthAuditLog.created_at) < created_before))
            await self._persist(session)
            return int(result.rowcount or 0)

    async def create_oidc_authorization_state(self, state: AuthOidcState) -> AuthOidcState:
        async with self._unit_of_work.session_scope() as session:
            session.add(state)
            await self._persist(session)
            await session.refresh(state)
            return state

    async def consume_oidc_authorization_state(
        self,
        state_hash: str,
        browser_binding_hash: str,
        consumed_at: datetime,
    ) -> AuthOidcStateConsumeResult:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                select(AuthOidcState).where(
                    AuthOidcState.state_hash == state_hash).with_for_update())
            state = result.one_or_none()
            if state is None:
                return AuthOidcStateConsumeResult(status="state_mismatch")
            if state.consumed_at is not None:
                return AuthOidcStateConsumeResult(status="already_consumed", state=state)
            if state.expires_at <= consumed_at:
                return AuthOidcStateConsumeResult(status="expired", state=state)
            if state.browser_binding_hash != browser_binding_hash:
                return AuthOidcStateConsumeResult(
                    status="browser_binding_mismatch",
                    state=state,
                )
            state.consumed_at = consumed_at
            session.add(state)
            await self._persist(session)
            await session.refresh(state)
            return AuthOidcStateConsumeResult(status="consumed", state=state)

    async def delete_oidc_states_expired_before(self, expired_before: datetime) -> int:
        async with self._unit_of_work.session_scope() as session:
            result = await session.exec(
                delete(AuthOidcState).where((col(AuthOidcState.expires_at) < expired_before)
                                            | (col(AuthOidcState.consumed_at) < expired_before)))
            await self._persist(session)
            return int(result.rowcount or 0)

    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        async with self._unit_of_work.session_scope() as session:
            session.add(audit_log)
            await self._persist(session)

    async def record_rejected_session_replay(
        self,
        auth_session: AuthSession,
        ip_address: str | None,
        user_agent: str | None,
        replayed_at: datetime,
        window_seconds: int,
    ) -> None:
        async with self._unit_of_work.session_scope() as session:
            connection = await session.connection()
            lock_result = await connection.execute(
                text("SELECT pg_try_advisory_xact_lock(:class_id, :object_id)"),
                {
                    "class_id": REJECTED_SESSION_REPLAY_LOCK_CLASS_ID,
                    "object_id": _rejected_session_replay_lock_object_id(auth_session.id),
                },
            )
            if lock_result.scalar_one() is not True:
                return
            window_started_at = replayed_at - timedelta(seconds=window_seconds)
            result = await session.exec(
                select(AuthAuditLog).where(
                    AuthAuditLog.session_id == auth_session.id,
                    AuthAuditLog.event_type == AuthEventType.SESSION_REJECTED,
                    AuthAuditLog.created_at >= window_started_at,
                    type_coerce(AuthAuditLog.detail_json, JSONB).has_key("replay_count"),
                ).order_by(col(AuthAuditLog.created_at).desc()).limit(1))
            audit_log = result.one_or_none()
            if audit_log is None:
                session.add(
                    AuthAuditLog(
                        user_id=auth_session.user_id,
                        session_id=auth_session.id,
                        event_type=AuthEventType.SESSION_REJECTED,
                        ip_address=ip_address,
                        user_agent=user_agent,
                        detail_json=_replay_detail_json(
                            None,
                            ip_address,
                            user_agent,
                            replayed_at,
                            window_seconds,
                        ),
                        created_at=replayed_at,
                    ))
            else:
                audit_log.detail_json = _replay_detail_json(
                    dict(audit_log.detail_json or {}),
                    ip_address,
                    user_agent,
                    replayed_at,
                    window_seconds,
                )
                session.add(audit_log)
            await self._persist(session)


def _rejected_session_replay_lock_object_id(session_id: UUID) -> int:
    return session_id.int & 0x7fffffff


def _replay_detail_json(
    detail_json: dict | None,
    ip_address: str | None,
    user_agent: str | None,
    replayed_at: datetime,
    window_seconds: int,
) -> dict:
    detail_json = dict(detail_json or {})
    recent_ip_addresses = _recent_ip_addresses(detail_json)
    distinct_ip_count = _distinct_ip_count(detail_json, recent_ip_addresses)
    if ip_address is not None and ip_address not in recent_ip_addresses:
        distinct_ip_count += 1
        recent_ip_addresses.append(ip_address)
        recent_ip_addresses = recent_ip_addresses[-RECENT_REPLAY_IP_LIMIT:]
    return {
        **detail_json,
        "distinct_ip_count": distinct_ip_count,
        "last_ip_address": ip_address,
        "last_user_agent": user_agent,
        "last_replayed_at": replayed_at.isoformat(),
        "recent_ip_addresses": recent_ip_addresses,
        "replay_count": _replay_count(detail_json) + 1,
        "window_seconds": window_seconds,
    }


def _recent_ip_addresses(detail_json: dict) -> list[str]:
    recent_ip_addresses = detail_json.get("recent_ip_addresses", [])
    if not isinstance(recent_ip_addresses, list):
        return []
    return [ip_address for ip_address in recent_ip_addresses if isinstance(ip_address, str)]


def _distinct_ip_count(detail_json: dict, recent_ip_addresses: list[str]) -> int:
    distinct_ip_count = detail_json.get("distinct_ip_count", len(recent_ip_addresses))
    if isinstance(distinct_ip_count, int):
        return max(distinct_ip_count, len(recent_ip_addresses))
    return len(recent_ip_addresses)


def _replay_count(detail_json: dict) -> int:
    replay_count = detail_json.get("replay_count", 0)
    if isinstance(replay_count, int):
        return max(replay_count, 0)
    return 0
