# Auth DB / Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PostgreSQL と Alembic を認証基盤の正式な永続化レイヤとして導入し、`users` / `auth_sessions` / `auth_audit_logs` を安全に作成できる状態にする。

**Architecture:** 既存の `SQLModel` は継続し、接続は SQLAlchemy 2 系 async engine で扱う。migration は Alembic を canonical にし、初回 revision は autogenerate を起点にしつつ、`LOWER(email)` index や timezone-aware column のために必ず手で review する。integration test は PostgreSQL を正とし、test 間 cleanup は `TRUNCATE ... CASCADE` で保証する。

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy 2 async, Alembic, asyncpg, PostgreSQL 15+ (local/CI baseline 17), pytest, pytest-asyncio

**Dependencies:** [20260418-auth-structure.md](./20260418-auth-structure.md), [20260418-auth-delivery-notes.md](./20260418-auth-delivery-notes.md)

**Done When:** `manage.py db-upgrade` / `db-downgrade` が通り、初回 migration が PostgreSQL 上で安定し、auth 関連 integration test が test 間 clean で通る。あわせて `backend/AGENTS.md` に auth 領域の PostgreSQL 方針と Alembic 導線が反映される。

---

## File Structure

- Create: `backend/app/config/database.py`
- Create: `backend/app/libraries/database_engine.py`
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/auth_session.py`
- Create: `backend/app/models/auth_audit_log.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260418_0001_create_auth_tables.py`
- Create: `backend/tests/unit/config/test_database_settings.py`
- Create: `backend/tests/unit/libraries/test_database_engine.py`
- Create: `backend/tests/unit/models/test_auth_models.py`
- Create: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_auth_schema.py`
- Create: `docker/postgres/init/01-create-test-database.sql`
- Modify: `backend/app/config/__init__.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/manage.py`
- Modify: `backend/.env.example`
- Modify: `backend/AGENTS.md`
- Modify: `docker-compose.yaml`

## Task 1: 依存・設定・pytest 基盤を追加する

**Files:**
- Create: `backend/app/config/database.py`
- Create: `backend/tests/unit/config/test_database_settings.py`
- Modify: `backend/app/config/__init__.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env.example`

- [x] **Step 1: 依存追加と PostgreSQL スキーマ追加の承認を取る**

Run: なし
Expected: `uv add sqlalchemy alembic asyncpg` と `uv add --dev pytest pytest-asyncio`、および PostgreSQL 用の auth schema 追加についてユーザー承認が得られる。

- [x] **Step 2: 設定テストを先に書く**

```python
from app.config.database import DatabaseSettings


def test_database_settings_expose_urls_and_pool_defaults(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:app@localhost:5432/app",
    )
    monkeypatch.setenv(
        "ALEMBIC_DATABASE_URL",
        "postgresql://app:app@localhost:5432/app",
    )

    settings = DatabaseSettings()

    assert settings.DATABASE_URL == "postgresql+asyncpg://app:app@localhost:5432/app"
    assert settings.ALEMBIC_DATABASE_URL == "postgresql://app:app@localhost:5432/app"
    assert settings.DATABASE_POOL_SIZE == 10
    assert settings.DATABASE_MAX_OVERFLOW == 20
    assert settings.DATABASE_POOL_RECYCLE_SECONDS == 1800
    assert settings.DATABASE_ECHO is False
```

Run: `cd backend && uv run pytest tests/unit/config/test_database_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config.database'`

- [x] **Step 3: 設定面と pytest 設定を実装する**

`backend/app/config/database.py`:

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    ALEMBIC_DATABASE_URL: str = "postgresql://app:app@localhost:5432/app"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20
    DATABASE_POOL_RECYCLE_SECONDS: int = 1800
    DATABASE_ECHO: bool = False


def get_database_settings() -> DatabaseSettings:
    # test 側の monkeypatch.setenv() を効かせるため、module import 時に固定しない
    return DatabaseSettings()
```

`backend/pyproject.toml`:

```toml
[project]
dependencies = [
    "aiosqlite>=0.22.1",
    "alembic>=1.16.0",
    "asyncpg>=0.30.0",
    "fastapi[standard]>=0.128.0",
    "greenlet>=3.3.0",
    "injector>=0.24.0",
    "python-dotenv>=1.2.1",
    "sqlalchemy>=2.0.41",
    "sqlmodel>=0.0.31",
    "typer>=0.21.1",
]

