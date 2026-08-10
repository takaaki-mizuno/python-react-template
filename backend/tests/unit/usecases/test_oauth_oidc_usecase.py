from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from logging import getLogger

import pytest

from app.config.auth import AuthSettings
from app.config.oidc import OidcProviderSettings, OidcSettings
from app.libraries.clock import utcnow
from app.libraries.session_tokens import hash_token
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.auth_event_type import AuthEventType
from app.models.auth_identity import AuthIdentity
from app.models.auth_oidc_state import AuthOidcState
from app.models.auth_session import AuthSession
from app.models.oidc import OidcAuthorizationUrl, OidcTokenSetForValidation, OidcVerifiedClaims
# yapf: disable
from app.models.oidc_errors import (OidcAuthorizationRateLimitedError,
                                    OidcBrowserBindingMismatchError, OidcCallbackFlowError,
                                    OidcEmailNotVerifiedError, OidcIdentityLinkDisabledError,
                                    OidcIdentityLinkRequiredError, OidcIdentityUnavailableError,
                                    OidcProviderAccessDeniedError, OidcProviderNotConfiguredError,
                                    OidcProvisioningDisabledError,
                                    OidcReauthAuthenticationRequiredError,
                                    OidcReauthAuthTimeRequiredError, OidcReauthStaleError,
                                    OidcReauthSubjectMismatchError, OidcStateMismatchError)
# yapf: enable
from app.models.user import User
from app.usecases.oauth_oidc_usecase import OAuthOidcUsecase

pytestmark = pytest.mark.asyncio


class UnitOfWorkStub:

    def __init__(self) -> None:
        self.in_transaction = False
        self.transaction_entries = 0

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[None]:
        self.transaction_entries += 1
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False


