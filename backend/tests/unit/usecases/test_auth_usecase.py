from contextlib import asynccontextmanager
from datetime import timedelta
from logging import getLogger

import pytest

from app.config.auth import AuthSettings
from app.libraries.clock import utcnow
from app.libraries.password_hasher import hash_password, verify_password
from app.libraries.session_tokens import hash_token
from app.models.auth_context import AuthenticatedSessionContext
from app.models.auth_csrf import SessionCsrfStatus
from app.models.auth_errors import InvalidCredentialsError, RateLimitExceededError
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.language import DEFAULT_LANGUAGE_CODE, LanguageCode
from app.models.user import AuthUserUpdateChanges, User
from app.usecases.auth_usecase import DUMMY_PASSWORD_HASH, AuthUsecase


class AllowingRateLimiter:

    def __init__(self) -> None:
        self.failure_records: list[tuple[str, str, bool]] = []
        self.success_records: list[tuple[str, str]] = []
        self.registration_records: list[str] = []
        self.allowed = True
        self.registration_allowed = True

    async def is_allowed(self, _ip_address: str, _normalized_email: str) -> bool:
        return self.allowed

    async def record_failure(
        self,
        ip_address: str,
        normalized_email: str,
        include_email_bucket: bool = True,
    ) -> None:
        self.failure_records.append((ip_address, normalized_email, include_email_bucket))

    async def record_success(self, ip_address: str, normalized_email: str) -> None:
        self.success_records.append((ip_address, normalized_email))

    async def is_registration_allowed(self, _ip_address: str) -> bool:
        return self.registration_allowed

    async def record_registration(self, ip_address: str) -> None:
        self.registration_records.append(ip_address)

    async def aclose(self) -> None:
        return None

    def reset_for_tests(self) -> None:
        self.failure_records.clear()
        self.success_records.clear()
        self.registration_records.clear()


class PasswordHashExecutorStub:

    def __init__(
        self,
        verify_result: bool = True,
        hash_result: str = "hashed-password",
    ) -> None:
        self.verify_result = verify_result
        self.hash_result = hash_result
        self.hash_calls: list[str] = []
        self.verify_calls: list[tuple[str, str]] = []

    async def hash(self, raw_password: str) -> str:
        self.hash_calls.append(raw_password)
        return self.hash_result

    async def verify(self, raw_password: str, hashed_password: str) -> bool:
        self.verify_calls.append((raw_password, hashed_password))
        return self.verify_result


class UnitOfWorkStub:

    def __init__(self) -> None:
        self.in_transaction = False
        self.transaction_entries = 0

    @asynccontextmanager
    async def transaction(self):
        self.transaction_entries += 1
        self.in_transaction = True
        try:
            yield
        finally:
            self.in_transaction = False


class AuthRepositoryStub:

    def __init__(self, user: User | None):
        self.user = user
        self.created_sessions: list[AuthSession] = []
        self.audit_logs = []
        self.recorded_login_user_ids = []
        self.created_users: list[User] = []
        self.updated_language_records = []
        self.revoked_session_ids = []
        self.revoked_user_session_records = []
        self.rejected_session_replays = []

    async def create_user(
        self,
        email: str,
        password_hash: str | None,
        language_code: LanguageCode = DEFAULT_LANGUAGE_CODE,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            is_active=True,
            language_code=language_code,
        )
        self.user = user
        self.created_users.append(user)
        return user

    async def update_user_language(self, user_id, language_code, modified_at):
        self.updated_language_records.append((user_id, language_code, modified_at))
        if self.user is None or self.user.id != user_id or self.user.deleted_at is not None:
            from app.models.auth_errors import UserNotFoundError

            raise UserNotFoundError(user_id)
        self.user.language_code = language_code
        self.user.modified_at = modified_at
        return self.user

    async def find_user_by_email(self, _normalized_email: str) -> User | None:
        return self.user

    async def find_user_by_id_for_authentication(self, _user_id):
        return self.user

    async def create_session(self, **kwargs) -> AuthSession:
        auth_session = AuthSession(**kwargs)
        self.created_sessions.append(auth_session)
        return auth_session

    async def find_active_session_by_token_hash(self, _token_hash: str):
        return None

    async def find_session_by_token_hash(self, _token_hash: str):
        return None

    async def revoke_session(self, _session_id) -> None:
        self.revoked_session_ids.append(_session_id)

    async def revoke_sessions_for_user(self, user_id, revoked_at):
        self.revoked_user_session_records.append((user_id, revoked_at))
        return 1

    async def touch_session(self, _session_id, _last_seen_at, _expires_at):
        raise NotImplementedError

    async def record_user_login(self, user_id, login_at):
        self.recorded_login_user_ids.append(user_id)
        self.user.last_logged_in_at = login_at
        self.user.updated_at = login_at
        return self.user

    async def create_audit_log(self, audit_log) -> None:
        self.audit_logs.append(audit_log)

    async def record_rejected_session_replay(
        self,
        auth_session,
        ip_address,
        user_agent,
        replayed_at,
        window_seconds,
    ) -> None:
        self.rejected_session_replays.append(
            (auth_session, ip_address, user_agent, replayed_at, window_seconds))


