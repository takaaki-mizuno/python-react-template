# Auth DB / Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** PostgreSQL と Alembic を認証基盤の正式な永続化レイヤとして導入し、`users` / `auth_sessions` / `auth_audit_logs` を安全に作成できる状態にする。

**Architecture:** 既存の `SQLModel` は継続し、接続は SQLAlchemy 2 系 async engine で扱う。`docker-compose.yaml` に PostgreSQL を追加し、backend は `DATABASE_URL` と `ALEMBIC_DATABASE_URL` を `pydantic-settings` 経由で読み、migration と integration test は PostgreSQL を正として動かす。

**Tech Stack:** FastAPI, SQLModel, SQLAlchemy 2 async, Alembic, asyncpg, PostgreSQL 17, pytest, pytest-asyncio

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
- Create: `backend/tests/integration/conftest.py`
- Create: `backend/tests/integration/test_auth_schema.py`
- Modify: `backend/app/config/__init__.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/manage.py`
- Modify: `backend/.env.example`
- Modify: `docker-compose.yaml`

## Task 1: DB 設定面と依存を追加する

**Files:**
- Create: `backend/app/config/database.py`
- Create: `backend/tests/unit/config/test_database_settings.py`
- Modify: `backend/app/config/__init__.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/.env.example`

- [ ] **Step 1: 依存追加と DB スキーマ変更の承認を取る**

Run: なし
Expected: `uv add sqlalchemy alembic asyncpg` と `uv add --dev pytest pytest-asyncio`、および PostgreSQL 用スキーマ追加の実施についてユーザー承認が得られる。

- [ ] **Step 2: 設定テストを先に書く**

```python
from app.config.database import DatabaseSettings


def test_database_settings_expose_runtime_and_migration_urls(monkeypatch):
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
```

Run: `cd backend && uv run pytest tests/unit/config/test_database_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.config.database'`

- [ ] **Step 3: 最小実装で設定面を通す**

```python
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    DATABASE_URL: str = "postgresql+asyncpg://app:app@localhost:5432/app"
    ALEMBIC_DATABASE_URL: str = "postgresql://app:app@localhost:5432/app"


database_settings = DatabaseSettings()
```

`backend/pyproject.toml` には次を追加する。

```toml
dependencies = [
    "aiosqlite>=0.22.1",
    "alembic>=1.16.0",
    "asyncpg>=0.30.0",
    "fastapi[standard]>=0.128.0",
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
```

`backend/.env.example` には最低限次を入れる。

```dotenv
ENVIRONMENT=local
DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app
```

- [ ] **Step 4: 設定テストを再実行する**

Run: `cd backend && uv run pytest tests/unit/config/test_database_settings.py -v`
Expected: PASS

- [ ] **Step 5: コミットする**

```bash
git add backend/pyproject.toml backend/.env.example backend/app/config/__init__.py backend/app/config/database.py backend/tests/unit/config/test_database_settings.py
git commit -m "feat(auth): add database settings surface"
```

## Task 2: async engine / session factory と migration CLI を用意する

**Files:**
- Create: `backend/app/libraries/database_engine.py`
- Create: `backend/tests/unit/libraries/test_database_engine.py`
- Modify: `backend/manage.py`

- [ ] **Step 1: engine factory の失敗テストを書く**

```python
from app.libraries.database_engine import build_engine_and_session_factory


def test_engine_factory_uses_runtime_database_url(monkeypatch):
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+asyncpg://app:app@localhost:5432/app",
    )

    engine, session_factory = build_engine_and_session_factory()

    assert "postgresql+asyncpg://app:***@localhost:5432/app" in str(engine.url)
    assert session_factory is not None
```

Run: `cd backend && uv run pytest tests/unit/libraries/test_database_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.libraries.database_engine'`

- [ ] **Step 2: 最小実装で engine と session factory を作る**

```python
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from app.config.database import database_settings


def build_engine_and_session_factory():
    engine = create_async_engine(
        database_settings.DATABASE_URL,
        future=True,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    return engine, session_factory
```

`backend/manage.py` には Alembic を呼ぶ最小コマンドを足す。

```python
@app.command()
def db_upgrade():
    from alembic import command
    from alembic.config import Config

    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")
```

- [ ] **Step 3: factory テストを通す**

Run: `cd backend && uv run pytest tests/unit/libraries/test_database_engine.py -v`
Expected: PASS

- [ ] **Step 4: CLI の import エラーがないことを確認する**

Run: `cd backend && uv run python manage.py --help`
Expected: `serve`, `version`, `db-upgrade` が表示される

- [ ] **Step 5: コミットする**

```bash
git add backend/manage.py backend/app/libraries/database_engine.py backend/tests/unit/libraries/test_database_engine.py
git commit -m "feat(auth): add async database engine and migration cli"
```

## Task 3: 認証テーブルと Alembic 初回 migration を定義する