class AuthRepositoryStub:

    def __init__(self, unit_of_work: UnitOfWorkStub) -> None:
        self._unit_of_work = unit_of_work
        self.created_states: list[tuple[AuthOidcState, bool]] = []
        self.consumed_states: list[tuple[str, str, bool]] = []
        self.users_by_id: dict = {}
        self.users_by_email: dict[str, User] = {}
        self.identities_by_subject: dict[tuple[str, str], AuthIdentity] = {}
        self.created_users: list[tuple[str, str | None, bool]] = []
        self.created_identities: list[tuple[AuthIdentity, bool]] = []
        self.created_sessions: list[tuple[AuthSession, bool]] = []
        self.revoked_session_ids: list = []
        self.recorded_oidc_logins: list[tuple] = []
        self.recorded_oidc_reauths: list[tuple] = []
        self.audit_logs: list[tuple[AuthAuditLog, bool]] = []
        self.create_user_error: Exception | None = None

    async def create_oidc_authorization_state(self, state: AuthOidcState) -> AuthOidcState:
        self.created_states.append((state, self._unit_of_work.in_transaction))
        return state

    async def consume_oidc_authorization_state(
        self,
        state_hash: str,
        browser_binding_hash: str,
        consumed_at: datetime,
    ):
        from app.models.auth_oidc_state import AuthOidcStateConsumeResult

        self.consumed_states.append(
            (state_hash, browser_binding_hash, self._unit_of_work.in_transaction))
        for state, _ in self.created_states:
            if state.state_hash != state_hash:
                continue
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
            return AuthOidcStateConsumeResult(status="consumed", state=state)
        return AuthOidcStateConsumeResult(status="state_mismatch")

    async def find_identity_by_provider_subject(
        self,
        provider_id: str,
        provider_subject: str,
    ) -> AuthIdentity | None:
        return self.identities_by_subject.get((provider_id, provider_subject))

    async def find_user_by_verified_email_for_oidc_link(self, email: str) -> User | None:
        user = self.users_by_email.get(email.strip().lower())
        if user is None or user.deleted_at is not None or not user.is_active:
            return None
        return user

    async def find_user_by_email_for_oidc_collision(self, email: str) -> User | None:
        user = self.users_by_email.get(email.strip().lower())
        if user is None or user.deleted_at is not None:
            return None
        return user

    async def find_user_by_id_for_authentication(self, user_id) -> User | None:
        return self.users_by_id.get(user_id)

    async def create_user(self, email: str, password_hash: str | None) -> User:
        if self.create_user_error is not None:
            raise self.create_user_error
        user = User(email=email, password_hash=password_hash, is_active=True)
        self.users_by_id[user.id] = user
        self.users_by_email[email.strip().lower()] = user
        self.created_users.append((email, password_hash, self._unit_of_work.in_transaction))
        return user

    async def create_auth_identity(self, identity: AuthIdentity) -> AuthIdentity:
        self.identities_by_subject[(identity.provider_id, identity.provider_subject)] = identity
        self.created_identities.append((identity, self._unit_of_work.in_transaction))
        return identity

    async def find_active_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        for session, _ in self.created_sessions:
            if session.session_token_hash == token_hash and session.revoked_at is None:
                return session
        return None

    async def revoke_session(self, session_id) -> None:
        self.revoked_session_ids.append(session_id)

    async def create_session(
        self,
        user_id,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at: datetime,
        issued_at: datetime,
        last_seen_at: datetime,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        session = AuthSession(
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
        self.created_sessions.append((session, self._unit_of_work.in_transaction))
        return session

    async def record_user_login(self, user_id, login_at: datetime) -> User:
        user = self.users_by_id[user_id]
        user.last_login_at = login_at
        return user

    async def record_oidc_login(
        self,
        user_id,
        identity_id,
        session_id,
        login_at: datetime,
        provider_auth_time: datetime | None,
    ) -> None:
        self.recorded_oidc_logins.append((user_id, identity_id, session_id, login_at,
                                          provider_auth_time, self._unit_of_work.in_transaction))

    async def record_oidc_reauth(
        self,
        session_id,
        auth_time: datetime,
        reauthenticated_at: datetime,
    ) -> None:
        self.recorded_oidc_reauths.append(
            (session_id, auth_time, reauthenticated_at, self._unit_of_work.in_transaction))

    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        self.audit_logs.append((audit_log, self._unit_of_work.in_transaction))


class AuthorizationRepositoryStub:

    def __init__(self) -> None:
        self.role_codes = ("admin", )

    async def get_user_role_codes(self, _user_id):
        return self.role_codes


class RateLimiterStub:

    def __init__(self, allowed: bool = True) -> None:
        self.allowed = allowed
        self.is_oidc_authorization_allowed_calls: list[str] = []
        self.record_oidc_authorization_calls: list[str] = []

    def is_oidc_authorization_allowed(self, ip_address: str) -> bool:
        self.is_oidc_authorization_allowed_calls.append(ip_address)
        return self.allowed

    def record_oidc_authorization(self, ip_address: str) -> None:
        self.record_oidc_authorization_calls.append(ip_address)


class OidcProviderClientStub:

    def __init__(self) -> None:
        self.authorization_calls: list[dict] = []
        self.exchange_code_calls: list[dict] = []
        self.validate_id_token_calls: list[dict] = []
        self.claims = _claims()

    async def build_authorization_url(
        self,
        provider_id: str,
        state: str,
        nonce: str,
        code_challenge: str,
        *,
        prompt: str | None = None,
        max_age: int | None = None,
        login_hint: str | None = None,
    ) -> OidcAuthorizationUrl:
        self.authorization_calls.append({
            "provider_id": provider_id,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge,
            "prompt": prompt,
            "max_age": max_age,
            "login_hint": login_hint,
        })
        return OidcAuthorizationUrl(provider_id=provider_id, url=f"https://idp.example/{state}")

    async def exchange_code(
        self,
        provider_id: str,
        code: str,
        code_verifier: str,
    ) -> OidcTokenSetForValidation:
        self.exchange_code_calls.append({
            "provider_id": provider_id,
            "code": code,
            "code_verifier": code_verifier,
        })
        return OidcTokenSetForValidation(id_token="id-token-value")

    async def validate_id_token(
        self,
        provider_id: str,
        id_token: str,
        *,
        expected_nonce: str | None = None,
        expected_nonce_hash: str | None = None,
        require_auth_time: bool = False,
    ) -> OidcVerifiedClaims:
        self.validate_id_token_calls.append({
            "provider_id": provider_id,
            "id_token": id_token,
            "expected_nonce": expected_nonce,
            "expected_nonce_hash": expected_nonce_hash,
            "require_auth_time": require_auth_time,
        })
        if require_auth_time and self.claims.auth_time is None:
            raise OidcReauthAuthTimeRequiredError
        return self.claims


def _oidc_settings(
    *,
    trust_verified_email: bool = True,
    auto_provision: str = "enabled",
    link_mode: str = "auto",
    reauth_freshness_seconds: int = 300,
) -> OidcSettings:
    return OidcSettings(
        providers=(OidcProviderSettings(
            provider_id="google",
            display_name="Google",
            issuer="https://accounts.example.com",
            client_id="client-id",
            client_secret="client-secret",
            callback_path="/api/auth/oidc/google/callback",
            trust_verified_email=trust_verified_email,
            auto_provision=auto_provision,
            link_mode=link_mode,
        ), ),
        AUTH_OIDC_REDIRECT_BASE_URL="https://app.example.com",
        AUTH_OIDC_STATE_TTL_SECONDS=300,
        AUTH_OIDC_REAUTH_FRESHNESS_SECONDS=reauth_freshness_seconds,
    )


def _auth_context(email: str = "user@example.com") -> AuthenticatedSessionContext:
    now = utcnow()
    user = _user(email, password_hash=None)
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-hash",
        csrf_token_hash="csrf-hash",
        created_at=now,
        issued_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(minutes=10),
    )
    return AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset(),
        permissions=frozenset(),
    )


