# Auth Backend Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/auth/csrf`, `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` を Cookie session 方式で実装し、backend 単体で browser auth が成立する状態を作る。

**Architecture:** `controllers -> usecases -> services / models` の既存レイヤを維持しつつ、auth は専用の usecase と repository に閉じる。repository は singleton で session factory だけを保持し、各 method で `async with session_factory() as session` を使う。CSRF は `Depends` で強制し、session の有効判定は repository に集約する。

**Tech Stack:** FastAPI, Injector, SQLModel, PostgreSQL, pwdlib[argon2], email-validator, pytest, FastAPI TestClient

**Dependencies:** [20260418-auth-structure.md](./20260418-auth-structure.md), [20260418-auth-db-migration.md](./20260418-auth-db-migration.md), [20260418-auth-delivery-notes.md](./20260418-auth-delivery-notes.md)

**Done When:** register / login / me / logout の happy path と failure path が通り、session expiry / revoke / fixation / CSRF / rate limit の責務がコード上で一意になる。あわせて `backend/AGENTS.md` の auth 追記が計画どおり更新される。

---

## File Structure

- Create: `backend/app/interfaces/services/auth_repository_interface.py`
- Create: `backend/app/interfaces/usecases/auth_usecase_interface.py`
- Create: `backend/app/services/auth_repository.py`
- Create: `backend/app/usecases/auth_usecase.py`
- Create: `backend/app/controllers/auth_controller.py`
- Create: `backend/app/controllers/auth_dependencies.py`
- Create: `backend/app/config/auth.py`
- Create: `backend/app/libraries/password_hasher.py`
- Create: `backend/app/libraries/session_tokens.py`
- Create: `backend/app/libraries/auth_rate_limiter.py`
- Create: `backend/app/models/auth_errors.py`
- Create: `backend/app/models/auth_schemas.py`
- Create: `backend/app/models/auth_event_type.py`
- Create: `backend/tests/unit/libraries/test_session_tokens.py`
- Create: `backend/tests/unit/libraries/test_password_hasher.py`
- Create: `backend/tests/unit/libraries/test_auth_rate_limiter.py`
- Create: `backend/tests/unit/config/test_auth_settings.py`
- Create: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/app/bootstrap/container.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/interfaces/services/__init__.py`
- Modify: `backend/app/interfaces/usecases/__init__.py`
- Modify: `backend/app/services/__init__.py`
- Modify: `backend/app/usecases/__init__.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/AGENTS.md`

## Task 1: auth contract test と test client fixture を先に固定する

**Files:**
- Create: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/conftest.py`

- [x] **Step 1: `client` fixture が test DB を使うようにする**

`backend/tests/integration/conftest.py` に auth controller 向け fixture を追加する。

```python
import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.create_app import create_app


@pytest.fixture
def client(monkeypatch) -> Iterator[TestClient]:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for auth integration tests")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv(
        "ALEMBIC_DATABASE_URL",
        test_database_url.replace("+asyncpg", ""),
    )

    with TestClient(create_app()) as test_client:
        yield test_client
```

補足:

- この fixture が安全に動く前提は、DB 計画どおり `get_database_settings()` と `build_engine_and_session_factory()` が lazy であること
- `container.py` で engine / session factory / repository / usecase を module top-level に置いたら、この fixture は壊れる。必ず `configure(binder)` の中で作る
- `clean_auth_tables` は DB migration 計画で作った `backend/tests/integration/conftest.py` の autouse fixture を引き継ぐ

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL because auth routes are未実装

- [x] **Step 2: happy path と failure path の contract test を書く**

```python
def test_get_me_returns_401_without_session(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_register_then_me_returns_current_user(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    register_response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert register_response.status_code == 201
    assert register_response.cookies.get("session_token")

    me_response = client.get("/api/auth/me")

    assert me_response.status_code == 200
    assert me_response.json()["email"] == "user@example.com"


def test_register_duplicate_email_returns_409(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    first_response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": csrf_token},
    )
    assert first_response.status_code == 201

    duplicate_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    duplicate_response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": duplicate_csrf},
    )

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["detail"] == "Email already registered"


def test_register_with_weak_password_returns_422(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    response = client.post(
        "/api/auth/register",
        json={"email": "weak@example.com", "password": "short"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 422


def test_login_with_invalid_password_returns_generic_401(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": csrf_token},
    )

    login_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
        headers={"X-CSRF-Token": login_csrf},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Unauthorized"


def test_logout_clears_cookie_and_rejects_subsequent_me(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": csrf_token},
    )

    logout_response = client.post(
        "/api/auth/logout",
        headers={"X-CSRF-Token": client.cookies.get("csrf_token")},
    )

    assert logout_response.status_code == 204
    set_cookie_headers = logout_response.headers.get_list("set-cookie")
    assert any(
        "session_token=" in header and "Max-Age=0" in header
        for header in set_cookie_headers
    )

    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 401
```

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL with route not found or import error