**Files:**
- Create: `backend/app/models/user.py`
- Create: `backend/app/models/auth_session.py`
- Create: `backend/app/models/auth_audit_log.py`
- Create: `backend/alembic.ini`
- Create: `backend/alembic/env.py`
- Create: `backend/alembic/script.py.mako`
- Create: `backend/alembic/versions/20260418_0001_create_auth_tables.py`
- Create: `backend/tests/integration/test_auth_schema.py`
- Modify: `backend/app/models/__init__.py`

- [ ] **Step 1: PostgreSQL 上のテーブル存在を確認する失敗テストを書く**

```python
from sqlalchemy import text


async def test_auth_tables_exist(async_session):
    rows = await async_session.exec(
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

    assert [row[0] for row in rows.fetchall()] == [
        "auth_audit_logs",
        "auth_sessions",
        "users",
    ]
```

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run pytest tests/integration/test_auth_schema.py -v`
Expected: FAIL because fixtures and tables areまだ存在しない

- [ ] **Step 2: SQLModel と Alembic を実装する**

`backend/app/models/user.py` の最小形:

```python
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    email: str = Field(index=True, unique=True, max_length=320)
    password_hash: str = Field(max_length=255)
    is_active: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    updated_at: datetime = Field(default_factory=utcnow, nullable=False)
    last_login_at: datetime | None = Field(default=None, nullable=True)
```

`backend/app/models/auth_session.py` の最小形:

```python
class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    user_id: UUID = Field(foreign_key="users.id", nullable=False, index=True)
    session_token_hash: str = Field(index=True, unique=True, max_length=64)
    csrf_token_hash: str = Field(max_length=64)
    created_at: datetime = Field(default_factory=utcnow, nullable=False)
    last_seen_at: datetime = Field(default_factory=utcnow, nullable=False)
    expires_at: datetime = Field(nullable=False)
    revoked_at: datetime | None = Field(default=None, nullable=True)
    ip_address: str | None = Field(default=None, max_length=64)
    user_agent: str | None = Field(default=None, max_length=512)
```

`backend/alembic/env.py` では `SQLModel.metadata` を target metadata に使う。

```python
from sqlmodel import SQLModel

from app.config.database import database_settings
from app.models import AuthAuditLog, AuthSession, User

target_metadata = SQLModel.metadata
config.set_main_option("sqlalchemy.url", database_settings.ALEMBIC_DATABASE_URL)
```

migration 本体では 3 テーブルと必要 index を明示的に作る。

```python
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
op.create_index("ix_users_email", "users", ["email"], unique=True)
```

- [ ] **Step 3: migration を適用してテーブル確認テストを通す**

Run: `cd backend && uv run python manage.py db-upgrade`
Expected: Alembic が `head` まで進み、`users`, `auth_sessions`, `auth_audit_logs` が作成される

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run pytest tests/integration/test_auth_schema.py -v`
Expected: PASS

- [ ] **Step 4: downgrade / rerun の最低確認を行う**

Run: `cd backend && uv run alembic downgrade base && uv run alembic upgrade head`
Expected: downgrade / re-upgrade の両方が通る

- [ ] **Step 5: コミットする**

```bash
git add backend/alembic.ini backend/alembic backend/app/models backend/tests/integration/test_auth_schema.py
git commit -m "feat(auth): add postgres auth schema and alembic migration"
```

## Task 4: docker-compose と PostgreSQL integration test harness を整える

**Files:**
- Create: `backend/tests/integration/conftest.py`
- Modify: `docker-compose.yaml`

- [ ] **Step 1: PostgreSQL 起動前提の integration fixture を先に書く**

```python
import os
from collections.abc import AsyncIterator

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession


@pytest.fixture
async def async_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(
        os.environ["TEST_DATABASE_URL"],
        future=True,
        pool_pre_ping=True,
    )
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        yield session
    await engine.dispose()
```

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run pytest tests/integration/test_auth_schema.py -v`
Expected: FAIL if PostgreSQL が未起動

- [ ] **Step 2: compose に PostgreSQL と必要な環境変数を追加する**

`docker-compose.yaml` に次を追加する。

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

  frontend:
    environment:
      VITE_BACKEND_ORIGIN: http://backend:8000

volumes:
  postgres_data:
```

- [ ] **Step 3: PostgreSQL を起動して integration test を通す**

Run: `docker compose up -d postgres`
Expected: `postgres` service が healthy に近い状態で起動する

Run: `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app uv run pytest tests/integration/test_auth_schema.py -v`
Expected: PASS

- [ ] **Step 4: 品質ゲートで backend 側の最低確認を行う**

Run: `cd backend && uv run pytest`
Expected: PASS

Run: `cd backend && uv run isort . --check-only && uv run yapf -dr app/`
Expected: 差分なし

- [ ] **Step 5: コミットする**

```bash
git add docker-compose.yaml backend/tests/integration/conftest.py
git commit -m "feat(auth): add postgres compose and integration harness"
```