def _user(email: str = "user@example.com", *, password_hash: str | None = "hash") -> User:
    return User(email=email, password_hash=password_hash, is_active=True)


def _claims(
    *,
    subject: str = "subject-1",
    email: str | None = "user@example.com",
    email_verified: bool = True,
    auth_time: datetime | None = None,
) -> OidcVerifiedClaims:
    now = utcnow()
    return OidcVerifiedClaims(
        provider_id="google",
        issuer="https://accounts.example.com",
        audience="client-id",
        subject=subject,
        email=email,
        email_verified=email_verified,
        issued_at=now,
        expires_at=now + timedelta(minutes=5),
        auth_time=auth_time,
        claims_json={
            "iss": "https://accounts.example.com",
            "sub": subject,
            "email": email,
            "email_verified": email_verified,
        },
    )


def _identity(user: User, *, subject: str = "subject-1") -> AuthIdentity:
    return AuthIdentity(
        user_id=user.id,
        provider_id="google",
        provider_subject=subject,
        email=user.email.strip().lower(),
        email_verified=True,
        claims_json={"sub": subject},
    )


async def _started_login(
    usecase: OAuthOidcUsecase,
    repository: AuthRepositoryStub,
    provider_client: OidcProviderClientStub,
):
    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings",
        purpose="login",
        current_session=None,
        ip_address="127.0.0.1",
    )
    state = provider_client.authorization_calls[-1]["state"]
    created_state = repository.created_states[-1][0]
    return result, state, created_state


def _usecase(
    *,
    oidc_settings: OidcSettings | None = None,
    rate_limiter: RateLimiterStub | None = None,
) -> tuple[OAuthOidcUsecase, AuthRepositoryStub, RateLimiterStub, OidcProviderClientStub]:
    unit_of_work = UnitOfWorkStub()
    repository = AuthRepositoryStub(unit_of_work)
    rate_limiter = rate_limiter or RateLimiterStub()
    provider_client = OidcProviderClientStub()
    usecase = OAuthOidcUsecase(
        auth_repository=repository,
        authorization_repository=AuthorizationRepositoryStub(),
        unit_of_work=unit_of_work,
        auth_rate_limiter=rate_limiter,
        auth_settings=AuthSettings(_env_file=None),
        oidc_settings=oidc_settings or _oidc_settings(),
        oidc_provider_client=provider_client,
        logger=getLogger(__name__),
    )
    return usecase, repository, rate_limiter, provider_client


