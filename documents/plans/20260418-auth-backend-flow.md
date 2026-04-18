# Auth Backend Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `GET /api/auth/csrf`, `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` を Cookie session 方式で実装し、backend 単体で browser auth が成立する状態を作る。

**Architecture:** `controllers -> usecases -> services / models` の既存レイヤを維持しつつ、auth は専用の usecase と repository に閉じる。認証状態は `auth_sessions` に保存し、cookie には生の session token と csrf token だけを載せ、DB にはハッシュを保存する。

**Tech Stack:** FastAPI, Injector, SQLModel, PostgreSQL, pwdlib[argon2], pytest, FastAPI TestClient

---

## File Structure

- Create: `backend/app/interfaces/services/auth_repository_interface.py`
- Create: `backend/app/interfaces/usecases/auth_usecase_interface.py`
- Create: `backend/app/services/auth_repository.py`
- Create: `backend/app/usecases/auth_usecase.py`
- Create: `backend/app/controllers/auth_controller.py`
- Create: `backend/app/libraries/password_hasher.py`
- Create: `backend/app/libraries/session_tokens.py`
- Create: `backend/app/models/auth_schemas.py`
- Create: `backend/tests/unit/libraries/test_session_tokens.py`
- Create: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/app/bootstrap/container.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/interfaces/services/__init__.py`
- Modify: `backend/app/interfaces/usecases/__init__.py`
- Modify: `backend/app/services/__init__.py`
- Modify: `backend/app/usecases/__init__.py`
- Modify: `backend/tests/integration/conftest.py`

## Task 1: API 契約の integration test を先に固定する

**Files:**
- Create: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/conftest.py`

- [ ] **Step 1: 認証 API の失敗テストを書く**

```python
def test_get_me_returns_401_without_session(client):
    response = client.get("/api/auth/me")

    assert response.status_code == 401
    assert response.json()["message"] == "Unauthorized"


def test_get_csrf_sets_cookie(client):
    response = client.get("/api/auth/csrf")

    assert response.status_code == 200
    assert response.json()["csrfToken"]
    assert response.cookies.get("csrf_token") == response.json()["csrfToken"]


def test_register_sets_session_cookie_and_returns_user(client):
    csrf_response = client.get("/api/auth/csrf")
    csrf_token = csrf_response.json()["csrfToken"]

    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": csrf_token},
    )

    assert response.status_code == 201
    assert response.json()["email"] == "user@example.com"
    assert response.cookies.get("session_token")
    assert response.cookies.get("csrf_token")
```

Run: `cd backend && uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL with route not found or import error

- [ ] **Step 2: ログインとログアウトの契約も追加する**

```python
def test_login_reissues_session_cookie(client):
    csrf_response = client.get("/api/auth/csrf")
    csrf_token = csrf_response.json()["csrfToken"]
    client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": csrf_token},
    )

    login_csrf = client.get("/api/auth/csrf").json()["csrfToken"]
    response = client.post(
        "/api/auth/login",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": login_csrf},
    )

    assert response.status_code == 200
    assert response.cookies.get("session_token")
    assert response.cookies.get("csrf_token")


def test_logout_revokes_session_and_clears_cookie(client):
    csrf_response = client.get("/api/auth/csrf")
    csrf_token = csrf_response.json()["csrfToken"]
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
    assert logout_response.cookies.get("session_token") == ""
```

`backend/tests/integration/conftest.py` には少なくとも `client` fixture を足す。

```python
import pytest
from fastapi.testclient import TestClient

from app.bootstrap.create_app import create_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())
```

Run: `cd backend && uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL

- [ ] **Step 3: 期待値を確定したまま commit せず次タスクへ進む**

Run: なし
Expected: 失敗しているが、欲しい API contract が固定されている

## Task 2: password hash と session token の library / repository を実装する

