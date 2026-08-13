import base64
import hashlib
from datetime import timedelta
from logging import Logger
from typing import NoReturn
from urllib.parse import urlparse
from uuid import UUID

from injector import inject

from app.config.auth import AuthSettings
from app.config.authorization import resolve_user_authorization
from app.config.oidc import OidcProviderSettings, OidcSettings
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.services.authorization_repository_interface import \
    AuthorizationRepositoryInterface
from app.interfaces.services.oidc_provider_client_interface import OidcProviderClientInterface
from app.interfaces.services.unit_of_work_interface import UnitOfWorkInterface
from app.interfaces.usecases.oauth_oidc_usecase_interface import OAuthOidcUsecaseInterface
from app.libraries.auth_session_issuer import replace_auth_session
from app.libraries.clock import utcnow
from app.libraries.session_tokens import generate_token, hash_token
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext, IssuedAuthSession
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.auth_event_type import AuthEventType
from app.models.auth_identity import AuthIdentity
from app.models.auth_oidc_state import AuthOidcState
from app.models.authorization import UserAuthorization
from app.models.language import DEFAULT_LANGUAGE_CODE, LanguageCode, is_supported_language_code
from app.models.oidc import (OidcAuthorizationPurpose, OidcAuthorizationStartResult,
                             OidcCallbackResult, OidcVerifiedClaims)
# yapf: disable
from app.models.oidc_errors import (OidcAuthorizationRateLimitedError,
                                    OidcBrowserBindingMismatchError, OidcCallbackFlowError,
                                    OidcEmailNotVerifiedError, OidcIdentityLinkDisabledError,
                                    OidcIdentityLinkRequiredError, OidcIdentityUnavailableError,
                                    OidcProviderNotConfiguredError, OidcProvisioningDisabledError,
                                    OidcReauthAuthenticationRequiredError,
                                    OidcReauthAuthTimeRequiredError, OidcReauthStaleError,
                                    OidcReauthSubjectMismatchError, OidcStateMismatchError)
# yapf: enable
from app.models.user import User

AUTH_REDIRECT_PATHS = {"/login", "/register"}
DEFAULT_REDIRECT_PATH = "/app"