async def test_start_authorization_rejects_unconfigured_provider() -> None:
    usecase, repository, _, _ = _usecase(oidc_settings=OidcSettings())

    with pytest.raises(OidcProviderNotConfiguredError):
        await usecase.start_authorization(
            provider_id="google",
            redirect_path="/app",
            purpose="login",
            current_session=None,
            ip_address="127.0.0.1",
        )

    assert repository.created_states == []


async def test_start_authorization_rejects_rate_limited_ip_without_creating_state() -> None:
    rate_limiter = RateLimiterStub(allowed=False)
    usecase, repository, _, _ = _usecase(rate_limiter=rate_limiter)

    with pytest.raises(OidcAuthorizationRateLimitedError):
        await usecase.start_authorization(
            provider_id="google",
            redirect_path="/app",
            purpose="login",
            current_session=None,
            ip_address="127.0.0.1",
        )

    assert repository.created_states == []
    assert rate_limiter.record_oidc_authorization_calls == []


@pytest.mark.parametrize(
    ("redirect_path", "stored_redirect_path"),
    [
        ("/app/settings?tab=danger#delete", "/app/settings?tab=danger#delete"),
        ("https://evil.example/app", "/app"),
        ("app/settings", "/app"),
        ("/login?redirect=/app", "/app"),
        ("/app\u0000/settings", "/app"),
        (f"/app/{'x' * 2050}", "/app"),
    ],
)
async def test_start_authorization_creates_state_and_browser_binding_cookie(
    redirect_path: str,
    stored_redirect_path: str,
) -> None:
    usecase, repository, rate_limiter, provider_client = _usecase()

    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path=redirect_path,
        purpose="login",
        current_session=None,
        ip_address="127.0.0.1",
    )

    assert result.authorization_url.startswith("https://idp.example/")
    assert result.browser_binding_cookie_name.startswith("oidc_binding_")
    assert result.browser_binding_cookie_value
    assert result.browser_binding_cookie_max_age == 300
    assert rate_limiter.record_oidc_authorization_calls == ["127.0.0.1"]
    created_state = repository.created_states[0][0]
    _, created_in_transaction = repository.created_states[0]
    authorization_call = provider_client.authorization_calls[0]
    assert created_state.provider_id == "google"
    assert created_in_transaction is True
    assert created_state.purpose == "login"
    assert created_state.redirect_path == stored_redirect_path
    assert created_state.state_hash == hash_token(authorization_call["state"])
    assert created_state.browser_binding_hash == hash_token(result.browser_binding_cookie_value)
    assert created_state.nonce_hash == hash_token(authorization_call["nonce"])
    assert created_state.pkce_verifier
    assert created_state.expected_user_id is None
    assert created_state.expected_session_id is None
    assert authorization_call["prompt"] is None
    assert authorization_call["max_age"] is None


async def test_start_reauth_requires_current_session() -> None:
    usecase, _, _, _ = _usecase()

    with pytest.raises(OidcReauthAuthenticationRequiredError):
        await usecase.start_authorization(
            provider_id="google",
            redirect_path="/app/settings",
            purpose="account_deletion_reauth",
            current_session=None,
            ip_address="127.0.0.1",
        )