- [x] **Step 3: コミットせず次タスクへ進む**

Run: なし
Expected: 欲しい API contract がコードより先に固定されている。

## Task 2: password / token / rate limit の library を実装する

**Files:**
- Create: `backend/app/config/auth.py`
- Create: `backend/app/libraries/password_hasher.py`
- Create: `backend/app/libraries/session_tokens.py`
- Create: `backend/app/libraries/auth_rate_limiter.py`
- Create: `backend/app/models/auth_event_type.py`
- Create: `backend/app/models/auth_errors.py`
- Create: `backend/tests/unit/config/test_auth_settings.py`
- Create: `backend/tests/unit/libraries/test_session_tokens.py`
- Create: `backend/tests/unit/libraries/test_password_hasher.py`
- Create: `backend/tests/unit/libraries/test_auth_rate_limiter.py`

- [x] **Step 1: runtime 依存追加の承認を取る**

Run: なし
Expected: `uv add 'pwdlib[argon2]' email-validator` 実施のユーザー承認が得られる。

- [x] **Step 2: unit test を先に書く**

```python
from app.config.auth import get_auth_settings
from app.libraries.password_hasher import (
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.libraries.session_tokens import generate_token, hash_token


def test_password_hash_round_trip():
    hashed_password = hash_password("Password123!")

    assert verify_password("Password123!", hashed_password) is True


def test_password_policy_rejects_short_password():
    is_valid, message = validate_password_policy("short")

    assert is_valid is False
    assert message == "Password must be at least 12 characters long"


def test_hash_token_is_deterministic_for_high_entropy_token():
    token = "session-token"

    assert hash_token(token) == hash_token(token)


def test_generate_token_is_not_empty():
    assert generate_token()


def test_auth_settings_reads_session_ttl_from_env(monkeypatch):
    monkeypatch.setenv("AUTH_SESSION_ABSOLUTE_TTL_SECONDS", "123")

    settings = get_auth_settings()

    assert settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS == 123
```

`backend/tests/unit/libraries/test_auth_rate_limiter.py`:

```python
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter


def test_rate_limiter_blocks_after_threshold():
    limiter = InMemoryLoginRateLimiter(
        window_seconds=900,
        max_attempts_per_email_ip=2,
        max_attempts_per_ip=10,
    )

    assert limiter.allow("127.0.0.1", "user@example.com") is True
    assert limiter.allow("127.0.0.1", "user@example.com") is True
    assert limiter.allow("127.0.0.1", "user@example.com") is False


def test_rate_limiter_reset_clears_state():
    limiter = InMemoryLoginRateLimiter(
        window_seconds=900,
        max_attempts_per_email_ip=1,
        max_attempts_per_ip=10,
    )

    assert limiter.allow("127.0.0.1", "user@example.com") is True
    assert limiter.allow("127.0.0.1", "user@example.com") is False

    limiter.reset()

    assert limiter.allow("127.0.0.1", "user@example.com") is True
```

Run: `cd backend && uv run pytest tests/unit/config/test_auth_settings.py tests/unit/libraries/test_password_hasher.py tests/unit/libraries/test_session_tokens.py tests/unit/libraries/test_auth_rate_limiter.py -v`
Expected: FAIL

- [x] **Step 3: 最小実装で library を通す**

`backend/app/libraries/password_hasher.py`:

```python
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def validate_password_policy(raw_password: str) -> tuple[bool, str | None]:
    if len(raw_password) < 12:
        return False, "Password must be at least 12 characters long"
    if len(raw_password) > 128:
        return False, "Password must be 128 characters or fewer"
    return True, None


def hash_password(raw_password: str) -> str:
    return password_hash.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return password_hash.verify(raw_password, hashed_password)
```

`backend/app/libraries/session_tokens.py`:

```python
import hashlib
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    # session token 自体が高 entropy の乱数なので、DB lookup 用の固定 hash で十分
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
```

`backend/app/libraries/auth_rate_limiter.py`:

```python
from collections import defaultdict, deque
from time import time


class InMemoryLoginRateLimiter:
    def __init__(
        self,
        window_seconds: int,
        max_attempts_per_email_ip: int,
        max_attempts_per_ip: int,
    ):
        self._window_seconds = window_seconds
        self._max_attempts_per_email_ip = max_attempts_per_email_ip
        self._max_attempts_per_ip = max_attempts_per_ip
        self._email_ip_buckets = defaultdict(deque)
        self._ip_buckets = defaultdict(deque)

    def allow(self, ip_address: str, normalized_email: str) -> bool:
        now = time()
        email_ip_key = f"{ip_address}:{normalized_email}"
        self._trim(self._email_ip_buckets[email_ip_key], now)
        self._trim(self._ip_buckets[ip_address], now)

        if len(self._email_ip_buckets[email_ip_key]) >= self._max_attempts_per_email_ip:
            return False
        if len(self._ip_buckets[ip_address]) >= self._max_attempts_per_ip:
            return False

        self._email_ip_buckets[email_ip_key].append(now)
        self._ip_buckets[ip_address].append(now)
        return True

    def _trim(self, bucket: deque[float], now: float) -> None:
        while bucket and now - bucket[0] > self._window_seconds:
            bucket.popleft()

    def reset(self) -> None:
        self._email_ip_buckets.clear()
        self._ip_buckets.clear()
```

`backend/app/models/auth_event_type.py`:

```python
from enum import StrEnum


class AuthEventType(StrEnum):
    REGISTER_SUCCESS = "register_success"
    REGISTER_FAILED = "register_failed"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    LOGOUT = "logout"
    SESSION_REJECTED = "session_rejected"
```

`backend/app/models/auth_errors.py`:

```python
class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class RateLimitExceededError(Exception):
    pass


class WeakPasswordError(Exception):
    pass
```

`backend/app/config/auth.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    AUTH_SESSION_ABSOLUTE_TTL_SECONDS: int = 604800
    AUTH_SESSION_IDLE_TTL_SECONDS: int = 86400
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 900
    AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP: int = 5
    AUTH_RATE_LIMIT_ATTEMPTS_PER_IP: int = 20


def get_auth_settings() -> AuthSettings:
    return AuthSettings()
```

- [x] **Step 4: unit test を通す**

Run: `cd backend && uv run pytest tests/unit/config/test_auth_settings.py tests/unit/libraries/test_password_hasher.py tests/unit/libraries/test_session_tokens.py tests/unit/libraries/test_auth_rate_limiter.py -v`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add backend/app/config/auth.py backend/app/libraries/password_hasher.py backend/app/libraries/session_tokens.py backend/app/libraries/auth_rate_limiter.py backend/app/models/auth_event_type.py backend/app/models/auth_errors.py backend/tests/unit/config/test_auth_settings.py backend/tests/unit/libraries/test_password_hasher.py backend/tests/unit/libraries/test_session_tokens.py backend/tests/unit/libraries/test_auth_rate_limiter.py
git commit -m "feat(backend/auth): add auth security libraries"
```

## Task 3: repository / usecase / controller の happy path を実装する

**Files:**
- Create: `backend/app/interfaces/services/auth_repository_interface.py`
- Create: `backend/app/interfaces/usecases/auth_usecase_interface.py`
- Create: `backend/app/services/auth_repository.py`
- Create: `backend/app/usecases/auth_usecase.py`
- Create: `backend/app/controllers/auth_controller.py`
- Create: `backend/app/controllers/auth_dependencies.py`
- Create: `backend/app/models/auth_schemas.py`
- Modify: `backend/app/bootstrap/container.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/interfaces/services/__init__.py`
- Modify: `backend/app/interfaces/usecases/__init__.py`
- Modify: `backend/app/services/__init__.py`
- Modify: `backend/app/usecases/__init__.py`

- [x] **Step 1: request / response schema を定義する**

```python
from uuid import UUID

from pydantic import EmailStr, Field
from sqlmodel import SQLModel


class RegisterRequest(SQLModel):
    email: EmailStr
    # pydantic.Field を使うこと。SQLModel.Field と混同しない
    password: str = Field(min_length=12, max_length=128)


class LoginRequest(SQLModel):
    email: EmailStr
    password: str = Field(max_length=128)


class AuthUserResponse(SQLModel):
    id: UUID
    email: EmailStr


class CsrfTokenResponse(SQLModel):
    csrfToken: str