class OAuthOidcUsecase(OAuthOidcUsecaseInterface):

    @inject
    def __init__(
        self,
        auth_repository: AuthRepositoryInterface,
        authorization_repository: AuthorizationRepositoryInterface,
        unit_of_work: UnitOfWorkInterface,
        auth_rate_limiter: LoginRateLimiterInterface,
        auth_settings: AuthSettings,
        oidc_settings: OidcSettings,
        oidc_provider_client: OidcProviderClientInterface,
        logger: Logger,
    ) -> None:
        self._auth_repository = auth_repository
        self._authorization_repository = authorization_repository
        self._unit_of_work = unit_of_work
        self._auth_rate_limiter = auth_rate_limiter
        self._auth_settings = auth_settings
        self._oidc_settings = oidc_settings
        self._oidc_provider_client = oidc_provider_client
        self._logger = logger

    async def start_authorization(
        self,
        provider_id: str,
        redirect_path: str | None,
        purpose: OidcAuthorizationPurpose,
        current_session: AuthenticatedSessionContext | None,
        ip_address: str | None,
        language_code: LanguageCode | None = None,
    ) -> OidcAuthorizationStartResult:
        try:
            provider = self._oidc_settings.get_provider(provider_id)
        except KeyError as exc:
            raise OidcProviderNotConfiguredError(provider_id) from exc

        if purpose == "account_deletion_reauth" and current_session is None:
            raise OidcReauthAuthenticationRequiredError(
                "Current session is required for OIDC reauth")

        rate_limit_ip = ip_address or "unknown"
        if not await self._auth_rate_limiter.is_oidc_authorization_allowed(rate_limit_ip):
            raise OidcAuthorizationRateLimitedError

        state = generate_token()
        browser_binding = generate_token()
        nonce = generate_token()
        pkce_verifier = generate_token()
        state_hash = hash_token(state)
        now = utcnow()

        authorization_url = await self._oidc_provider_client.build_authorization_url(
            provider_id=provider.provider_id,
            state=state,
            nonce=nonce,
            code_challenge=_s256_code_challenge(pkce_verifier),
            prompt="login" if purpose == "account_deletion_reauth" else None,
            max_age=0 if purpose == "account_deletion_reauth" else None,
            login_hint=(current_session.user.email.strip().lower()
                        if purpose == "account_deletion_reauth" and current_session else None),
        )

        async with self._unit_of_work.transaction():
            await self._auth_repository.create_oidc_authorization_state(
                AuthOidcState(
                    state_hash=state_hash,
                    browser_binding_hash=hash_token(browser_binding),
                    nonce_hash=hash_token(nonce),
                    pkce_verifier=pkce_verifier,
                    provider_id=provider.provider_id,
                    purpose=purpose,
                    expected_user_id=(current_session.user.id if current_session else None),
                    expected_session_id=(current_session.session.id if current_session else None),
                    redirect_path=_normalize_redirect_path(redirect_path),
                    login_hint=(current_session.user.email.strip().lower() if
                                purpose == "account_deletion_reauth" and current_session else None),
                    language_code=(language_code if purpose == "login" else None),
                    expires_at=now +
                    timedelta(seconds=self._oidc_settings.AUTH_OIDC_STATE_TTL_SECONDS),
                ))
            await self._auth_rate_limiter.record_oidc_authorization(rate_limit_ip)

        return OidcAuthorizationStartResult(
            provider_id=provider.provider_id,
            authorization_url=authorization_url.url,
            browser_binding_cookie_name=f"oidc_binding_{state_hash[:16]}",
            browser_binding_cookie_value=browser_binding,
            browser_binding_cookie_max_age=self._oidc_settings.AUTH_OIDC_STATE_TTL_SECONDS,
        )

    async def complete_callback(
        self,
        provider_id: str,
        state: str,
        code: str,
        browser_binding_cookie_value: str | None,
        current_session: AuthenticatedSessionContext | None,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> OidcCallbackResult:
        try:
            provider = self._oidc_settings.get_provider(provider_id)
        except KeyError as exc:
            raise OidcProviderNotConfiguredError(provider_id) from exc
        oidc_state = await self._consume_callback_state(
            provider=provider,
            state=state,
            browser_binding_cookie_value=browser_binding_cookie_value,
        )

        purpose = oidc_state.purpose
        try:
            token_set = await self._oidc_provider_client.exchange_code(
                provider_id=provider.provider_id,
                code=code,
                code_verifier=oidc_state.pkce_verifier,
            )
            claims = await self._oidc_provider_client.validate_id_token(
                provider_id=provider.provider_id,
                id_token=token_set.id_token,
                expected_nonce_hash=oidc_state.nonce_hash,
                require_auth_time=purpose == "account_deletion_reauth",
            )
            if purpose == "account_deletion_reauth":
                return await self._complete_reauth_callback(
                    provider=provider,
                    oidc_state=oidc_state,
                    claims=claims,
                    current_session=current_session,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            return await self._complete_login_callback(
                provider=provider,
                oidc_state=oidc_state,
                claims=claims,
                current_session_token=current_session_token,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        except Exception as exc:
            if purpose == "account_deletion_reauth":
                await self._audit_oidc_failure(
                    AuthEventType.OIDC_REAUTH_FAILED,
                    provider.provider_id,
                    purpose,
                    exc,
                    ip_address,
                    user_agent,
                    user_id=current_session.user.id
                    if current_session else oidc_state.expected_user_id,
                    session_id=(current_session.session.id
                                if current_session else oidc_state.expected_session_id),
                )
            else:
                await self._audit_oidc_failure(
                    AuthEventType.OIDC_LOGIN_FAILED,
                    provider.provider_id,
                    purpose,
                    exc,
                    ip_address,
                    user_agent,
                    user_id=None,
                    session_id=None,
                )
            raise OidcCallbackFlowError(
                exc,
                purpose=purpose,
                redirect_path=oidc_state.redirect_path,
            ) from exc

    async def complete_error_callback(
        self,
        provider_id: str,
        state: str,
        browser_binding_cookie_value: str | None,
        provider_error: Exception,
        current_session: AuthenticatedSessionContext | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> NoReturn:
        try:
            provider = self._oidc_settings.get_provider(provider_id)
        except KeyError as exc:
            raise OidcProviderNotConfiguredError(provider_id) from exc
        oidc_state = await self._consume_callback_state(
            provider=provider,
            state=state,
            browser_binding_cookie_value=browser_binding_cookie_value,
        )
        if oidc_state.purpose == "account_deletion_reauth":
            await self._audit_oidc_failure(
                AuthEventType.OIDC_REAUTH_FAILED,
                provider.provider_id,
                oidc_state.purpose,
                provider_error,
                ip_address,
                user_agent,
                user_id=current_session.user.id if current_session else oidc_state.expected_user_id,
                session_id=(current_session.session.id
                            if current_session else oidc_state.expected_session_id),
            )
        else:
            await self._audit_oidc_failure(
                AuthEventType.OIDC_LOGIN_FAILED,
                provider.provider_id,
                oidc_state.purpose,
                provider_error,
                ip_address,
                user_agent,
                user_id=None,
                session_id=None,
            )
        raise OidcCallbackFlowError(
            provider_error,
            purpose=oidc_state.purpose,
            redirect_path=oidc_state.redirect_path,
        )

    async def _consume_callback_state(
        self,
        *,
        provider: OidcProviderSettings,
        state: str,
        browser_binding_cookie_value: str | None,
    ) -> AuthOidcState:
        if browser_binding_cookie_value is None:
            raise OidcBrowserBindingMismatchError

        state_hash = hash_token(state)
        consumed_at = utcnow()
        async with self._unit_of_work.transaction():
            consume_result = await self._auth_repository.consume_oidc_authorization_state(
                state_hash=state_hash,
                browser_binding_hash=hash_token(browser_binding_cookie_value),
                consumed_at=consumed_at,
            )
        if consume_result.status in {"state_mismatch", "expired", "already_consumed"}:
            raise OidcStateMismatchError
        if consume_result.status == "browser_binding_mismatch":
            raise OidcBrowserBindingMismatchError
        oidc_state = consume_result.state
        if oidc_state is None or oidc_state.provider_id != provider.provider_id:
            raise OidcStateMismatchError
        return oidc_state

    async def _complete_login_callback(
        self,
        *,
        provider: OidcProviderSettings,
        oidc_state: AuthOidcState,
        claims: OidcVerifiedClaims,
        current_session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> OidcCallbackResult:
        language_code = (oidc_state.language_code if oidc_state.language_code is not None
                         and is_supported_language_code(oidc_state.language_code) else None)
        async with self._unit_of_work.transaction():
            user, identity, setup_audits = await self._resolve_login_user_and_identity(
                provider,
                claims,
                language_code,
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
            await self._auth_repository.record_oidc_login(
                user.id,
                identity.id,
                session.id,
                login_at,
                claims.auth_time,
            )
            for event_type in setup_audits:
                await self._auth_repository.create_audit_log(
                    self._audit_log(
                        event_type,
                        user.id,
                        session.id,
                        provider.provider_id,
                        oidc_state.purpose,
                        ip_address,
                        user_agent,
                    ))
            await self._auth_repository.create_audit_log(
                self._audit_log(
                    AuthEventType.OIDC_LOGIN_SUCCESS,
                    user.id,
                    session.id,
                    provider.provider_id,
                    oidc_state.purpose,
                    ip_address,
                    user_agent,
                ))
        authorization = await self._authorization_for_existing_user(user.id)
        return OidcCallbackResult(
            redirect_path=oidc_state.redirect_path,
            issued_session=IssuedAuthSession(
                user=user,
                session=session,
                session_token=session_token,
                csrf_token=csrf_token,
                roles=authorization.roles,
                permissions=authorization.permissions,
            ),
        )

    async def _authorization_for_existing_user(self, user_id: UUID) -> UserAuthorization:
        role_codes = await self._authorization_repository.get_user_role_codes(user_id)
        return resolve_user_authorization(user_id, role_codes, self._logger)

    async def _resolve_login_user_and_identity(
        self,
        provider: OidcProviderSettings,
        claims: OidcVerifiedClaims,
        language_code: LanguageCode | None,
    ) -> tuple[User, AuthIdentity, list[AuthEventType]]:
        identity = await self._auth_repository.find_identity_by_provider_subject(
            provider.provider_id,
            claims.subject,
        )
        if identity is not None:
            user = await self._auth_repository.find_user_by_id_for_authentication(identity.user_id)
            if user is None or user.deleted_at is not None or not user.is_active:
                raise OidcIdentityUnavailableError
            return user, identity, []

        normalized_email = _trusted_verified_email(provider, claims)
        linked_user = await self._auth_repository.find_user_by_verified_email_for_oidc_link(
            normalized_email)
        if linked_user is not None:
            if provider.link_mode == "disabled":
                raise OidcIdentityLinkDisabledError
            if provider.link_mode != "auto":
                raise OidcIdentityLinkRequiredError
            identity = await self._auth_repository.create_auth_identity(
                _identity_for_claims(provider, claims, linked_user.id))
            return linked_user, identity, [AuthEventType.OIDC_IDENTITY_LINKED]

        colliding_user = await self._auth_repository.find_user_by_email_for_oidc_collision(
            normalized_email)
        if colliding_user is not None:
            raise OidcIdentityUnavailableError

        if not provider.allows_auto_provision:
            raise OidcProvisioningDisabledError
        try:
            user = await self._auth_repository.create_user(
                normalized_email,
                None,
                language_code=language_code or DEFAULT_LANGUAGE_CODE,
            )
        except EmailAlreadyRegisteredError as exc:
            raise OidcIdentityUnavailableError from exc
        identity = await self._auth_repository.create_auth_identity(
            _identity_for_claims(provider, claims, user.id))
        return user, identity, [AuthEventType.OIDC_USER_PROVISIONED]

    async def _complete_reauth_callback(
        self,
        *,
        provider: OidcProviderSettings,
        oidc_state: AuthOidcState,
        claims: OidcVerifiedClaims,
        current_session: AuthenticatedSessionContext | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> OidcCallbackResult:
        if current_session is None:
            raise OidcReauthAuthenticationRequiredError("Current session is required")
        if (oidc_state.expected_user_id != current_session.user.id
                or oidc_state.expected_session_id != current_session.session.id):
            raise OidcReauthSubjectMismatchError
        identity = await self._auth_repository.find_identity_by_provider_subject(
            provider.provider_id,
            claims.subject,
        )
        if identity is None or identity.user_id != current_session.user.id:
            raise OidcReauthSubjectMismatchError
        auth_time = claims.auth_time
        if auth_time is None:
            raise OidcReauthAuthTimeRequiredError
        if utcnow() - auth_time > timedelta(
                seconds=self._oidc_settings.AUTH_OIDC_REAUTH_FRESHNESS_SECONDS):
            raise OidcReauthStaleError

        reauthenticated_at = utcnow()
        async with self._unit_of_work.transaction():
            await self._auth_repository.record_oidc_reauth(
                current_session.session.id,
                auth_time,
                reauthenticated_at,
            )
            await self._auth_repository.create_audit_log(
                self._audit_log(
                    AuthEventType.OIDC_REAUTH_SUCCESS,
                    current_session.user.id,
                    current_session.session.id,
                    provider.provider_id,
                    oidc_state.purpose,
                    ip_address,
                    user_agent,
                ))
        return OidcCallbackResult(
            redirect_path=oidc_state.redirect_path,
            reauthenticated_context=current_session,
        )

    async def _audit_oidc_failure(
        self,
        event_type: AuthEventType,
        provider_id: str,
        purpose: str,
        error: Exception,
        ip_address: str | None,
        user_agent: str | None,
        *,
        user_id: UUID | None,
        session_id: UUID | None,
    ) -> None:
        await self._auth_repository.create_audit_log(
            AuthAuditLog(
                user_id=user_id,
                session_id=session_id,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent,
                detail_json={
                    "provider_id": provider_id,
                    "purpose": purpose,
                    "error": type(error).__name__,
                },
            ))

    def _audit_log(
        self,
        event_type: AuthEventType,
        user_id: UUID,
        session_id: UUID,
        provider_id: str,
        purpose: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthAuditLog:
        return AuthAuditLog(
            user_id=user_id,
            session_id=session_id,
            event_type=event_type,
            ip_address=ip_address,
            user_agent=user_agent,
            detail_json={
                "provider_id": provider_id,
                "purpose": purpose,
            },
        )


def _s256_code_challenge(code_verifier: str) -> str:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _normalize_redirect_path(value: str | None) -> str:
    if not value:
        return DEFAULT_REDIRECT_PATH
    if len(value) > 2048:
        return DEFAULT_REDIRECT_PATH
    if not value.startswith("/"):
        return DEFAULT_REDIRECT_PATH
    if "\\" in value or _has_ascii_control(value):
        return DEFAULT_REDIRECT_PATH
    parsed = urlparse(value)
    if parsed.scheme or parsed.netloc:
        return DEFAULT_REDIRECT_PATH
    normalized_path = (parsed.path.rstrip("/") or "/").lower()
    if normalized_path in AUTH_REDIRECT_PATHS:
        return DEFAULT_REDIRECT_PATH
    query = f"?{parsed.query}" if parsed.query else ""
    fragment = f"#{parsed.fragment}" if parsed.fragment else ""
    normalized = f"{parsed.path or '/'}{query}{fragment}"
    if len(normalized) > 2048:
        return DEFAULT_REDIRECT_PATH
    return normalized


def _has_ascii_control(value: str) -> bool:
    return any(ord(character) <= 0x1F or ord(character) == 0x7F for character in value)


def _trusted_verified_email(
    provider: OidcProviderSettings,
    claims: OidcVerifiedClaims,
) -> str:
    if not provider.trust_verified_email or not claims.email_verified or claims.email is None:
        raise OidcEmailNotVerifiedError
    normalized_email = claims.email.strip().lower()
    if not normalized_email:
        raise OidcEmailNotVerifiedError
    return normalized_email


def _identity_for_claims(
    provider: OidcProviderSettings,
    claims: OidcVerifiedClaims,
    user_id: UUID,
) -> AuthIdentity:
    email = claims.email.strip().lower() if claims.email is not None else None
    return AuthIdentity(
        user_id=user_id,
        provider_id=provider.provider_id,
        provider_subject=claims.subject,
        email=email,
        is_email_verified=claims.email_verified,
        claims_json=claims.claims_json,
    )