async def test_start_reauth_records_expected_session_and_forces_provider_login() -> None:
    auth_context = _auth_context("User@Example.com")
    usecase, repository, _, provider_client = _usecase()

    await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings",
        purpose="account_deletion_reauth",
        current_session=auth_context,
        ip_address="127.0.0.1",
    )

    created_state = repository.created_states[0][0]
    authorization_call = provider_client.authorization_calls[0]
    assert created_state.purpose == "account_deletion_reauth"
    assert created_state.expected_user_id == auth_context.user.id
    assert created_state.expected_session_id == auth_context.session.id
    assert created_state.login_hint == "user@example.com"
    assert authorization_call["prompt"] == "login"
    assert authorization_call["max_age"] == 0
    assert authorization_call["login_hint"] == "user@example.com"


async def test_start_authorization_uses_state_specific_binding_cookie_names() -> None:
    usecase, _, _, _ = _usecase()

    first = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app",
        purpose="login",
        current_session=None,
        ip_address="127.0.0.1",
    )
    second = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app",
        purpose="login",
        current_session=None,
        ip_address="127.0.0.1",
    )

    assert first.browser_binding_cookie_name != second.browser_binding_cookie_name
    assert first.browser_binding_cookie_value != second.browser_binding_cookie_value


async def test_complete_callback_rejects_url_state_mismatch_without_audit() -> None:
    usecase, repository, _, provider_client = _usecase()
    result, _, _ = await _started_login(usecase, repository, provider_client)

    with pytest.raises(OidcStateMismatchError):
        await usecase.complete_callback(
            provider_id="google",
            state="wrong-state",
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert provider_client.exchange_code_calls == []
    assert repository.audit_logs == []


async def test_complete_callback_rejects_missing_browser_binding_without_audit() -> None:
    usecase, repository, _, provider_client = _usecase()
    _, state, _ = await _started_login(usecase, repository, provider_client)

    with pytest.raises(OidcBrowserBindingMismatchError):
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=None,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert provider_client.exchange_code_calls == []
    assert repository.audit_logs == []


async def test_complete_callback_rejects_browser_binding_mismatch_without_audit() -> None:
    usecase, repository, _, provider_client = _usecase()
    _, state, _ = await _started_login(usecase, repository, provider_client)

    with pytest.raises(OidcBrowserBindingMismatchError):
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value="wrong-binding",
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert provider_client.exchange_code_calls == []
    assert repository.audit_logs == []


@pytest.mark.parametrize("state_mutation", ["expired", "consumed"])
async def test_complete_callback_rejects_expired_or_consumed_state_without_audit(
    state_mutation: str, ) -> None:
    usecase, repository, _, provider_client = _usecase()
    result, state, created_state = await _started_login(usecase, repository, provider_client)
    if state_mutation == "expired":
        created_state.expires_at = utcnow() - timedelta(seconds=1)
    else:
        created_state.consumed_at = utcnow()

    with pytest.raises(OidcStateMismatchError):
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert provider_client.exchange_code_calls == []
    assert repository.audit_logs == []


async def test_complete_callback_logs_in_existing_identity_user() -> None:
    usecase, repository, _, provider_client = _usecase()
    result, state, created_state = await _started_login(usecase, repository, provider_client)
    user = _user("linked@example.com", password_hash=None)
    identity = _identity(user)
    repository.users_by_id[user.id] = user
    repository.identities_by_subject[("google", "subject-1")] = identity

    callback = await usecase.complete_callback(
        provider_id="google",
        state=state,
        code="code-1",
        browser_binding_cookie_value=result.browser_binding_cookie_value,
        current_session=None,
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert callback.redirect_path == "/app/settings"
    assert callback.issued_session is not None
    assert callback.issued_session.user.id == user.id
    assert provider_client.exchange_code_calls == [{
        "provider_id": "google",
        "code": "code-1",
        "code_verifier": created_state.pkce_verifier,
    }]
    assert provider_client.validate_id_token_calls[0]["expected_nonce_hash"] == (
        created_state.nonce_hash)
    assert provider_client.validate_id_token_calls[0]["require_auth_time"] is False
    assert repository.recorded_oidc_logins[0][0:3] == (
        user.id,
        identity.id,
        callback.issued_session.session.id,
    )
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_LOGIN_SUCCESS]


async def test_complete_callback_rejects_existing_identity_for_inactive_user() -> None:
    usecase, repository, _, provider_client = _usecase()
    result, state, _ = await _started_login(usecase, repository, provider_client)
    user = _user("inactive@example.com", password_hash=None)
    user.is_active = False
    identity = _identity(user)
    repository.users_by_id[user.id] = user
    repository.identities_by_subject[("google", "subject-1")] = identity

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcIdentityUnavailableError)
    assert repository.created_sessions == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_LOGIN_FAILED]