class AuthorizationRepositoryStub:

    def __init__(self) -> None:
        self.role_codes = ("admin", )

    async def get_user_role_codes(self, _user_id):
        return self.role_codes


class CsrfSessionRepository(AuthRepositoryStub):

    def __init__(self, active_session: AuthSession | None) -> None:
        super().__init__(user=None)
        self.active_session = active_session

    async def find_active_session_by_token_hash(self, _token_hash: str):
        return self.active_session


class KnownRejectedSessionRepository(CsrfSessionRepository):

    def __init__(self, rejected_session: AuthSession) -> None:
        super().__init__(active_session=None)
        self.rejected_session = rejected_session

    async def find_session_by_token_hash(self, _token_hash: str):
        return self.rejected_session


def test_dummy_password_hash_is_valid_argon2_with_current_work_factor():
    current_hash = hash_password("Password123!")

    assert DUMMY_PASSWORD_HASH.startswith("$argon2id$")
    assert verify_password("not-the-dummy-password", DUMMY_PASSWORD_HASH) is False
    assert DUMMY_PASSWORD_HASH.split("$")[3] == current_hash.split("$")[3]


@pytest.mark.asyncio
async def test_validate_session_csrf_returns_no_session_for_unknown_session():
    repository = CsrfSessionRepository(active_session=None)

    status = await _usecase(repository).validate_session_csrf(
        session_token="missing-session",
        csrf_token="csrf-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert status is SessionCsrfStatus.NO_SESSION
    assert repository.audit_logs == []
    assert repository.rejected_session_replays == []


@pytest.mark.asyncio
async def test_validate_session_csrf_records_bounded_replay_for_known_rejected_session():
    rejected_session = AuthSession(
        user_id=User(email="rejected-csrf@example.com").id,
        session_token_hash=hash_token("session-token"),
        csrf_token_hash=hash_token("csrf-token"),
        created_at=utcnow() - timedelta(minutes=20),
        issued_at=utcnow() - timedelta(minutes=20),
        last_seen_at=utcnow() - timedelta(minutes=20),
        expires_at=utcnow() - timedelta(minutes=10),
    )
    repository = KnownRejectedSessionRepository(rejected_session)

    status = await _usecase(repository).validate_session_csrf(
        session_token="session-token",
        csrf_token="csrf-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert status is SessionCsrfStatus.NO_SESSION
    assert repository.audit_logs == []
    assert len(repository.rejected_session_replays) == 1
    replay_session, ip_address, user_agent, _replayed_at, window_seconds = (
        repository.rejected_session_replays[0])
    assert replay_session == rejected_session
    assert ip_address == "127.0.0.1"
    assert user_agent == "pytest"
    assert window_seconds == 300


@pytest.mark.asyncio
async def test_validate_session_csrf_returns_valid_for_matching_token():
    active_session = AuthSession(
        user_id=User(email="active@example.com").id,
        session_token_hash=hash_token("session-token"),
        csrf_token_hash=hash_token("csrf-token"),
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )

    status = await _usecase(CsrfSessionRepository(active_session=active_session)
                            ).validate_session_csrf(
                                session_token="session-token",
                                csrf_token="csrf-token",
                                ip_address="127.0.0.1",
                                user_agent="pytest",
                            )

    assert status is SessionCsrfStatus.VALID


@pytest.mark.asyncio
async def test_validate_session_csrf_returns_mismatch_for_different_token():
    active_session = AuthSession(
        user_id=User(email="active@example.com").id,
        session_token_hash=hash_token("session-token"),
        csrf_token_hash=hash_token("csrf-token"),
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )

    status = await _usecase(CsrfSessionRepository(active_session=active_session)
                            ).validate_session_csrf(
                                session_token="session-token",
                                csrf_token="different-token",
                                ip_address="127.0.0.1",
                                user_agent="pytest",
                            )

    assert status is SessionCsrfStatus.MISMATCH


def _usecase(
    repository: AuthRepositoryStub,
    unit_of_work: UnitOfWorkStub | None = None,
    password_hash_executor: PasswordHashExecutorStub | None = None,
    rate_limiter: AllowingRateLimiter | None = None,
    auth_settings: AuthSettings | None = None,
) -> AuthUsecase:
    return AuthUsecase(
        auth_repository=repository,
        authorization_repository=AuthorizationRepositoryStub(),
        unit_of_work=unit_of_work or UnitOfWorkStub(),
        auth_rate_limiter=rate_limiter or AllowingRateLimiter(),
        auth_settings=auth_settings or AuthSettings(_env_file=None),
        password_hash_executor=password_hash_executor or PasswordHashExecutorStub(),
        logger=getLogger(__name__),
    )


@pytest.mark.asyncio
async def test_login_verifies_dummy_password_hash_when_user_is_missing():
    password_hash_executor = PasswordHashExecutorStub(verify_result=False)
    rate_limiter = AllowingRateLimiter()

    with pytest.raises(InvalidCredentialsError):
        await _usecase(
            AuthRepositoryStub(user=None),
            password_hash_executor=password_hash_executor,
            rate_limiter=rate_limiter,
        ).login(
            email="missing@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert password_hash_executor.verify_calls == [("Password123!", DUMMY_PASSWORD_HASH)]
    assert rate_limiter.failure_records == [("127.0.0.1", "missing@example.com", True)]


@pytest.mark.asyncio
async def test_login_records_failure_before_audit_insert():
    rate_limiter = AllowingRateLimiter()

    class FailingAuditRepository(AuthRepositoryStub):

        async def create_audit_log(self, audit_log) -> None:
            raise RuntimeError("audit failed")

    with pytest.raises(RuntimeError, match="audit failed"):
        await _usecase(
            FailingAuditRepository(user=None),
            password_hash_executor=PasswordHashExecutorStub(verify_result=False),
            rate_limiter=rate_limiter,
        ).login(
            email="missing@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert rate_limiter.failure_records == [("127.0.0.1", "missing@example.com", True)]


@pytest.mark.asyncio
async def test_login_rate_limit_does_not_write_audit_log():
    rate_limiter = AllowingRateLimiter()
    rate_limiter.allowed = False
    repository = AuthRepositoryStub(user=None)

    with pytest.raises(RateLimitExceededError) as error:
        await _usecase(
            repository,
            rate_limiter=rate_limiter,
        ).login(
            email="blocked@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert error.value.retry_after_seconds == 900
    assert repository.audit_logs == []
    assert rate_limiter.failure_records == []


@pytest.mark.asyncio
async def test_login_rejects_inactive_user_without_creating_session():
    repository = AuthRepositoryStub(
        user=User(email="inactive@example.com", password_hash="hashed", is_active=False))

    with pytest.raises(InvalidCredentialsError):
        await _usecase(repository).login(
            email="inactive@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.created_sessions == []


@pytest.mark.asyncio
async def test_login_rejects_user_without_password_hash_with_dummy_verify():
    password_hash_executor = PasswordHashExecutorStub(verify_result=True)
    repository = AuthRepositoryStub(
        user=User(email="oauth@example.com", password_hash=None, is_active=True))

    with pytest.raises(InvalidCredentialsError):
        await _usecase(
            repository,
            password_hash_executor=password_hash_executor,
        ).login(
            email="oauth@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert password_hash_executor.verify_calls == [("Password123!", DUMMY_PASSWORD_HASH)]
    assert repository.created_sessions == []


@pytest.mark.asyncio
async def test_login_records_last_login_before_creating_session(monkeypatch):
    user = User(email="active@example.com", password_hash="hashed", is_active=True)
    repository = AuthRepositoryStub(user=user)

    rate_limiter = AllowingRateLimiter()
    issued_session = await _usecase(repository, rate_limiter=rate_limiter).login(
        email="active@example.com",
        password="Password123!",
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert repository.recorded_login_user_ids == [user.id]
    assert rate_limiter.success_records == [("127.0.0.1", "active@example.com")]
    assert issued_session.user.last_logged_in_at is not None
    assert issued_session.user.updated_at == issued_session.user.last_logged_in_at


@pytest.mark.asyncio
async def test_register_records_last_login_for_issued_session():
    repository = AuthRepositoryStub(user=None)
    password_hash_executor = PasswordHashExecutorStub(hash_result="executor-hash")
    rate_limiter = AllowingRateLimiter()

    issued_session = await _usecase(
        repository,
        password_hash_executor=password_hash_executor,
        rate_limiter=rate_limiter,
    ).register(
        email="new@example.com",
        password="Password123!",
        language_code="ja",
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert repository.created_users == [issued_session.user]
    assert repository.created_users[0].password_hash == "executor-hash"
    assert password_hash_executor.hash_calls == ["Password123!"]
    assert rate_limiter.failure_records == []
    assert rate_limiter.registration_records == ["127.0.0.1"]
    assert repository.recorded_login_user_ids == [issued_session.user.id]
    assert issued_session.user.last_logged_in_at is not None


@pytest.mark.asyncio
async def test_register_passes_language_code_to_created_user():
    repository = AuthRepositoryStub(user=None)

    issued_session = await _usecase(repository).register(
        email="new@example.com",
        password="Password123!",
        language_code="en",
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert issued_session.user.language_code == "en"


@pytest.mark.asyncio
async def test_register_checks_registration_rate_limit_bucket():
    rate_limiter = AllowingRateLimiter()
    rate_limiter.registration_allowed = False
    repository = AuthRepositoryStub(user=None)

    with pytest.raises(RateLimitExceededError) as error:
        await _usecase(
            repository,
            rate_limiter=rate_limiter,
        ).register(
            email="new@example.com",
            password="Password123!",
            language_code="ja",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert error.value.retry_after_seconds == 3600
    assert repository.audit_logs == []
    assert rate_limiter.failure_records == []
    assert rate_limiter.registration_records == []


@pytest.mark.asyncio
async def test_register_login_rate_limit_does_not_write_audit_log():
    rate_limiter = AllowingRateLimiter()
    rate_limiter.allowed = False
    repository = AuthRepositoryStub(user=None)

    with pytest.raises(RateLimitExceededError) as error:
        await _usecase(
            repository,
            rate_limiter=rate_limiter,
        ).register(
            email="blocked@example.com",
            password="Password123!",
            language_code="ja",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert error.value.retry_after_seconds == 900
    assert repository.audit_logs == []
    assert rate_limiter.failure_records == []
    assert rate_limiter.registration_records == []


@pytest.mark.asyncio
async def test_register_duplicate_records_failure_before_audit_insert():
    rate_limiter = AllowingRateLimiter()

    class FailingAuditRepository(AuthRepositoryStub):

        async def create_audit_log(self, audit_log) -> None:
            raise RuntimeError("audit failed")

    with pytest.raises(RuntimeError, match="audit failed"):
        await _usecase(
            FailingAuditRepository(user=User(
                email="existing@example.com",
                password_hash="hashed",
                is_active=True,
            )),
            rate_limiter=rate_limiter,
        ).register(
            email="existing@example.com",
            password="Password123!",
            language_code="ja",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert rate_limiter.failure_records == [("127.0.0.1", "existing@example.com", False)]


@pytest.mark.asyncio
async def test_update_current_user_updates_language_and_preserves_context():
    user = User(email="settings@example.com", password_hash="hash", language_code="ja")
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    auth_context = AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset({"admin"}),
        permissions=frozenset({"admin:access"}),
    )
    repository = AuthRepositoryStub(user=user)

    updated_context = await _usecase(repository).update_current_user(
        auth_context,
        AuthUserUpdateChanges(language_code="en", fields_set=frozenset({"language_code"})),
    )

    assert updated_context.user.language_code == "en"
    assert updated_context.session is session
    assert updated_context.roles == frozenset({"admin"})
    assert updated_context.permissions == frozenset({"admin:access"})
    assert repository.updated_language_records[0][0] == user.id


@pytest.mark.asyncio
async def test_update_current_user_empty_body_is_no_op():
    user = User(email="settings@example.com", password_hash="hash", language_code="ja")
    session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    auth_context = AuthenticatedSessionContext(
        user=user,
        session=session,
        roles=frozenset(),
        permissions=frozenset(),
    )
    repository = AuthRepositoryStub(user=user)

    updated_context = await _usecase(repository).update_current_user(
        auth_context,
        AuthUserUpdateChanges(fields_set=frozenset()),
    )

    assert updated_context is auth_context
    assert repository.updated_language_records == []


class TransactionRecordingRepository(AuthRepositoryStub):

    def __init__(
        self,
        unit_of_work: UnitOfWorkStub,
        user: User | None,
        active_session: AuthSession | None,
    ) -> None:
        super().__init__(user=user)
        self._unit_of_work = unit_of_work
        self.active_session = active_session
        self.operations: list[tuple[str, bool]] = []

    async def find_active_session_by_token_hash(self, _token_hash: str):
        self.operations.append(("find_active_session", self._unit_of_work.in_transaction))
        return self.active_session

    async def find_user_by_id_for_authentication(self, _user_id):
        self.operations.append(
            ("find_user_by_id_for_authentication", self._unit_of_work.in_transaction))
        return self.user

    async def find_session_by_token_hash(self, _token_hash: str):
        self.operations.append(("find_session_by_token_hash", self._unit_of_work.in_transaction))
        return None

    async def touch_session(self, _session_id, last_seen_at, expires_at):
        self.operations.append(("touch_session", self._unit_of_work.in_transaction))
        self.active_session.last_seen_at = last_seen_at
        self.active_session.expires_at = expires_at
        return self.active_session


@pytest.mark.asyncio
async def test_authenticate_session_uses_one_unit_of_work_transaction():
    unit_of_work = UnitOfWorkStub()
    user = User(
        email="active@example.com",
        password_hash="hashed",
        is_active=True,
    )
    active_session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow() - timedelta(minutes=10),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )

    auth_context = await _usecase(repository, unit_of_work).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert auth_context is not None
    assert repository.revoked_user_session_records == []
    assert repository.operations == [
        ("find_active_session", True),
        ("find_user_by_id_for_authentication", True),
        ("touch_session", True),
    ]

    missing_token_repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )
    missing_token_context = await _usecase(
        missing_token_repository,
        unit_of_work,
    ).authenticate_session(
        session_token=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert missing_token_context is None
    assert missing_token_repository.operations == []

    rejected_repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=None,
    )
    rejected_context = await _usecase(
        rejected_repository,
        unit_of_work,
    ).authenticate_session(
        session_token="unknown-session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert rejected_context is None
    assert rejected_repository.operations == [
        ("find_active_session", True),
        ("find_session_by_token_hash", True),
    ]


@pytest.mark.asyncio
async def test_authenticate_session_records_bounded_replay_for_known_rejected_session():
    unit_of_work = UnitOfWorkStub()
    user = User(email="rejected-auth@example.com", password_hash="hashed", is_active=True)
    rejected_session = AuthSession(
        user_id=user.id,
        session_token_hash=hash_token("session-token"),
        csrf_token_hash=hash_token("csrf-token"),
        created_at=utcnow() - timedelta(minutes=20),
        issued_at=utcnow() - timedelta(minutes=20),
        last_seen_at=utcnow() - timedelta(minutes=20),
        expires_at=utcnow() - timedelta(minutes=10),
    )
    repository = KnownRejectedSessionRepository(rejected_session)

    auth_context = await _usecase(repository, unit_of_work).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert auth_context is None
    assert repository.audit_logs == []
    assert len(repository.rejected_session_replays) == 1
    replay_session, ip_address, user_agent, _replayed_at, window_seconds = (
        repository.rejected_session_replays[0])
    assert replay_session == rejected_session
    assert ip_address == "127.0.0.1"
    assert user_agent == "pytest"
    assert window_seconds == 300


@pytest.mark.asyncio
async def test_authenticate_session_skips_touch_inside_interval():
    unit_of_work = UnitOfWorkStub()
    user = User(email="active@example.com", password_hash="hashed", is_active=True)
    active_session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )

    auth_context = await _usecase(repository, unit_of_work).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert auth_context is not None
    assert repository.operations == [
        ("find_active_session", True),
        ("find_user_by_id_for_authentication", True),
    ]


@pytest.mark.asyncio
async def test_authenticate_session_revokes_deleted_user_session_and_audits():
    unit_of_work = UnitOfWorkStub()
    user = User(email="deleted@example.com", password_hash="hashed", is_active=True)
    user.deleted_at = utcnow()
    active_session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )

    auth_context = await _usecase(repository, unit_of_work).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert auth_context is None
    assert repository.revoked_session_ids == []
    assert len(repository.revoked_user_session_records) == 1
    revoked_user_id, revoked_at = repository.revoked_user_session_records[0]
    assert revoked_user_id == user.id
    assert revoked_at is not None
    assert repository.audit_logs[-1].event_type == AuthEventType.SESSION_REVOKED_DELETED_USER
    assert repository.audit_logs[-1].session_id == active_session.id


@pytest.mark.asyncio
async def test_authenticate_session_revokes_inactive_user_session_and_audits():
    unit_of_work = UnitOfWorkStub()
    user = User(email="inactive@example.com", password_hash="hashed", is_active=False)
    active_session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )

    auth_context = await _usecase(repository, unit_of_work).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert auth_context is None
    assert repository.revoked_session_ids == []
    assert len(repository.revoked_user_session_records) == 1
    revoked_user_id, revoked_at = repository.revoked_user_session_records[0]
    assert revoked_user_id == user.id
    assert revoked_at is not None
    assert repository.audit_logs[-1].event_type == AuthEventType.SESSION_REVOKED_INACTIVE_USER
    assert repository.audit_logs[-1].session_id == active_session.id


@pytest.mark.asyncio
async def test_authenticate_session_rejects_missing_user_without_deleted_or_inactive_event():
    unit_of_work = UnitOfWorkStub()
    active_session = AuthSession(
        user_id=User(email="missing@example.com").id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=None,
        active_session=active_session,
    )

    auth_context = await _usecase(repository, unit_of_work).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert auth_context is None
    assert repository.revoked_session_ids == [active_session.id]
    assert repository.revoked_user_session_records == []
    assert repository.audit_logs[-1].event_type == AuthEventType.SESSION_REJECTED


@pytest.mark.asyncio
async def test_authenticate_session_touch_interval_zero_touches_every_time():
    unit_of_work = UnitOfWorkStub()
    user = User(email="active@example.com", password_hash="hashed", is_active=True)
    active_session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=utcnow(),
        issued_at=utcnow(),
        last_seen_at=utcnow(),
        expires_at=utcnow() + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )

    await _usecase(
        repository,
        unit_of_work,
        auth_settings=AuthSettings(_env_file=None, AUTH_SESSION_TOUCH_INTERVAL_SECONDS=0),
    ).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert ("touch_session", True) in repository.operations


@pytest.mark.asyncio
async def test_authenticate_session_refreshes_expiry_from_issued_at_not_created_at(monkeypatch, ):
    unit_of_work = UnitOfWorkStub()
    fixed_now = utcnow()
    monkeypatch.setattr("app.usecases.auth_usecase.utcnow", lambda: fixed_now)
    user = User(
        email="active@example.com",
        password_hash="hashed",
        is_active=True,
    )
    active_session = AuthSession(
        user_id=user.id,
        session_token_hash="session-token-hash",
        csrf_token_hash="csrf-token-hash",
        created_at=fixed_now - timedelta(days=10),
        issued_at=fixed_now - timedelta(minutes=30),
        last_seen_at=fixed_now - timedelta(minutes=10),
        expires_at=fixed_now + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )

    await _usecase(
        repository,
        unit_of_work,
        auth_settings=AuthSettings(
            _env_file=None,
            AUTH_SESSION_TOUCH_INTERVAL_SECONDS=0,
            AUTH_SESSION_ABSOLUTE_TTL_SECONDS=3600,
            AUTH_SESSION_IDLE_TTL_SECONDS=86400,
        ),
    ).authenticate_session(
        session_token="session-token",
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert repository.active_session.expires_at == fixed_now + timedelta(minutes=30)