[dependency-groups]
dev = [
    "isort>=7.0.0",
    "pytest>=8.4.0",
    "pytest-asyncio>=1.1.0",
    "yapf>=0.43.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
markers = [
    "integration: PostgreSQL-backed auth tests",
]
```

`backend/.env.example`:

```dotenv
ENVIRONMENT=local
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_RECYCLE_SECONDS=1800
DATABASE_ECHO=false
AUTH_SESSION_ABSOLUTE_TTL_SECONDS=604800
AUTH_SESSION_IDLE_TTL_SECONDS=86400
AUTH_RATE_LIMIT_WINDOW_SECONDS=900
AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP=5
AUTH_RATE_LIMIT_ATTEMPTS_PER_IP=20
```

補足:

- `aiosqlite` はこの auth 作業では削除しない
- 既存テンプレートの非 auth 領域がまだ SQLite 前提の可能性があるため、削除は別タスクに分離する

- [x] **Step 4: 設定テストを再実行する**

Run: `cd backend && uv run pytest tests/unit/config/test_database_settings.py -v`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add backend/pyproject.toml backend/.env.example backend/app/config/__init__.py backend/app/config/database.py backend/tests/unit/config/test_database_settings.py
git commit -m "feat(backend/auth): add database settings and pytest config"
```

## Task 2: async engine と Alembic ラッパー CLI を用意する

**Files:**
- Create: `backend/app/libraries/database_engine.py`
- Create: `backend/tests/unit/libraries/test_database_engine.py`
- Modify: `backend/manage.py`

- [x] **Step 1: engine factory の失敗テストを書く**

```python
from app.libraries.database_engine import build_engine_and_session_factory


def test_engine_factory_accepts_override_database_url():
    engine, session_factory = build_engine_and_session_factory(
        "postgresql+asyncpg://app:app@localhost:5432/app_test",
    )

    assert "postgresql+asyncpg://app:***@localhost:5432/app_test" in str(engine.url)
    assert session_factory is not None
```

Run: `cd backend && uv run pytest tests/unit/libraries/test_database_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.libraries.database_engine'`

- [x] **Step 2: engine / session factory と `manage.py` コマンドを実装する**

`backend/app/libraries/database_engine.py`:

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.database import get_database_settings


def build_engine_and_session_factory(database_url: str | None = None):
    database_settings = get_database_settings()
    target_url = database_url or database_settings.DATABASE_URL
    engine = create_async_engine(
        target_url,
        future=True,
        echo=database_settings.DATABASE_ECHO,
        pool_size=database_settings.DATABASE_POOL_SIZE,
        max_overflow=database_settings.DATABASE_MAX_OVERFLOW,
        pool_recycle=database_settings.DATABASE_POOL_RECYCLE_SECONDS,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory
```

`backend/manage.py`:

```python
@app.command()
def db_upgrade(revision: str = "head"):
    from alembic import command
    from alembic.config import Config

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, revision)


@app.command()
def db_downgrade(revision: str = "base"):
    from alembic import command
    from alembic.config import Config

    alembic_config = Config("alembic.ini")
    command.downgrade(alembic_config, revision)
```

- [x] **Step 3: unit test と CLI help を確認する**

Run: `cd backend && uv run pytest tests/unit/libraries/test_database_engine.py -v`
Expected: PASS

Run: `cd backend && uv run python manage.py --help`
Expected: `db-upgrade` と `db-downgrade` が表示される

- [x] **Step 4: Alembic 操作の正を文書化する**

Run: なし
Expected: 以後の計画では upgrade / downgrade の主コマンドを `uv run python manage.py db-upgrade` / `db-downgrade` に統一し、`uv run alembic ...` は revision 生成の補助用途だけにする。

- [ ] **Step 5: コミットする**

```bash
git add backend/manage.py backend/app/libraries/database_engine.py backend/tests/unit/libraries/test_database_engine.py
git commit -m "feat(backend/auth): add async database engine and alembic commands"
```

## Task 3: model registry と初回 migration を Alembic 運用前提で定義する

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/auth_session.py`
- Create: `backend/app/models/auth_audit_log.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260418_0001_create_auth_tables.py`
- Modify: `backend/app/models/__init__.py`

- [x] **Step 1: model registry の契約を先に固定する**

`backend/app/models/__init__.py` は、Alembic が `SQLModel.metadata` から全テーブルを見つけられるよう、table model を必ず集約 import する責務を持つ。

```python
from .auth_audit_log import AuthAuditLog
from .auth_session import AuthSession
from .status import Status
from .user import User

__all__ = [
    "AuthAuditLog",
    "AuthSession",
    "Status",
    "User",
]
```

Run: なし
Expected: 以後、新規 table model を追加したら `backend/app/models/__init__.py` にも必ず追記するルールが固定される。

- [x] **Step 2: timezone-aware model を実装する**

`backend/app/models/user.py`:

```python
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Column, DateTime, String
from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(
        sa_column=Column(String(length=320), nullable=False),
        index=False,
    )
    password_hash: str = Field(
        sa_column=Column(String(length=255), nullable=False),
    )
    is_active: bool = Field(
        sa_column=Column(Boolean, nullable=False, default=True),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
    updated_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
    last_login_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True),
        default=None,
    )
```

`backend/app/models/auth_session.py`:

```python
class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    session_token_hash: str = Field(
        sa_column=Column(String(length=64), nullable=False),
        index=False,
    )
    csrf_token_hash: str = Field(
        sa_column=Column(String(length=64), nullable=False),
    )
    created_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
    last_seen_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False, default=utcnow),
    )
    expires_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    revoked_at: datetime | None = Field(
        sa_column=Column(DateTime(timezone=True), nullable=True),
        default=None,
    )
    ip_address: str | None = Field(
        sa_column=Column(String(length=64), nullable=True),
        default=None,
    )
    user_agent: str | None = Field(
        sa_column=Column(String(length=512), nullable=True),
        default=None,
    )
```

- [x] **Step 3: Alembic は autogenerate 起点 + 手修正方針で作る**

`backend/alembic/env.py`:

```python
from sqlmodel import SQLModel

from app.config.database import get_database_settings
import app.models  # noqa: F401

database_settings = get_database_settings()
target_metadata = SQLModel.metadata
config.set_main_option("sqlalchemy.url", database_settings.ALEMBIC_DATABASE_URL)
```

revision 生成:

Run: `cd backend && uv run alembic revision --autogenerate -m "create auth tables"`
Expected: `backend/alembic/versions/` に baseline revision が生成される

生成後、必ず手で修正する点:

- `users.email` の plain unique を削り、`LOWER(email)` unique index に置き換える
- `session_token_hash` unique index を明示する
- `DateTime(timezone=True)` が migration 上でも `timezone=True` になっていることを確認する
- `auth_audit_logs.detail_json` は phase 1 では nullable の `JSONB` として明示する

修正後の migration 例:

```python
from sqlalchemy.dialects import postgresql


op.create_table(
    "users",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("email", sa.String(length=320), nullable=False),
    sa.Column("password_hash", sa.String(length=255), nullable=False),
    sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint("id"),
)
op.create_index(
    "uq_users_email_lower",
    "users",
    [sa.text("lower(email)")],
    unique=True,
)
op.create_index(
    "uq_auth_sessions_session_token_hash",
    "auth_sessions",
    ["session_token_hash"],
    unique=True,
)
op.create_table(
    "auth_audit_logs",
    sa.Column("id", sa.Uuid(), nullable=False),
    sa.Column("user_id", sa.Uuid(), nullable=True),
    sa.Column("session_id", sa.Uuid(), nullable=True),
    sa.Column("event_type", sa.String(length=64), nullable=False),
    sa.Column("ip_address", sa.String(length=45), nullable=True),
    sa.Column("user_agent", sa.String(length=512), nullable=True),
    sa.Column("detail_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
    sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"]),
    sa.PrimaryKeyConstraint("id"),
)
```

補足:

- `get_database_settings()` を毎回呼ぶ形にしておくと、`backend/tests/integration/conftest.py` の `monkeypatch.setenv()` と整合する
- `build_engine_and_session_factory()` は top-level import 時ではなく、呼び出し時に settings を読む前提で使う
- `auth_audit_logs.event_type` は PostgreSQL enum にせず `String(64)` に固定する。phase 1 では migration 変更コストより語彙の安定性を優先する

- [x] **Step 4: migration の up/down を通す**

Run: `cd backend && uv run python manage.py db-upgrade`
Expected: `head` まで migration が進む

Run: `cd backend && uv run python manage.py db-downgrade`
Expected: `base` まで戻る

Run: `cd backend && uv run python manage.py db-upgrade`
Expected: 再度 `head` まで上がる

- [ ] **Step 5: コミットする**

```bash
git add backend/alembic.ini backend/alembic backend/app/models/__init__.py backend/app/models/user.py backend/app/models/auth_session.py backend/app/models/auth_audit_log.py
git commit -m "feat(backend/auth): add auth models and initial alembic revision"
```

## Task 4: PostgreSQL integration fixture と test cleanup を整える

**Files:**
- Create: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_auth_schema.py`
- Modify: `docker-compose.yaml`

- [x] **Step 1: test fixture を先に書く**

```python
import asyncio
import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


def require_test_database_url() -> str:
    test_database_url = os.environ.get("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for auth integration tests")
    return test_database_url


async def wait_for_database(database_url: str) -> None:
    for _ in range(20):
        try:
            engine = create_async_engine(database_url, future=True)
            async with engine.connect() as connection:
                await connection.execute(text("select 1"))
            await engine.dispose()
            return
        except Exception:
            await asyncio.sleep(1)
    raise RuntimeError("PostgreSQL did not become ready for auth integration tests")


@pytest_asyncio.fixture(scope="session")
async def async_engine():
    database_url = require_test_database_url()
    await wait_for_database(database_url)
    engine = create_async_engine(database_url, future=True, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(autouse=True)
async def clean_auth_tables(async_engine) -> AsyncIterator[None]:
    yield
    async with async_engine.begin() as connection:
        await connection.execute(
            text(
                "TRUNCATE TABLE auth_audit_logs, auth_sessions, users CASCADE"
            )
        )


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncIterator[AsyncSession]:
    session_factory = async_sessionmaker(
        bind=async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
```

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_schema.py -v`
Expected: FAIL because tables areまだ無い

- [x] **Step 2: schema test は raw SQL を `execute()` で検証する**

```python
from sqlalchemy import text


async def test_auth_tables_exist(async_session):
    result = await async_session.execute(
        text(
            """
            select table_name
            from information_schema.tables
            where table_schema = 'public'
              and table_name in ('users', 'auth_sessions', 'auth_audit_logs')
            order by table_name
            """
        )
    )

    assert [row[0] for row in result.fetchall()] == [
        "auth_audit_logs",
        "auth_sessions",
        "users",
    ]


async def test_users_email_has_lower_unique_index(async_session):
    result = await async_session.execute(
        text(
            """
            select indexdef
            from pg_indexes
            where schemaname = 'public'
              and tablename = 'users'
            """
        )
    )

    index_definitions = [row[0] for row in result.fetchall()]
    assert any("lower(email)" in definition.lower() for definition in index_definitions)
```

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_schema.py -v`
Expected: FAIL until migration is applied

- [x] **Step 3: compose に PostgreSQL と test DB を追加する**

`docker-compose.yaml`:

```yaml
services:
  postgres:
    image: postgres:17-bookworm
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: app
    ports:
      - "${POSTGRES_PORT:-5432}:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data

  backend:
    depends_on:
      - postgres
    environment:
      DATABASE_URL: postgresql+asyncpg://app:app@postgres:5432/app
      ALEMBIC_DATABASE_URL: postgresql://app:app@postgres:5432/app

volumes:
  postgres_data:
```

補足:

- `TEST_DATABASE_URL` は local / CI で別途注入する
- `app_test` database を事前に作る方法は CI 手順へも明記する

- [x] **Step 4: PostgreSQL を起動して migration と integration test を通す**

Run: `docker compose up -d postgres`
Expected: `postgres` service が起動する

Run: `cd backend && uv run python manage.py db-upgrade`
Expected: auth schema が作成される

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_schema.py -v`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add docker-compose.yaml backend/tests/integration/conftest.py backend/tests/integration/test_auth_schema.py
git commit -m "feat(backend/auth): add postgres integration fixtures and schema tests"
```

## Task 5: backend ガイドを更新し、品質ゲートを通す

**Files:**
- Modify: `backend/AGENTS.md`

- [x] **Step 1: backend ガイドの認証例外を明記する**

`backend/AGENTS.md` には最低限次を反映する。

```md
- auth 領域の integration test は PostgreSQL を正とする
- `python manage.py db-upgrade` / `python manage.py db-downgrade` を migration の主要コマンドとする
- SQLite in-memory は auth 領域の DB integration test には使わない
```

- [x] **Step 2: backend 品質ゲートを通す**

Run: `cd backend && uv run pytest`
Expected: PASS

Run: `cd backend && uv run isort . --check-only && uv run yapf -dr app/`
Expected: 差分なし

- [x] **Step 3: 手順と文書の整合を見直す**

Run: なし
Expected: `manage.py`, `alembic/env.py`, `backend/AGENTS.md`, `documents/plans/20260418-auth-delivery-notes.md` の記述が矛盾していない。

- [ ] **Step 4: コミットする**

```bash
git add backend/AGENTS.md documents/plans/20260418-auth-delivery-notes.md
git commit -m "docs(backend/auth): align backend guide with postgres auth migration"
```