```

Run: `cd backend && uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL

- [x] **Step 2: repository は per-call session で実装する**

`backend/app/interfaces/services/auth_repository_interface.py`:

```python
from abc import ABCMeta, abstractmethod
from uuid import UUID

from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_session import AuthSession
from app.models.user import User


class AuthRepositoryInterface(metaclass=ABCMeta):
    @abstractmethod
    async def create_user(self, email: str, password_hash: str) -> User:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_email(self, normalized_email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_id(self, user_id: UUID) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def create_session(
        self,
        user_id: UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at,
        last_seen_at,
        expires_at,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def find_active_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        raise NotImplementedError

    @abstractmethod
    async def revoke_session(self, session_id: UUID) -> None:
        raise NotImplementedError

    @abstractmethod
    async def touch_session(self, session_id: UUID, last_seen_at, expires_at) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        raise NotImplementedError
```

`backend/app/services/auth_repository.py` の重要部分:

```python
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from app.models.auth_errors import EmailAlreadyRegisteredError
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_session import AuthSession
from app.models.user import User


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AuthRepository(AuthRepositoryInterface):
    def __init__(self, session_factory):
        self._session_factory = session_factory

    async def create_user(self, email: str, password_hash: str) -> User:
        async with self._session_factory() as session:
            user = User(email=email, password_hash=password_hash)
            session.add(user)
            try:
                await session.commit()
            except IntegrityError as error:
                await session.rollback()
                raise EmailAlreadyRegisteredError from error
            await session.refresh(user)
            return user

    async def find_user_by_email(self, normalized_email: str) -> User | None:
        async with self._session_factory() as session:
            statement = select(User).where(User.email == normalized_email)
            result = await session.exec(statement)
            return result.one_or_none()

    async def find_user_by_id(self, user_id: UUID) -> User | None:
        async with self._session_factory() as session:
            statement = select(User).where(User.id == user_id)
            result = await session.exec(statement)
            return result.one_or_none()

    async def create_session(
        self,
        user_id: UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        created_at,
        last_seen_at,
        expires_at,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        async with self._session_factory() as session:
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
            await session.commit()
            await session.refresh(auth_session)
            return auth_session

    async def find_active_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        now = utcnow()
        async with self._session_factory() as session:
            statement = select(AuthSession).where(
                AuthSession.session_token_hash == token_hash,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
            result = await session.exec(statement)
            return result.one_or_none()

    async def revoke_session(self, session_id: UUID) -> None:
        async with self._session_factory() as session:
            auth_session = await session.get(AuthSession, session_id)
            if not auth_session:
                return
            auth_session.revoked_at = utcnow()
            session.add(auth_session)
            await session.commit()

    async def touch_session(self, session_id: UUID, last_seen_at, expires_at) -> AuthSession:
        async with self._session_factory() as session:
            auth_session = await session.get(AuthSession, session_id)
            auth_session.last_seen_at = last_seen_at
            auth_session.expires_at = expires_at
            session.add(auth_session)
            await session.commit()
            await session.refresh(auth_session)
            return auth_session

    async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
        async with self._session_factory() as session:
            session.add(audit_log)
            await session.commit()
```

補足:

- repository instance は singleton でよい
- ただし DB session を field に保持してはいけない
- 各 method が自分で `async with self._session_factory() as session` を開閉する

- [x] **Step 3: usecase と controller を実装する**

`backend/app/usecases/auth_usecase.py` の重要部分:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from logging import Logger