async def test_complete_callback_auto_links_verified_email_user() -> None:
    usecase, repository, _, provider_client = _usecase()
    result, state, _ = await _started_login(usecase, repository, provider_client)
    user = _user("User@Example.com", password_hash="hash")
    repository.users_by_id[user.id] = user
    repository.users_by_email["user@example.com"] = user

    callback = await usecase.complete_callback(
        provider_id="google",
        state=state,
        code="code-1",
        browser_binding_cookie_value=result.browser_binding_cookie_value,
        current_session=None,
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    created_identity = repository.created_identities[0][0]
    assert created_identity.user_id == user.id
    assert created_identity.provider_subject == "subject-1"
    assert callback.issued_session is not None
    assert [audit.event_type for audit, _ in repository.audit_logs] == [
        AuthEventType.OIDC_IDENTITY_LINKED,
        AuthEventType.OIDC_LOGIN_SUCCESS,
    ]


async def test_complete_callback_auto_provisions_verified_email_user() -> None:
    usecase, repository, _, provider_client = _usecase()
    result, state, _ = await _started_login(usecase, repository, provider_client)

    callback = await usecase.complete_callback(
        provider_id="google",
        state=state,
        code="code-1",
        browser_binding_cookie_value=result.browser_binding_cookie_value,
        current_session=None,
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert callback.issued_session is not None
    assert repository.created_users[0][0:2] == ("user@example.com", None)
    assert repository.created_identities[0][0].user_id == callback.issued_session.user.id
    assert [audit.event_type for audit, _ in repository.audit_logs] == [
        AuthEventType.OIDC_USER_PROVISIONED,
        AuthEventType.OIDC_LOGIN_SUCCESS,
    ]


async def test_complete_callback_rejects_new_user_when_auto_provision_is_link_only() -> None:
    usecase, repository, _, provider_client = _usecase(oidc_settings=_oidc_settings(
        auto_provision="link-only"))
    result, state, _ = await _started_login(usecase, repository, provider_client)

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcProvisioningDisabledError)
    assert repository.created_users == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_LOGIN_FAILED]
    assert "code-1" not in str(repository.audit_logs[0][0].detail_json)
    assert "id-token-value" not in str(repository.audit_logs[0][0].detail_json)


async def test_complete_callback_maps_duplicate_email_race_to_identity_unavailable() -> None:
    usecase, repository, _, provider_client = _usecase()
    repository.create_user_error = EmailAlreadyRegisteredError
    result, state, _ = await _started_login(usecase, repository, provider_client)

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcIdentityUnavailableError)
    assert repository.created_identities == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_LOGIN_FAILED]
    assert repository.audit_logs[0][0].detail_json["error"] == "OidcIdentityUnavailableError"


@pytest.mark.parametrize(
    ("trust_verified_email", "email_verified"),
    [(False, True), (True, False)],
)
async def test_complete_callback_rejects_untrusted_or_unverified_email(
    trust_verified_email: bool,
    email_verified: bool,
) -> None:
    usecase, repository, _, provider_client = _usecase(oidc_settings=_oidc_settings(
        trust_verified_email=trust_verified_email))
    provider_client.claims = _claims(email_verified=email_verified)
    result, state, _ = await _started_login(usecase, repository, provider_client)

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcEmailNotVerifiedError)
    assert repository.created_users == []
    assert repository.created_identities == []