**Files:**
- Create: `backend/app/interfaces/services/auth_repository_interface.py`
- Create: `backend/app/services/auth_repository.py`
- Create: `backend/app/libraries/password_hasher.py`
- Create: `backend/app/libraries/session_tokens.py`
- Modify: `backend/app/interfaces/services/__init__.py`
- Modify: `backend/app/services/__init__.py`

- [ ] **Step 1: `pwdlib[argon2]` 追加の承認を取る**

Run: なし
Expected: `uv add 'pwdlib[argon2]'` 実施のユーザー承認が得られる

- [ ] **Step 2: token / hash helper の unit test を書く**

```python
from app.libraries.session_tokens import generate_token, hash_token


def test_hash_token_is_deterministic():
    token = "session-token"

    assert hash_token(token) == hash_token(token)


def test_generate_token_is_not_empty():
    assert generate_token()
```

Run: `cd backend && uv run pytest tests/unit/libraries/test_session_tokens.py -v`
Expected: FAIL with file not found

- [ ] **Step 3: 最小実装で helper と repository を作る**

`backend/app/libraries/session_tokens.py`:

```python
import hashlib
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
```

`backend/app/libraries/password_hasher.py`:

```python
from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()


def hash_password(raw_password: str) -> str:
    return password_hash.hash(raw_password)


def verify_password(raw_password: str, hashed_password: str) -> bool:
    return password_hash.verify(raw_password, hashed_password)
```

repository 契約は最低限次を持つ。

```python
class AuthRepositoryInterface(metaclass=ABCMeta):
    @abstractmethod
    async def create_user(self, email: str, password_hash: str) -> User:
        raise NotImplementedError

    @abstractmethod
    async def find_user_by_email(self, email: str) -> User | None:
        raise NotImplementedError

    @abstractmethod
    async def create_session(
        self,
        user_id: UUID,
        session_token_hash: str,
        csrf_token_hash: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> AuthSession:
        raise NotImplementedError

    @abstractmethod
    async def find_session_by_token_hash(self, token_hash: str) -> AuthSession | None:
        raise NotImplementedError

    @abstractmethod
    async def revoke_session(self, session_id: UUID) -> None:
        raise NotImplementedError
```

- [ ] **Step 4: unit test を通す**

Run: `cd backend && uv run pytest tests/unit/libraries/test_session_tokens.py -v`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add backend/app/interfaces/services backend/app/services backend/app/libraries/password_hasher.py backend/app/libraries/session_tokens.py backend/tests/unit/libraries/test_session_tokens.py
git commit -m "feat(auth): add auth repository and token helpers"
```

## Task 3: auth usecase と controller をつなぎ、Cookie session を発行する

**Files:**
- Create: `backend/app/interfaces/usecases/auth_usecase_interface.py`
- Create: `backend/app/usecases/auth_usecase.py`
- Create: `backend/app/controllers/auth_controller.py`
- Create: `backend/app/models/auth_schemas.py`
- Modify: `backend/app/bootstrap/container.py`
- Modify: `backend/app/bootstrap/route.py`
- Modify: `backend/app/interfaces/usecases/__init__.py`
- Modify: `backend/app/usecases/__init__.py`

- [ ] **Step 1: request / response schema を先に定義する**

```python
from sqlmodel import SQLModel


class RegisterRequest(SQLModel):
    email: str
    password: str


class LoginRequest(SQLModel):
    email: str
    password: str


class AuthUserResponse(SQLModel):
    id: str
    email: str


class CsrfTokenResponse(SQLModel):
    csrfToken: str
```

Run: `cd backend && uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL

- [ ] **Step 2: usecase の最小実装を書く**