from app.config.auth import AuthSettings
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.libraries.password_hasher import (
    hash_password,
    validate_password_policy,
    verify_password,
)
from app.models.auth_audit_log import AuthAuditLog
from app.models.auth_errors import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    RateLimitExceededError,
    WeakPasswordError,
)
from app.models.auth_event_type import AuthEventType
from app.models.auth_session import AuthSession
from app.models.user import User
from app.libraries.session_tokens import generate_token, hash_token


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

    async def issue_csrf_token(self) -> str:
        return generate_token()

    def _calculate_session_expiry(
        self,
        created_at: datetime,
        last_seen_at: datetime,
    ) -> datetime:
        absolute_expires_at = created_at + timedelta(
            seconds=self._auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
        )
        idle_expires_at = last_seen_at + timedelta(
            seconds=self._auth_settings.AUTH_SESSION_IDLE_TTL_SECONDS,
        )
        # structure.md で固定した min(created_at + absolute_ttl, last_seen_at + idle_ttl)
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
                hash_token(current_session_token),
            )
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
        if not self._auth_rate_limiter.allow(ip_address or "unknown", normalized_email):
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=None,
                    session_id=None,
                    event_type=AuthEventType.REGISTER_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            raise RateLimitExceededError

        is_valid_password, error_message = validate_password_policy(password)
        if not is_valid_password:
            # defense-in-depth: DTO validation が先に 422 を返す想定だが、usecase 直接呼び出しにも備える
            raise WeakPasswordError(error_message or "Invalid password")

        existing_user = await self._auth_repository.find_user_by_email(normalized_email)
        if existing_user:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=existing_user.id,
                    session_id=None,
                    event_type=AuthEventType.REGISTER_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            raise EmailAlreadyRegisteredError

        try:
            user = await self._auth_repository.create_user(
                normalized_email,
                hash_password(password),
            )
        except EmailAlreadyRegisteredError:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=None,
                    session_id=None,
                    event_type=AuthEventType.REGISTER_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            raise
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
            )
        )
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
        if not self._auth_rate_limiter.allow(ip_address or "unknown", normalized_email):
            raise RateLimitExceededError

        user = await self._auth_repository.find_user_by_email(normalized_email)
        if not user or not verify_password(password, user.password_hash):
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=user.id if user else None,
                    session_id=None,
                    event_type=AuthEventType.LOGIN_FAILED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            raise InvalidCredentialsError

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
            )
        )
        return user, session, session_token, csrf_token

    async def authenticate_session(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthenticatedSessionContext | None:
        if not session_token:
            return None

        auth_session = await self._auth_repository.find_active_session_by_token_hash(
            hash_token(session_token),
        )
        if not auth_session:
            await self._auth_repository.create_audit_log(
                AuthAuditLog(
                    user_id=None,
                    session_id=None,
                    event_type=AuthEventType.SESSION_REJECTED,
                    ip_address=ip_address,
                    user_agent=user_agent,
                )
            )
            return None

        user = await self._auth_repository.find_user_by_id(auth_session.user_id)
        if not user or not user.is_active:
            await self._auth_repository.revoke_session(auth_session.id)
            return None

        now = utcnow()
        refreshed_session = await self._auth_repository.touch_session(
            auth_session.id,
            last_seen_at=now,
            expires_at=self._calculate_session_expiry(auth_session.created_at, now),
        )
        return AuthenticatedSessionContext(user=user, session=refreshed_session)

    async def logout(
        self,
        session_token: str | None,
        ip_address: str | None,
        user_agent: str | None,
    ) -> None:
        if not session_token:
            return

        auth_session = await self._auth_repository.find_active_session_by_token_hash(
            hash_token(session_token),
        )
        if not auth_session:
            return

        await self._auth_repository.revoke_session(auth_session.id)
        await self._auth_repository.create_audit_log(
            AuthAuditLog(
                user_id=auth_session.user_id,
                session_id=auth_session.id,
                event_type=AuthEventType.LOGOUT,
                ip_address=ip_address,
                user_agent=user_agent,
            )
        )
```

`backend/app/controllers/auth_dependencies.py` の重要部分:

```python
from fastapi import HTTPException, Request

from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.usecases.auth_usecase import AuthenticatedSessionContext


async def require_current_session(request: Request) -> AuthenticatedSessionContext:
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    auth_context = await usecase.authenticate_session(
        session_token=request.cookies.get("session_token"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    if auth_context is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return auth_context
```

`backend/app/controllers/auth_controller.py` の重要部分:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config.auth import get_auth_settings
from app.controllers.auth_dependencies import require_current_session
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_schemas import (
    AuthUserResponse,
    CsrfTokenResponse,
    LoginRequest,
    RegisterRequest,
)
from app.models.auth_errors import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    RateLimitExceededError,
    WeakPasswordError,
)
from app.usecases.auth_usecase import AuthenticatedSessionContext


def is_secure_request(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    return request.headers.get("x-forwarded-proto") == "https"


def set_session_cookie(
    response: Response,
    session_token: str,
    secure: bool,
    max_age_seconds: int,
) -> None:
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age_seconds,
    )


def set_csrf_cookie(
    response: Response,
    csrf_token: str,
    secure: bool,
    max_age_seconds: int,
) -> None:
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=max_age_seconds,
    )


def clear_session_cookie(response: Response, secure: bool) -> None:
    response.set_cookie(
        key="session_token",
        value="",
        httponly=True,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=0,
    )


def clear_csrf_cookie(response: Response, secure: bool) -> None:
    response.set_cookie(
        key="csrf_token",
        value="",
        httponly=False,
        samesite="lax",
        secure=secure,
        path="/",
        max_age=0,
    )


@router.get("/me", response_model=AuthUserResponse)
async def get_me(
    auth_context: AuthenticatedSessionContext = Depends(require_current_session),
) -> AuthUserResponse:
    return AuthUserResponse(id=auth_context.user.id, email=auth_context.user.email)


@router.post("/register", response_model=AuthUserResponse, status_code=201)
async def register(payload: RegisterRequest, request: Request, response: Response) -> AuthUserResponse:
    auth_settings = get_auth_settings()
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    try:
        user, session, session_token, csrf_token = await usecase.register(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(status_code=409, detail="Email already registered") from error
    except RateLimitExceededError as error:
        raise HTTPException(
            status_code=429,
            detail="Too many register attempts",
            headers={"Retry-After": str(auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)},
        ) from error
    except WeakPasswordError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    secure = is_secure_request(request)
    set_session_cookie(
        response,
        session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=AuthUserResponse)
async def login(payload: LoginRequest, request: Request, response: Response) -> AuthUserResponse:
    auth_settings = get_auth_settings()
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    try:
        user, session, session_token, csrf_token = await usecase.login(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=401, detail="Unauthorized") from error

    secure = is_secure_request(request)
    set_session_cookie(
        response,
        session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=user.id, email=user.email)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response) -> Response:
    secure = is_secure_request(request)
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    await usecase.logout(
        request.cookies.get("session_token"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    clear_session_cookie(response, secure=secure)
    clear_csrf_cookie(response, secure=secure)
    return response
```

`backend/app/bootstrap/route.py`:

```python
from app.controllers.auth_controller import router as auth_router


def _setup_api_routes(app: FastAPI) -> FastAPI:
    router = APIRouter()
    router.include_router(healthz_router)
    router.include_router(sample_router)
    router.include_router(auth_router)
    app.include_router(router, prefix="/api")
    return app
```

`backend/app/bootstrap/container.py`:

```python
from logging import Logger, getLogger

from injector import Binder, Injector, singleton

from app.config.auth import get_auth_settings
from app.config import Config, config
from app.interfaces.services.auth_repository_interface import AuthRepositoryInterface
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.interfaces.usecases.get_sample_index_usecase_interface import GetSampleIndexUsecaseInterface
from app.libraries.database_engine import build_engine_and_session_factory
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter
from app.services.auth_repository import AuthRepository
from app.usecases.auth_usecase import AuthUsecase
from app.usecases.get_sample_index_usecase import GetSampleIndexUsecase


def build_container() -> Injector:
    return Injector(modules=[configure])


def configure(binder: Binder):
    binder.bind(Config, to=config, scope=singleton)

    logger = getLogger(__name__)
    binder.bind(Logger, to=logger, scope=singleton)

    get_sample_index_usecase = GetSampleIndexUsecase(
        config=config,
        logger=logger,
    )
    binder.bind(GetSampleIndexUsecaseInterface, to=get_sample_index_usecase)

    auth_settings = get_auth_settings()
    _, session_factory = build_engine_and_session_factory()

    auth_repository = AuthRepository(session_factory=session_factory)
    auth_rate_limiter = InMemoryLoginRateLimiter(
        window_seconds=auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        max_attempts_per_email_ip=auth_settings.AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP,
        max_attempts_per_ip=auth_settings.AUTH_RATE_LIMIT_ATTEMPTS_PER_IP,
    )
    auth_usecase = AuthUsecase(
        auth_repository=auth_repository,
        auth_rate_limiter=auth_rate_limiter,
        auth_settings=auth_settings,
        logger=logger,
    )

    binder.bind(AuthRepositoryInterface, to=auth_repository, scope=singleton)
    binder.bind(InMemoryLoginRateLimiter, to=auth_rate_limiter, scope=singleton)
    binder.bind(AuthUsecaseInterface, to=auth_usecase, scope=singleton)
```

補足:

- 既存の `Config` / `Logger` / `GetSampleIndexUsecaseInterface` bind は削除しない。上のサンプルは既存 bind と auth bind を含む完成形として扱う
- app ごとの singleton は `configure(binder)` の中で閉じる。module top-level singleton を作らない
- `authenticate_session()` が `last_seen_at` と `expires_at` を更新することで、idle 24h / absolute 7d の sliding renewal を表現する
- `register()` / `login()` は session fixation 対策として、既存 session があれば必ず revoke してから新しい cookie を発行する

- [x] **Step 4: contract test を通す**

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py -v`
Expected: register / me / invalid login / logout の contract test が PASS する

- [ ] **Step 5: コミットする**

```bash
git add backend/app/interfaces/services backend/app/interfaces/usecases backend/app/services/auth_repository.py backend/app/usecases/auth_usecase.py backend/app/controllers/auth_controller.py backend/app/controllers/auth_dependencies.py backend/app/models/auth_schemas.py backend/app/bootstrap/container.py backend/app/bootstrap/route.py backend/tests/integration/test_auth_controller.py
git commit -m "feat(backend/auth): implement auth repository usecase and controller"
```

## Task 4: CSRF / rate limit / failure path / audit log を仕上げる

**Files:**
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] **Step 1: 失敗系の test を追加する**

```python
def test_register_requires_matching_csrf_header(client):
    csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]

    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": f"{csrf_token}-wrong"},
    )

    assert response.status_code == 403


def test_register_rate_limit_returns_429(client):
    for _ in range(5):
        csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
        client.post(
            "/api/auth/register",
            json={"email": "limited@example.com", "password": "Password123!"},
            headers={"X-CSRF-Token": csrf_token},
        )

    blocked_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    blocked_response = client.post(
        "/api/auth/register",
        json={"email": "limited@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": blocked_csrf},
    )

    assert blocked_response.status_code == 429


def test_login_rate_limit_returns_429(client):
    for _ in range(5):
        csrf_token = client.get("/api/auth/csrf").json()["csrfToken"]
        client.post(
            "/api/auth/login",
            json={"email": "user@example.com", "password": "wrong-password"},
            headers={"X-CSRF-Token": csrf_token},
        )

    blocked_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    blocked_response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "wrong-password"},
        headers={"X-CSRF-Token": blocked_csrf},
    )

    assert blocked_response.status_code == 429