@pytest.mark.parametrize(
    ("link_mode", "expected_error"),
    [("manual", OidcIdentityLinkRequiredError), ("disabled", OidcIdentityLinkDisabledError)],
)
async def test_complete_callback_rejects_non_auto_link_modes(
    link_mode: str,
    expected_error: type[Exception],
) -> None:
    usecase, repository, _, provider_client = _usecase(oidc_settings=_oidc_settings(
        link_mode=link_mode))
    result, state, _ = await _started_login(usecase, repository, provider_client)
    user = _user("user@example.com", password_hash="hash")
    repository.users_by_id[user.id] = user
    repository.users_by_email["user@example.com"] = user

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, expected_error)
    assert repository.created_identities == []


async def test_complete_callback_does_not_link_deleted_or_inactive_email_user() -> None:
    usecase, repository, _, provider_client = _usecase(oidc_settings=_oidc_settings(
        auto_provision="link-only"))
    result, state, _ = await _started_login(usecase, repository, provider_client)
    user = _user("user@example.com", password_hash="hash")
    user.is_active = False
    repository.users_by_id[user.id] = user
    repository.users_by_email["user@example.com"] = user

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcIdentityUnavailableError)
    assert repository.created_identities == []


async def test_complete_callback_rejects_inactive_email_collision_without_auto_provision() -> None:
    usecase, repository, _, provider_client = _usecase()
    result, state, _ = await _started_login(usecase, repository, provider_client)
    user = _user("user@example.com", password_hash="hash")
    user.is_active = False
    repository.users_by_id[user.id] = user
    repository.users_by_email["user@example.com"] = user

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=None,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcIdentityUnavailableError)
    assert repository.created_users == []
    assert repository.created_identities == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_LOGIN_FAILED]


async def test_complete_callback_reauth_updates_current_session_freshness() -> None:
    current = _auth_context("user@example.com")
    usecase, repository, _, provider_client = _usecase()
    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings",
        purpose="account_deletion_reauth",
        current_session=current,
        ip_address="127.0.0.1",
    )
    state = provider_client.authorization_calls[-1]["state"]
    auth_time = utcnow()
    provider_client.claims = _claims(auth_time=auth_time)
    identity = _identity(current.user)
    repository.users_by_id[current.user.id] = current.user
    repository.identities_by_subject[("google", "subject-1")] = identity

    callback = await usecase.complete_callback(
        provider_id="google",
        state=state,
        code="code-1",
        browser_binding_cookie_value=result.browser_binding_cookie_value,
        current_session=current,
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert callback.issued_session is None
    assert callback.reauthenticated_context == current
    assert repository.created_sessions == []
    assert repository.recorded_oidc_reauths[0][0:2] == (current.session.id, auth_time)
    assert provider_client.validate_id_token_calls[0]["require_auth_time"] is True
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_REAUTH_SUCCESS]


async def test_complete_callback_reauth_rejects_different_provider_account() -> None:
    current = _auth_context("user@example.com")
    usecase, repository, _, provider_client = _usecase()
    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings",
        purpose="account_deletion_reauth",
        current_session=current,
        ip_address="127.0.0.1",
    )
    state = provider_client.authorization_calls[-1]["state"]
    provider_client.claims = _claims(auth_time=utcnow())

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=current,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcReauthSubjectMismatchError)
    assert repository.created_sessions == []
    assert repository.recorded_oidc_reauths == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_REAUTH_FAILED]


async def test_complete_callback_reauth_rejects_expected_session_mismatch() -> None:
    current = _auth_context("user@example.com")
    usecase, repository, _, provider_client = _usecase()
    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings",
        purpose="account_deletion_reauth",
        current_session=current,
        ip_address="127.0.0.1",
    )
    state = provider_client.authorization_calls[-1]["state"]
    repository.created_states[-1][0].expected_session_id = AuthSession(
        user_id=current.user.id,
        session_token_hash="other",
        csrf_token_hash="other",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=5),
    ).id
    provider_client.claims = _claims(auth_time=utcnow())

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=current,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcReauthSubjectMismatchError)
    assert repository.created_sessions == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_REAUTH_FAILED]


