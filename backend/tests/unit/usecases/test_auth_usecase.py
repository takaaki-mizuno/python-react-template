from contextlib import asynccontextmanager
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


class AuthRepositoryStub:

    def __init__(self, user: User | None):
        self.user = user
        self.created_sessions: list[AuthSession] = []
        self.audit_logs = []
        self.recorded_login_user_ids = []
        self.created_users: list[User] = []

    @asynccontextmanager
    async def transaction(self):
        yield

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


def _usecase(repository: AuthRepositoryStub) -> AuthUsecase:
    return AuthUsecase(
        auth_repository=repository,
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

    logged_in_user, _session, _session_token, _csrf_token = await _usecase(
        repository).login(
            email="active@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.recorded_login_user_ids == [user.id]
    assert logged_in_user.last_login_at is not None
    assert logged_in_user.updated_at == logged_in_user.last_login_at


@pytest.mark.asyncio
async def test_register_records_last_login_for_issued_session():
    repository = AuthRepositoryStub(user=None)

    registered_user, _session, _session_token, _csrf_token = await _usecase(
        repository).register(
            email="new@example.com",
            password="Password123!",
            current_session_token=None,
            ip_address="127.0.0.1",
            user_agent="pytest",
        )

    assert repository.created_users == [registered_user]
    assert repository.recorded_login_user_ids == [registered_user.id]
    assert registered_user.last_login_at is not None