```

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL

- [x] **Step 2: CSRF / rate limit / audit log / test cleanup を仕上げる**

`backend/tests/integration/conftest.py` に rate limiter reset を追加する:

```python
from app.libraries.auth_rate_limiter import InMemoryLoginRateLimiter


@pytest.fixture
def client(monkeypatch) -> Iterator[TestClient]:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for auth integration tests")

    monkeypatch.setenv("DATABASE_URL", test_database_url)
    monkeypatch.setenv(
        "ALEMBIC_DATABASE_URL",
        test_database_url.replace("+asyncpg", ""),
    )

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    app.state.injector.get(InMemoryLoginRateLimiter).reset()
```

補足:

- `client` fixture は function scope のまま維持する
- rate limiter を app singleton にしても、各 test の teardown で `reset()` すれば test 順依存が入らない

`backend/app/controllers/auth_dependencies.py`:

```python
from fastapi import HTTPException, Request

from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.usecases.auth_usecase import AuthenticatedSessionContext


async def require_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="CSRF validation failed")


async def require_current_session(request: Request) -> AuthenticatedSessionContext:
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    auth_context = await usecase.authenticate_session(
        session_token=request.cookies.get("session_token"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    if auth_context is None:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return auth_context
```

`backend/app/controllers/auth_controller.py`:

```python
from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.config.auth import get_auth_settings
from app.controllers.auth_dependencies import require_csrf, require_current_session
from app.interfaces.usecases.auth_usecase_interface import AuthUsecaseInterface
from app.models.auth_errors import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    RateLimitExceededError,
    WeakPasswordError,
)
from app.usecases.auth_usecase import AuthenticatedSessionContext
from app.models.auth_schemas import (
    AuthUserResponse,
    CsrfTokenResponse,
    LoginRequest,
    RegisterRequest,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/csrf", response_model=CsrfTokenResponse)
async def get_csrf(request: Request, response: Response) -> CsrfTokenResponse:
    auth_settings = get_auth_settings()
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    csrf_token = await usecase.issue_csrf_token()
    set_csrf_cookie(
        response,
        csrf_token,
        secure=is_secure_request(request),
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return CsrfTokenResponse(csrfToken=csrf_token)


@router.get("/me", response_model=AuthUserResponse)
async def get_me(
    auth_context: AuthenticatedSessionContext = Depends(require_current_session),
) -> AuthUserResponse:
    return AuthUserResponse(id=auth_context.user.id, email=auth_context.user.email)


@router.post("/register", response_model=AuthUserResponse, status_code=201, dependencies=[Depends(require_csrf)])
async def register(payload: RegisterRequest, request: Request, response: Response) -> AuthUserResponse:
    auth_settings = get_auth_settings()
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    try:
        user, session, session_token, csrf_token = await usecase.register(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(status_code=409, detail="Email already registered") from error
    except RateLimitExceededError as error:
        raise HTTPException(
            status_code=429,
            detail="Too many register attempts",
            headers={"Retry-After": str(auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)},
        ) from error
    except WeakPasswordError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    secure = is_secure_request(request)
    set_session_cookie(
        response,
        session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=user.id, email=user.email)


@router.post("/login", response_model=AuthUserResponse, dependencies=[Depends(require_csrf)])
async def login(payload: LoginRequest, request: Request, response: Response) -> AuthUserResponse:
    auth_settings = get_auth_settings()
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    try:
        user, session, session_token, csrf_token = await usecase.login(
            email=payload.email,
            password=payload.password,
            current_session_token=request.cookies.get("session_token"),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(status_code=401, detail="Unauthorized") from error
    except RateLimitExceededError as error:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts",
            headers={"Retry-After": str(auth_settings.AUTH_RATE_LIMIT_WINDOW_SECONDS)},
        ) from error

    secure = is_secure_request(request)
    set_session_cookie(
        response,
        session_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    set_csrf_cookie(
        response,
        csrf_token,
        secure=secure,
        max_age_seconds=auth_settings.AUTH_SESSION_ABSOLUTE_TTL_SECONDS,
    )
    return AuthUserResponse(id=user.id, email=user.email)


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(request: Request, response: Response) -> Response:
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    secure = is_secure_request(request)
    await usecase.logout(
        request.cookies.get("session_token"),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    clear_session_cookie(response, secure=secure)
    clear_csrf_cookie(response, secure=secure)
    return response
```

`backend/app/services/auth_repository.py`:

```python
async def create_audit_log(self, audit_log: AuthAuditLog) -> None:
    async with self._session_factory() as session:
        session.add(audit_log)
        await session.commit()
```

補足:

- duplicate email / register rate limit 時は `AuthEventType.REGISTER_FAILED` を必ず残す
- invalid credential 時も `AuthEventType.LOGIN_FAILED` を必ず残す
- revoked / expired session で `me` が拒否された場合は `AuthEventType.SESSION_REJECTED` を残す
- `Retry-After` は auth rate limit window 秒を返す

- [x] **Step 3: full suite を通す**

Run: `cd backend && uv run pytest`
Expected: PASS

Run: `cd backend && uv run isort . --check-only && uv run yapf -dr app/`
Expected: 差分なし

- [x] **Step 4: 手動の最低確認を行う**

Run: `curl -i http://localhost:8000/api/auth/csrf`
Expected: `Set-Cookie: csrf_token=...`

Run: `curl -i http://localhost:8000/api/auth/me`
Expected: `401 Unauthorized`

- [ ] **Step 5: コミットする**

```bash
git add backend/app/controllers/auth_dependencies.py backend/app/controllers/auth_controller.py backend/app/services/auth_repository.py backend/app/usecases/auth_usecase.py backend/tests/integration/conftest.py backend/tests/integration/test_auth_controller.py
git commit -m "feat(backend/auth): enforce csrf rate limit and audit logging"
```

## Task 5: backend ガイドを更新し、最終確認を行う

**Files:**
- Modify: `backend/AGENTS.md`

- [x] **Step 1: backend ガイドに auth 方針を追記する**

```md
- 認証領域の integration test は PostgreSQL を正とする
- `python manage.py db-upgrade` / `python manage.py db-downgrade` を migration の主要コマンドとする
- `register` / `login` / `logout` の CSRF は FastAPI Depends で共通化する
```

- [x] **Step 2: 文書と実装順の整合を見直す**

Run: なし
Expected: `20260418-auth-structure.md`, `20260418-auth-db-migration.md`, `20260418-auth-delivery-notes.md` と backend ガイドの記述が矛盾していない。

- [ ] **Step 3: コミットする**

```bash
git add backend/AGENTS.md documents/plans/20260418-auth-structure.md documents/plans/20260418-auth-delivery-notes.md
git commit -m "docs(backend/auth): align backend guide with auth backend flow"
```