async def test_complete_callback_reauth_rejects_missing_auth_time() -> None:
    current = _auth_context("user@example.com")
    usecase, repository, _, provider_client = _usecase()
    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings",
        purpose="account_deletion_reauth",
        current_session=current,
        ip_address="127.0.0.1",
    )
    state = provider_client.authorization_calls[-1]["state"]
    identity = _identity(current.user)
    repository.identities_by_subject[("google", "subject-1")] = identity

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=current,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcReauthAuthTimeRequiredError)
    assert repository.recorded_oidc_reauths == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_REAUTH_FAILED]


async def test_complete_callback_reauth_rejects_stale_auth_time() -> None:
    current = _auth_context("user@example.com")
    usecase, repository, _, provider_client = _usecase(oidc_settings=_oidc_settings(
        reauth_freshness_seconds=60))
    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings",
        purpose="account_deletion_reauth",
        current_session=current,
        ip_address="127.0.0.1",
    )
    state = provider_client.authorization_calls[-1]["state"]
    provider_client.claims = _claims(auth_time=utcnow() - timedelta(minutes=5))
    identity = _identity(current.user)
    repository.identities_by_subject[("google", "subject-1")] = identity

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_callback(
            provider_id="google",
            state=state,
            code="code-1",
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            current_session=current,
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcReauthStaleError)
    assert repository.recorded_oidc_reauths == []
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_REAUTH_FAILED]


async def test_complete_error_callback_reauth_preserves_redirect_context_and_audits_failure(
) -> None:
    current = _auth_context("user@example.com")
    usecase, repository, _, provider_client = _usecase()
    result = await usecase.start_authorization(
        provider_id="google",
        redirect_path="/app/settings?tab=danger#delete",
        purpose="account_deletion_reauth",
        current_session=current,
        ip_address="127.0.0.1",
    )
    raw_state = provider_client.authorization_calls[-1]["state"]

    with pytest.raises(OidcCallbackFlowError) as captured_error:
        await usecase.complete_error_callback(
            provider_id="google",
            state=raw_state,
            browser_binding_cookie_value=result.browser_binding_cookie_value,
            provider_error=OidcProviderAccessDeniedError("access_denied"),
            current_session=current,
            ip_address="127.0.0.1",
            user_agent="test-agent",
        )

    assert isinstance(captured_error.value.error, OidcProviderAccessDeniedError)
    assert captured_error.value.purpose == "account_deletion_reauth"
    assert captured_error.value.redirect_path == "/app/settings?tab=danger#delete"
    assert repository.consumed_states[-1][2] is True
    assert [audit.event_type
            for audit, _ in repository.audit_logs] == [AuthEventType.OIDC_REAUTH_FAILED]


async def test_complete_callback_replaces_existing_session_for_login() -> None:
    usecase, repository, _, provider_client = _usecase()
    result, state, _ = await _started_login(usecase, repository, provider_client)
    user = _user("linked@example.com", password_hash=None)
    identity = _identity(user)
    existing_session = AuthSession(
        user_id=user.id,
        session_token_hash=hash_token("old-session-token"),
        csrf_token_hash="csrf-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository.users_by_id[user.id] = user
    repository.identities_by_subject[("google", "subject-1")] = identity
    repository.created_sessions.append((existing_session, False))

    callback = await usecase.complete_callback(
        provider_id="google",
        state=state,
        code="code-1",
        browser_binding_cookie_value=result.browser_binding_cookie_value,
        current_session=None,
        current_session_token="old-session-token",
        ip_address="127.0.0.1",
        user_agent="test-agent",
    )

    assert callback.issued_session is not None
    assert repository.revoked_session_ids == [existing_session.id]
    assert callback.issued_session.session.id != existing_session.id
