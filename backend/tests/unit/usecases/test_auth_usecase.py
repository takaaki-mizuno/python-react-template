from contextlib import asynccontextmanager
from datetime import timedelta
from logging import getLogger

import pytest

from app.config.auth import AuthSettings
from app.libraries.password_hasher import hash_password, verify_password
from app.models.auth_errors import InvalidCredentialsError
from app.models.auth_session import AuthSession
from app.models.user import User
from app.usecases import auth_usecase as auth_usecase_module
from app.usecases.auth_usecase import DUMMY_PASSWORD_HASH, AuthUsecase


class AllowingRateLimiter:

    def allow(self, _ip_address: str, _normalized_email: str) -> bool:
        return True


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

    async def create_user(self, email: str, password_hash: str) -> User:
        user = User(email=email, password_hash=password_hash, is_active=True)
        self.user = user
        self.created_users.append(user)
        return user

    async def find_user_by_email(self, _normalized_email: str) -> User | None:
        return self.user

    async def find_user_by_id(self, _user_id):
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
        return None

    async def touch_session(self, _session_id, _last_seen_at, _expires_at):
        raise NotImplementedError

    async def record_user_login(self, user_id, login_at):
        self.recorded_login_user_ids.append(user_id)
        self.user.last_login_at = login_at
        self.user.updated_at = login_at
        return self.user

    async def create_audit_log(self, audit_log) -> None:
        self.audit_logs.append(audit_log)


def test_dummy_password_hash_is_valid_argon2_with_current_work_factor():
    current_hash = hash_password("Password123!")

    assert DUMMY_PASSWORD_HASH.startswith("$argon2id$")
    assert verify_password("not-the-dummy-password",
                           DUMMY_PASSWORD_HASH) is False
    assert DUMMY_PASSWORD_HASH.split("$")[3] == current_hash.split("$")[3]


def _usecase(
    repository: AuthRepositoryStub,
    unit_of_work: UnitOfWorkStub | None = None,
) -> AuthUsecase:
    return AuthUsecase(
        auth_repository=repository,
        unit_of_work=unit_of_work or UnitOfWorkStub(),
        auth_rate_limiter=AllowingRateLimiter(),
        auth_settings=AuthSettings(),
        logger=getLogger(__name__),
    )


@pytest.mark.asyncio
async def test_login_verifies_dummy_password_hash_when_user_is_missing(
        monkeypatch):
    calls = []

    def fake_verify_password(raw_password: str, hashed_password: str) -> bool:
        calls.append((raw_password, hashed_password))
        return False

    monkeypatch.setattr(auth_usecase_module, "verify_password",
                        fake_verify_password)

    with pytest.raises(InvalidCredentialsError):
        await _usecase(AuthRepositoryStub(user=None)).login(
            email="missing@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert calls == [("Password123!", DUMMY_PASSWORD_HASH)]


@pytest.mark.asyncio
async def test_login_rejects_inactive_user_without_creating_session(
        monkeypatch):

    def fake_verify_password(_raw_password: str,
                             _hashed_password: str) -> bool:
        return True

    monkeypatch.setattr(auth_usecase_module, "verify_password",
                        fake_verify_password)
    repository = AuthRepositoryStub(user=User(
        email="inactive@example.com", password_hash="hashed", is_active=False))

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
async def test_login_records_last_login_before_creating_session(monkeypatch):

    def fake_verify_password(_raw_password: str,
                             _hashed_password: str) -> bool:
        return True

    monkeypatch.setattr(auth_usecase_module, "verify_password",
                        fake_verify_password)
    user = User(email="active@example.com",
                password_hash="hashed",
                is_active=True)
    repository = AuthRepositoryStub(user=user)

    issued_session = await _usecase(repository).login(
        email="active@example.com",
        password="Password123!",
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert repository.recorded_login_user_ids == [user.id]
    assert issued_session.user.last_login_at is not None
    assert issued_session.user.updated_at == issued_session.user.last_login_at


@pytest.mark.asyncio
async def test_register_records_last_login_for_issued_session():
    repository = AuthRepositoryStub(user=None)

    issued_session = await _usecase(repository).register(
        email="new@example.com",
        password="Password123!",
        current_session_token=None,
        ip_address="127.0.0.1",
        user_agent="pytest",
    )

    assert repository.created_users == [issued_session.user]
    assert repository.recorded_login_user_ids == [issued_session.user.id]
    assert issued_session.user.last_login_at is not None


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
        self.operations.append(
            ("find_active_session", self._unit_of_work.in_transaction))
        return self.active_session

    async def find_user_by_id(self, _user_id):
        self.operations.append(
            ("find_user_by_id", self._unit_of_work.in_transaction))
        return self.user

    async def find_session_by_token_hash(self, _token_hash: str):
        self.operations.append(
            ("find_session_by_token_hash", self._unit_of_work.in_transaction))
        return None

    async def touch_session(self, _session_id, last_seen_at, expires_at):
        self.operations.append(
            ("touch_session", self._unit_of_work.in_transaction))
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
        created_at=auth_usecase_module.utcnow(),
        last_seen_at=auth_usecase_module.utcnow(),
        expires_at=auth_usecase_module.utcnow() + timedelta(minutes=10),
    )
    repository = TransactionRecordingRepository(
        unit_of_work=unit_of_work,
        user=user,
        active_session=active_session,
    )

    auth_context = await _usecase(repository,
                                  unit_of_work).authenticate_session(
                                      session_token="session-token",
                                      ip_address="127.0.0.1",
                                      user_agent="pytest",
                                  )

    assert auth_context is not None
    assert repository.operations == [
        ("find_active_session", True),
        ("find_user_by_id", True),
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
