import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from logging import Logger

from app.config.auth import AuthSettings
from app.interfaces.services.auth_repository_interface import \
    AuthRepositoryInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.libraries.password_hasher import (hash_password,
                                           validate_password_policy,
                                           verify_password)
from app.libraries.session_tokens import generate_token, hash_token
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_errors import (EmailAlreadyRegisteredError,
                                    InvalidCredentialsError,
                                    RateLimitExceededError, WeakPasswordError)
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.user import User

DUMMY_PASSWORD_HASH = ("$argon2id$v=19$m=65536,t=3,p=4$TO8J42R39QBv7pem26bDUQ"
                       "$TsSlSgdcZ3mv06Gl9wQ7WaBhED0WIbQhcLhG35aHQd4")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class AuthenticatedSessionContext:
    user: User
    session: AuthSession


class AuthUsecase(AuthUsecaseInterface):

    def __init__(
        self,
        auth_repository: AuthRepositoryInterface,
        auth_rate_limiter: InMemoryLoginRateLimiter,
        auth_settings: AuthSettings,
        logger: Logger,
    ):
        self._auth_repository = auth_repository
        self._auth_rate_limiter = auth_rate_limiter
        self._auth_settings = auth_settings
        self._logger = logger

    async def _audit_known_rejected_session(
        self,
        token_hash: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        rejected_session = await self._auth_repository.find_session_by_token_hash(
            token_hash)
        if rejected_session is None:
            return
        await self._auth_repository.create_audit_log(
            AuthAuditLog(
                user_id=rejected_session.user_id,
                session_id=rejected_session.id,
                event_type=AuthEventType.SESSION_REJECTED,
                ip_address=ip_address,
                user_agent=user_agent,
            ))

    async def issue_csrf_token(self, session_token: str | None = None) -> str:
        csrf_token = generate_token()
        if not session_token:
            return csrf_token

        auth_session = await self._auth_repository.find_active_session_by_token_hash(
            hash_token(session_token), )
        if not auth_session:
            return csrf_token

        await self._auth_repository.update_session_csrf_token_hash(
            auth_session.id,
            hash_token(csrf_token),
        )
        return csrf_token

    async def validate_session_csrf(
        self,
        session_token: str,
        csrf_token: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> bool | None:
        session_token_hash = hash_token(session_token)
        auth_session = await self._auth_repository.find_active_session_by_token_hash(
            session_token_hash)
        if not auth_session:
            await self._audit_known_rejected_session(
                session_token_hash,
                ip_address,
                user_agent,
            )
            return None
        return secrets.compare_digest(auth_session.csrf_token_hash,
                                      hash_token(csrf_token))

    def _calculate_session_expiry(
        self,
        created_at: datetime,
        last_seen_at: datetime,
    ) -> datetime:
        absolute_expires_at = created_at + timedelta(
            seconds=self._auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS, )
        idle_expires_at = last_seen_at + timedelta(
            seconds=self._auth_settings.AUTH_SESSION_IDLE_TTL_SECONDS, )
        return min(absolute_expires_at, idle_expires_at)

    async def _replace_session(
        self,
        user: User,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[AuthSession, str, str]:
        if current_session_token:
            existing_session = await self._auth_repository.find_active_session_by_token_hash(
                hash_token(current_session_token), )
            if existing_session:
                await self._auth_repository.revoke_session(existing_session.id)

        session_token = generate_token()
        csrf_token = generate_token()
        created_at = utcnow()
        last_seen_at = created_at
        expires_at = self._calculate_session_expiry(created_at, last_seen_at)
        session = await self._auth_repository.create_session(
            user_id=user.id,
            session_token_hash=hash_token(session_token),
            csrf_token_hash=hash_token(csrf_token),
            created_at=created_at,
            last_seen_at=last_seen_at,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return session, session_token, csrf_token

    async def register(
        self,
        email: str,
        password: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ):
        normalized_email = email.strip().lower()
        if not self._auth_rate_limiter.allow(ip_address or "unknown",
                                             normalized_email):
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=None,
                    session_id=None,
                    event_type=AuthEventType.REGISTER_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            raise RateLimitExceededError

        is_valid_password, error_message = validate_password_policy(password)
        if not is_valid_password:
            # Defense-in-depth for callers that bypass the request DTO validator.
            raise WeakPasswordError(error_message or "Invalid password")

        existing_user = await self._auth_repository.find_user_by_email(
            normalized_email)
        if existing_user:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=existing_user.id,
                    session_id=None,
                    event_type=AuthEventType.REGISTER_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            raise EmailAlreadyRegisteredError

        try:
            async with self._auth_repository.transaction():
                user = await self._auth_repository.create_user(
                    normalized_email,
                    hash_password(password),
                )
                login_at = utcnow()
                user = await self._auth_repository.record_user_login(
                    user.id, login_at)
                session, session_token, csrf_token = await self._replace_session(
                    user=user,
                    current_session_token=current_session_token,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                await self._auth_repository.create_audit_log(
                    AuthAuditLog(
                        user_id=user.id,
                        session_id=session.id,
                        event_type=AuthEventType.REGISTER_SUCCESS,
                        ip_address=ip_address,
                        user_agent=user_agent,
                    ))
        except EmailAlreadyRegisteredError:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=None,
                    session_id=None,
                    event_type=AuthEventType.REGISTER_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            raise
        return user, session, session_token, csrf_token

    async def login(
        self,
        email: str,
        password: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ):
        normalized_email = email.strip().lower()
        if not self._auth_rate_limiter.allow(ip_address or "unknown",
                                             normalized_email):
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=None,
                    session_id=None,
                    event_type=AuthEventType.LOGIN_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            raise RateLimitExceededError

        user = await self._auth_repository.find_user_by_email(normalized_email)
        password_hash = user.password_hash if user else DUMMY_PASSWORD_HASH
        password_matches = verify_password(password, password_hash)
        if not user or not user.is_active or not password_matches:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=user.id if user else None,
                    session_id=None,
                    event_type=AuthEventType.LOGIN_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            raise InvalidCredentialsError

        async with self._auth_repository.transaction():
            login_at = utcnow()
            user = await self._auth_repository.record_user_login(
                user.id, login_at)
            session, session_token, csrf_token = await self._replace_session(
                user=user,
                current_session_token=current_session_token,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=user.id,
                    session_id=session.id,
                    event_type=AuthEventType.LOGIN_SUCCESS,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
        return user, session, session_token, csrf_token

    async def authenticate_session(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthenticatedSessionContext | None:
        if not session_token:
            return None

        session_token_hash = hash_token(session_token)
        auth_session = await self._auth_repository.find_active_session_by_token_hash(
            session_token_hash)
        if not auth_session:
            await self._audit_known_rejected_session(
                session_token_hash,
                ip_address,
                user_agent,
            )
            return None

        user = await self._auth_repository.find_user_by_id(auth_session.user_id
                                                           )
        if not user or not user.is_active:
            await self._auth_repository.revoke_session(auth_session.id)
            return None

        now = utcnow()
        refreshed_session = await self._auth_repository.touch_session(
            auth_session.id,
            last_seen_at=now,
            expires_at=self._calculate_session_expiry(auth_session.created_at,
                                                      now),
        )
        return AuthenticatedSessionContext(user=user,
                                           session=refreshed_session)

    async def logout(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        if not session_token:
            return

        auth_session = await self._auth_repository.find_active_session_by_token_hash(
            hash_token(session_token), )
        if not auth_session:
            return

        async with self._auth_repository.transaction():
            await self._auth_repository.revoke_session(auth_session.id)
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=auth_session.user_id,
                    session_id=auth_session.id,
                    event_type=AuthEventType.LOGOUT,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
