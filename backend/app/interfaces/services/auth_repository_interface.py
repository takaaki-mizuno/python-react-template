from abc import ABCMeta, abstractmethod
from datetime import datetime
from uuid import UUID

from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_identity import AuthIdentity
from app.models.auth_oidc_state import AuthOidcState, AuthOidcStateConsumeResult
from app.models.auth_session import AuthSession
from app.models.language import DEFAULT_LANGUAGE_CODE, LanguageCode
from app.models.user import User


class AuthRepositoryInterface(metaclass=ABCMeta):

    @abstractmethod
    async def create_user(
        self,
        email: str,
        password_hash: str | None,
        language_code: LanguageCode = DEFAULT_LANGUAGE_CODE,
    ) -> User:
        raise NotImplementedError

    @abstractmethod
    async def update_user_language(
        self,
        user_id: UUID,
        language_code: LanguageCode,
        modified_at: datetime,
    ) -> User:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_email(self, normalized_email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_verified_email_for_oidc_link(self, email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_email_for_oidc_collision(self, email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_id_for_authentication(self, user_id: UUID) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def find_identity_by_provider_subject(
        self,
        provider_id: str,
        provider_subject: str,
    ) -> AuthIdentity | None:
        raise NotImplementedError

    @abstractmethod
    async def find_identities_by_user_id(self, user_id: UUID) -> list[AuthIdentity]:
        raise NotImplementedError

    @abstractmethod
    async def create_auth_identity(self, identity: AuthIdentity) -> AuthIdentity:
        raise NotImplementedError

    @abstractmethod
    async def delete_auth_identities_for_user(self, user_id: UUID) -> int:
        raise NotImplementedError

    @abstractmethod
    async def create_session(
        self,
        user_id: UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        issued_at: datetime,
        last_seen_at: datetime,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def find_active_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        raise NotImplementedError

    @abstractmethod
    async def find_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        raise NotImplementedError

    @abstractmethod
    async def update_session_csrf_token_hash(
        self,
        session_id: UUID,
        csrf_token_hash: str,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def revoke_session(self, session_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def touch_session(
        self,
        session_id: UUID,
        last_seen_at: datetime,
        expires_at: datetime,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def record_user_login(self, user_id: UUID, login_at: datetime) -> User:
        raise NotImplementedError

    @abstractmethod
    async def record_oidc_login(
        self,
        user_id: UUID,
        identity_id: UUID,
        session_id: UUID,
        login_at: datetime,
        provider_auth_time: datetime | None,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def record_oidc_reauth(
        self,
        session_id: UUID,
        auth_time: datetime,
        reauthenticated_at: datetime,
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def mark_user_deleted(
        self,
        user_id: UUID,
        deleted_at: datetime,
        *,
        session_id: UUID | None,
        ip_address: str | None,
    ) -> User:
        raise NotImplementedError

    @abstractmethod
    async def revoke_sessions_for_user(self, user_id: UUID, revoked_at: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    async def delete_sessions_expired_before(self, expired_before: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    async def delete_audit_logs_occurred_before(self, occurred_before: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    async def create_oidc_authorization_state(self, state: AuthOidcState) -> AuthOidcState:
        raise NotImplementedError

    @abstractmethod
    async def consume_oidc_authorization_state(
        self,
        state_hash: str,
        browser_binding_hash: str,
        consumed_at: datetime,
    ) -> AuthOidcStateConsumeResult:
        raise NotImplementedError

    @abstractmethod
    async def delete_oidc_states_expired_before(self, expired_before: datetime) -> int:
        raise NotImplementedError

    @abstractmethod
    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        raise NotImplementedError

    @abstractmethod
    async def record_rejected_session_replay(
        self,
        auth_session: AuthSession,
        ip_address: str | None,
        user_agent: str | None,
        replayed_at: datetime,
        window_seconds: int,
    ) -> None:
        raise NotImplementedError