```python
class AuthUsecase(AuthUsecaseInterface):
    def __init__(self, auth_repository: AuthRepositoryInterface, logger: Logger):
        self._auth_repository = auth_repository
        self._logger = logger

    async def issue_csrf_token(self) -> str:
        return generate_token()

    async def register(self, email: str, password: str, ip_address: str | None, user_agent: str | None):
        normalized_email = email.strip().lower()
        password_digest = hash_password(password)
        user = await self._auth_repository.create_user(normalized_email, password_digest)
        session_token = generate_token()
        csrf_token = generate_token()
        await self._auth_repository.create_session(
            user_id=user.id,
            session_token_hash=hash_token(session_token),
            csrf_token_hash=hash_token(csrf_token),
            ip_address=ip_address,
            user_agent=user_agent,
        )
        return user, session_token, csrf_token
```

- [ ] **Step 3: controller で cookie を設定する**

```python
@router.get("/csrf", response_model=CsrfTokenResponse)
async def get_csrf(response: Response, request: Request) -> CsrfTokenResponse:
    usecase = request.app.state.injector.get(AuthUsecaseInterface)
    csrf_token = await usecase.issue_csrf_token()
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        samesite="lax",
        secure=request.url.scheme == "https",
    )
    return CsrfTokenResponse(csrfToken=csrf_token)
```

`register`, `login`, `logout`, `me` も同じ controller にまとめ、`/api/auth` prefix で公開する。

`backend/app/bootstrap/container.py` では repository / usecase を bind する。

```python
engine, session_factory = build_engine_and_session_factory()
auth_repository = AuthRepository(session_factory=session_factory)
auth_usecase = AuthUsecase(auth_repository=auth_repository, logger=logger)
binder.bind(AuthRepositoryInterface, to=auth_repository, scope=singleton)
binder.bind(AuthUsecaseInterface, to=auth_usecase, scope=singleton)
```

- [ ] **Step 4: integration test を通す**

Run: `cd backend && uv run pytest tests/integration/test_auth_controller.py -v`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add backend/app/interfaces/usecases backend/app/usecases backend/app/controllers/auth_controller.py backend/app/models/auth_schemas.py backend/app/bootstrap/container.py backend/app/bootstrap/route.py backend/tests/integration/test_auth_controller.py
git commit -m "feat(auth): implement auth controller and usecase"
```

## Task 4: CSRF 強制・監査ログ・品質ゲートを仕上げる

**Files:**
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [ ] **Step 1: CSRF 必須ケースの失敗テストを追加する**

```python
def test_register_requires_matching_csrf_header(client):
    csrf_response = client.get("/api/auth/csrf")

    response = client.post(
        "/api/auth/register",
        json={"email": "user@example.com", "password": "Password123!"},
        headers={"X-CSRF-Token": "mismatch"},
    )

    assert response.status_code == 403
```

Run: `cd backend && uv run pytest tests/integration/test_auth_controller.py -v`
Expected: FAIL

- [ ] **Step 2: controller / repository に CSRF と audit log を入れる**

```python
def assert_csrf(request: Request) -> None:
    cookie_token = request.cookies.get("csrf_token")
    header_token = request.headers.get("X-CSRF-Token")
    if not cookie_token or not header_token or cookie_token != header_token:
        raise HTTPException(status_code=403, detail="CSRF validation failed")
```

repository では login success / login failed / logout を `auth_audit_logs` に書き込む。

```python
await self._write_audit_log(
    user_id=user.id,
    session_id=session.id,
    event_type="login_success",
    ip_address=ip_address,
    user_agent=user_agent,
)
```

- [ ] **Step 3: full suite を通す**

Run: `cd backend && uv run pytest`
Expected: PASS

Run: `cd backend && uv run isort . --check-only && uv run yapf -dr app/`
Expected: 差分なし

- [ ] **Step 4: 手動の最低確認を行う**

Run: `curl -i http://localhost:8000/api/auth/csrf`
Expected: `Set-Cookie: csrf_token=...`

Run: `curl -i http://localhost:8000/api/auth/me`
Expected: `401 Unauthorized`

- [ ] **Step 5: コミットする**

```bash
git add backend/app/controllers/auth_controller.py backend/app/services/auth_repository.py backend/tests/integration/test_auth_controller.py
git commit -m "feat(auth): enforce csrf and audit auth events"
```
