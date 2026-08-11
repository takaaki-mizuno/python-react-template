import secrets
from datetime import timedelta
from logging import Logger
from uuid import UUID

from injector import inject

from app.config.auth import AuthSettings
from app.config.authorization import resolve_user_authorization
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.libraries.auth_session_issuer import calculate_session_expiry, replace_auth_session
from app.libraries.clock import utcnow
from app.libraries.password_hasher import PasswordHashExecutor, validate_password_policy
from app.libraries.session_tokens import generate_token, hash_token
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext, IssuedAuthSession
from app.models.auth_csrf import SessionCsrfStatus
from app.models.auth_errors import (EmailAlreadyRegisteredError, InvalidCredentialsError,
                                    RateLimitExceededError, WeakPasswordError)
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.authorization import UserAuthorization

DUMMY_PASSWORD_HASH = ("$argon2id$v=19$m=65536,t=3,p=4$TO8J42R39QBv7pem26bDUQ"
                       "$TsSlSgdcZ3mv06Gl9wQ7WaBhED0WIbQhcLhG35aHQd4")
SESSION_REJECTED_AUDIT_WINDOW_SECONDS = 300


class AuthUsecase(AuthUsecaseInterface):

    @inject
    def __init__(
        self,
        auth_repository: AuthRepositoryInterface,
        authorization_repository: AuthorizationRepositoryInterface,
        unit_of_work: UnitOfWorkInterface,
        auth_rate_limiter: LoginRateLimiterInterface,
        auth_settings: AuthSettings,
        password_hash_executor: PasswordHashExecutor,
        logger: Logger,
    ) -> None:
        self._auth_repository = auth_repository
        self._authorization_repository = authorization_repository
        self._unit_of_work = unit_of_work
        self._auth_rate_limiter = auth_rate_limiter
        self._auth_settings = auth_settings
        self._password_hash_executor = password_hash_executor
        self._logger = logger

    async def _audit_known_rejected_session(
        self,
        token_hash: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        rejected_session = await self._auth_repository.find_session_by_token_hash(token_hash)
        if rejected_session is None:
            return
        await self._auth_repository.record_rejected_session_replay(
            rejected_session,
            ip_address,
            user_agent,
            replayed_at=utcnow(),
            window_seconds=SESSION_REJECTED_AUDIT_WINDOW_SECONDS,
        )

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
    ) -> SessionCsrfStatus:
        session_token_hash = hash_token(session_token)
        auth_session = await self._auth_repository.find_active_session_by_token_hash(
            session_token_hash)
        if not auth_session:
            await self._audit_known_rejected_session(
                session_token_hash,
                ip_address,
                user_agent,
            )
            return SessionCsrfStatus.NO_SESSION
        if secrets.compare_digest(auth_session.csrf_token_hash, hash_token(csrf_token)):
            return SessionCsrfStatus.VALID
        return SessionCsrfStatus.MISMATCH

    async def register(
        self,
        email: str,
        password: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ):
        normalized_email = email.strip().lower()
        rate_limit_ip = ip_address or "unknown"
        if not self._auth_rate_limiter.is_allowed(rate_limit_ip, normalized_email):
            raise RateLimitExceededError(self._auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)
        if not self._auth_rate_limiter.is_registration_allowed(rate_limit_ip):
            raise RateLimitExceededError(
                self._auth_settings.AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS)

        is_valid_password, error_message = validate_password_policy(password)
        if not is_valid_password:
            # Defense-in-depth for callers that bypass the request DTO validator.
            self._auth_rate_limiter.record_failure(
                rate_limit_ip,
                normalized_email,
                include_email_bucket=False,
            )
            raise WeakPasswordError(error_message or "Invalid password")

        existing_user = await self._auth_repository.find_user_by_email(normalized_email)
        if existing_user:
            self._auth_rate_limiter.record_failure(
                rate_limit_ip,
                normalized_email,
                include_email_bucket=False,
            )
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
            async with self._unit_of_work.transaction():
                user = await self._auth_repository.create_user(
                    normalized_email,
                    await self._password_hash_executor.hash(password),
                )
                login_at = utcnow()
                user = await self._auth_repository.record_user_login(user.id, login_at)
                session, session_token, csrf_token = await replace_auth_session(
                    self._auth_repository,
                    self._auth_settings,
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
            self._auth_rate_limiter.record_failure(
                rate_limit_ip,
                normalized_email,
                include_email_bucket=False,
            )
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=None,
                    session_id=None,
                    event_type=AuthEventType.REGISTER_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            raise
        self._auth_rate_limiter.record_registration(rate_limit_ip)
        return IssuedAuthSession(
            user=user,
            session=session,
            session_token=session_token,
            csrf_token=csrf_token,
            roles=frozenset(),
            permissions=frozenset(),
        )

    async def login(
        self,
        email: str,
        password: str,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> IssuedAuthSession:
        normalized_email = email.strip().lower()
        rate_limit_ip = ip_address or "unknown"
        if not self._auth_rate_limiter.is_allowed(rate_limit_ip, normalized_email):
            raise RateLimitExceededError(self._auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)

        user = await self._auth_repository.find_user_by_email(normalized_email)
        password_hash = DUMMY_PASSWORD_HASH
        has_password_hash = False
        if user is not None and user.password_hash is not None:
            password_hash = user.password_hash
            has_password_hash = True
        password_matches = await self._password_hash_executor.verify(password, password_hash)
        if user is None or not user.is_active or not has_password_hash or not password_matches:
            self._auth_rate_limiter.record_failure(rate_limit_ip, normalized_email)
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=user.id if user is not None else None,
                    session_id=None,
                    event_type=AuthEventType.LOGIN_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
            raise InvalidCredentialsError

        async with self._unit_of_work.transaction():
            login_at = utcnow()
            user = await self._auth_repository.record_user_login(user.id, login_at)
            session, session_token, csrf_token = await replace_auth_session(
                self._auth_repository,
                self._auth_settings,
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
        self._auth_rate_limiter.record_success(rate_limit_ip, normalized_email)
        authorization = await self._authorization_for_existing_user(user.id)
        return IssuedAuthSession(
            user=user,
            session=session,
            session_token=session_token,
            csrf_token=csrf_token,
            roles=authorization.roles,
            permissions=authorization.permissions,
        )

    async def authenticate_session(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthenticatedSessionContext | None:
        if not session_token:
            return None

        session_token_hash = hash_token(session_token)
        async with self._unit_of_work.transaction():
            auth_session = await self._auth_repository.find_active_session_by_token_hash(
                session_token_hash)
            if not auth_session:
                await self._audit_known_rejected_session(
                    session_token_hash,
                    ip_address,
                    user_agent,
                )
                return None

            user = await self._auth_repository.find_user_by_id_for_authentication(
                auth_session.user_id)
            if user is None:
                await self._reject_session(
                    auth_session,
                    AuthEventType.SESSION_REJECTED,
                    user_id=None,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                return None
            if user.deleted_at is not None:
                await self._reject_user_sessions(
                    auth_session,
                    AuthEventType.SESSION_REVOKED_DELETED_USER,
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                return None
            if not user.is_active:
                await self._reject_user_sessions(
                    auth_session,
                    AuthEventType.SESSION_REVOKED_INACTIVE_USER,
                    user_id=user.id,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
                return None

            now = utcnow()
            refreshed_session = auth_session
            touch_interval_seconds = self._auth_settings.effective_session_touch_interval_seconds()
            if (touch_interval_seconds <= 0 or now - auth_session.last_seen_at
                    >= timedelta(seconds=touch_interval_seconds)):
                if (touch_interval_seconds
                        != self._auth_settings.AUTH_SESSION_TOUCH_INTERVAL_SECONDS):
                    self._logger.warning(
                        "AUTH_SESSION_TOUCH_INTERVAL_SECONDS=%s exceeds safe "
                        "idle TTL ratio; using %s",
                        self._auth_settings.AUTH_SESSION_TOUCH_INTERVAL_SECONDS,
                        touch_interval_seconds,
                    )
                refreshed_session = await self._auth_repository.touch_session(
                    auth_session.id,
                    last_seen_at=now,
                    expires_at=calculate_session_expiry(self._auth_settings, auth_session.issued_at,
                                                        now),
                )
            authorization = await self._authorization_for_existing_user(user.id)
            return AuthenticatedSessionContext(
                user=user,
                session=refreshed_session,
                roles=authorization.roles,
                permissions=authorization.permissions,
            )

    async def _authorization_for_existing_user(self, user_id: UUID) -> UserAuthorization:
        role_codes = await self._authorization_repository.get_user_role_codes(user_id)
        return resolve_user_authorization(user_id, role_codes, self._logger)

    async def _reject_session(
        self,
        auth_session: AuthSession,
        event_type: AuthEventType,
        user_id: UUID | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        await self._auth_repository.revoke_session(auth_session.id)
        await self._auth_repository.create_audit_log(
            AuthAuditLog(
                user_id=user_id,
                session_id=auth_session.id,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
            ))

    async def _reject_user_sessions(
        self,
        auth_session: AuthSession,
        event_type: AuthEventType,
        user_id: UUID,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        revoked_at = utcnow()
        await self._auth_repository.revoke_sessions_for_user(user_id, revoked_at)
        await self._auth_repository.create_audit_log(
            AuthAuditLog(
                user_id=user_id,
                session_id=auth_session.id,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
                occurred_at=revoked_at,
            ))

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

        async with self._unit_of_work.transaction():
            await self._auth_repository.revoke_session(auth_session.id)
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=auth_session.user_id,
                    session_id=auth_session.id,
                    event_type=AuthEventType.LOGOUT,
                    ip_address=ip_address,
                    user_agent=user_agent,
                ))
