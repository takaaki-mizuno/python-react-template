# Phase 7 レビュー指摘安定化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. この計画作成作業では `git add` / `git commit` / `git push` は実行しない。実装時もユーザーが明示するまで Git 操作は行わない。

**Goal:** Phase 5 / Phase 6 実装後レビューで確認された High / Medium 指摘を、実行可能なテストと正典同期まで含めて修正し、Alembic、DB CLI、auth session expiry、account deletion、frontend guard/cache の回帰を防ぐ。

**Architecture:** Phase 7 は新機能を追加しない。まず出典レビューと backlog の traceability を固定し、Alembic / migration / CLI の入口を直す。その後、auth repository の冪等性を unit では契約、integration では同時実行 race として検証し、最後に frontend regression と docs / quality gate を正典へ揃える。

**Tech Stack:** Python 3.12、FastAPI、SQLModel、SQLAlchemy、Alembic、Typer、PostgreSQL、pytest、ruff、isort、YAPF、mypy、React 19、TypeScript 5.7、TanStack Router、TanStack Query、Vitest、Docker

---

## 出典

- Phase 5 / Phase 6 コードレビュー: `documents/reviews/20260804-phase5-phase6-code-review.md`
- Phase 7 計画レビュー: `documents/reviews/20260804-phase7-plan-review.md`
- Phase 7 計画再レビュー: `documents/reviews/20260804-phase7-plan-rereview.md`
- Phase 7 計画三次レビュー: `documents/reviews/20260804-phase7-plan-third-review.md`
- Phase 8 backlog: `documents/plans/20260804-phase8-hardening-backlog.md`

## 上流コードレビュー ID 対応表

| Review ID | Phase 7 対応 |
|---|---|
| U7-1 | Task 1 で Alembic URL interpolation を修正する。 |
| U7-2 | Task 2 / Task 7 で `db-downgrade --revision` の CLI / docs を揃える。 |
| U7-3 | Task 3 で `issued_at` expiry mutation guard を追加する。 |
| U7-4 | Task 4 / Task 7 で migration downgrade の明示 error と docs を追加する。 |
| U7-5 | Task 5 で `mark_user_deleted()` を repository layer で冪等化する。 |
| U7-6 | Task 6 で OAuth-only account deletion caveat を docs に追加する。 |
| U7-7 | Task 7 / Task 9 で README と品質ゲートを正典へ同期する。 |
| U7-8 | Task 8 で `/app/settings` guard / cache regression を route test へ追加する。 |

## 計画レビュー ID 対応表

| Review ID | Phase 7 対応 |
|---|---|
| C7-A | 本計画の出典節と ID 対応表で traceability を確保する。 |
| C7-B | Task 5 で `CapturingSession` の rowcount test double 改修を必須化する。 |
| C7-C | Task 5 で逐次冪等 test と同時実行 integration test を分け、repository layer の範囲を明記する。 |
| C7-D | Task 4 で offline migration は preflight DB query だけを skip し、downgrade SQL は維持する。 |
| C7-E | Task 4 / Task 7 で downgrade の不可逆性を email 重複だけでなく dropped columns / type rollback まで含めて記述する。 |
| C7-F | Task 7 / Task 9 の検証を `rtk rg` に変更し、修正前から通る偽グリーンを防ぐ。 |
| C7-G | Task 1 で実 Alembic `Config` を使う helper test と `set_main_option` source guard を追加する。 |
| C7-H | Task 7 / Task 9 に `db-upgrade`、integration、`db-check`、Docker gate を含める。 |
| C7-I | Task 5 / Task 6 で既存の `mark_user_deleted()` 契約記述を書き換える。 |
| C7-J | Task 3 を mutation guard と明記し、`issued_at + absolute TTL` の厳密比較へ強化する。 |
| C7-K | Task 8 で route test 側に失敗時 cache 保持を追加し、401 mock は error envelope に揃える。 |
| C7-L | Task 2 で positional downgrade 廃止を破壊的 CLI 変更として明記し、Typer の既存 style に合わせる。Task 4 smoke に `DATABASE_URL` と scratch data 作成手順を書く。 |
| C7-M | Phase 8 backlog 文書を追加し、完了条件を grep 可能な語句へ寄せる。 |
| R7-1 | Task 9.6 の `npm run check$` 検索対象を README に限定し、`frontend/AGENTS.md` の正しい整形コマンド説明を誤検出しないようにする。 |
| R7-2 | 上流コードレビューを `documents/reviews/20260804-phase5-phase6-code-review.md` として追加し、U7 ID 対応表を本計画に追加する。 |
| R7-3 | Task 5 に transaction 内 integration test と `refresh()` 方針を追加する。 |
| R7-4 | Task 4.4 に scratch DB 作成手順と heredoc が使えない場合の `psql -c` 代替を追加する。 |
| R7-5 | Task 9.6 の docs positive check を語句別 `rtk rg` に分ける。 |
| R7-6 | Task 8.2 を既存 error test 拡張方針にし、`queryKeys.auth.me` と unrelated cache の両方を確認する。 |
| R7-7 | Task 1 の source guard に `build_alembic_engine_section` 使用確認を追加する。 |
| T7-1 | Task 7.4 / Task 9.6 の `TEST_DATABASE_URL` negative grep を `skipされる` に絞り、正しい「skip ではなく fail」文を誤検出しないようにする。 |
| T7-2 | Task 9.6 の negative grep を意味別に分割し、`backend/AGENTS.md` の正しい記述を誤検出しないようにする。 |
| T7-3 | Task 5.7 の transaction 内 test で、同じ transaction session に user を事前 load してから `mark_user_deleted()` を呼ぶ。 |
| T7-4 | Task 5 で既存 missing user unit test の `CapturingSession` を `exec_rowcount=0` に更新する。 |
| T7-5 | Task 8.2 の cache assertion を account deletion API error 全ケースで無条件に実行する。 |

## 精査結果

### Phase 7 で扱う確認済み項目

1. `backend/alembic/env.py` の `config.set_main_option("sqlalchemy.url", get_database_url())` は、`DATABASE_URL` に `%` を含む percent-encoded password が入ると ConfigParser interpolation で起動不能になる。
2. `backend/manage.py` の `db-downgrade` は positional argument だが、`README.md` と `.claude/settings.local.json` は `--revision` を前提にしている。
3. `AuthSession.issued_at` の実装は正しいが、`created_at` mutation を検出する test が弱い。
4. Phase 5 migration downgrade は、削除済み email 再登録後に旧 global unique index を復元できない。加えて、重複がなくても `deleted_at` / `issued_at` / `updated_at` / INET 型情報を失う不可逆 operation である。
5. `mark_user_deleted()` は `deleted_at IS NULL` guard がなく、同時実行 race で `USER_MARKED_DELETED` audit log が二重化し得る。逐次 2 回目の public `DELETE /api/auth/me` は session revoke により通常到達しないため、リスクの中心は同時実行である。
6. OAuth-only account deletion は Phase 6 の暫定方針として `confirmEmail` のみを許可している。session と CSRF token の両方が奪取された場合の不可逆削除リスクを正典に明記する。
7. `README.md` の品質ゲートは root / backend / frontend `AGENTS.md` より弱い。
8. `/app/settings` は `_authenticated` pathless layout 配下で guard はあるが、route-specific regression test がない。account deletion 失敗時 cache 保持は実アプリ経路で検証する。

### Phase 7 外

`documents/plans/20260804-phase8-hardening-backlog.md` に移した。Phase 7 では session replay audit 増幅、deleted / inactive 検知時の全 session revoke、revoked session pruning、OAuth provider reauthentication、削除猶予期間、restore API、Retry-After UI、form error live clear は実装しない。

## 変更予定ファイル

### 作成済み / 作成するファイル

- Created: `documents/reviews/20260804-phase5-phase6-code-review.md`
  - Phase 7 の上流コードレビュー ID。
- Created: `documents/reviews/20260804-phase7-plan-review.md`
  - Phase 7 計画レビューの出典 ID。
- Created: `documents/reviews/20260804-phase7-plan-rereview.md`
  - Phase 7 計画再レビューの出典 ID。
- Created: `documents/reviews/20260804-phase7-plan-third-review.md`
  - Phase 7 計画三次レビューの出典 ID。
- Created: `documents/plans/20260804-phase8-hardening-backlog.md`
  - Phase 7 外 hardening 項目の受け皿。
- Create: `backend/app/bootstrap/alembic_config.py`
  - Alembic `Config` から online engine 用 dict を作る helper。
- Create: `backend/tests/unit/test_alembic_config.py`
  - `%` URL と `set_main_option` source guard の regression test。

### 変更するファイル

- Modify: `backend/alembic/env.py`
- Modify: `backend/manage.py`
- Modify: `backend/alembic/versions/20260803_0003_phase5_auth_operational_fields.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/services/test_auth_repository.py`
- Modify: `backend/tests/integration/services/test_auth_repository.py`
- Modify: `frontend/src/routes/app.settings.test.tsx`
- Modify: `README.md`
- Modify: `.claude/settings.local.json`
- Modify: `backend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/plans/20260803-phase6-account-deletion-handoff.md`

## Task 1: Alembic URL interpolation を実 Config 経由で回避する

**Files:**
- Create: `backend/app/bootstrap/alembic_config.py`
- Create: `backend/tests/unit/test_alembic_config.py`
- Modify: `backend/alembic/env.py`

- [x] **Step 1.1: 実 Alembic Config を使う failing test を追加する**

`backend/tests/unit/test_alembic_config.py` を作成する。

```python
from pathlib import Path

from alembic.config import Config as AlembicConfig

from app.bootstrap.alembic_config import build_alembic_engine_section


BACKEND_DIR = Path(__file__).resolve().parents[2]


def test_build_alembic_engine_section_preserves_percent_encoded_database_url() -> None:
    config = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    database_url = "postgresql+asyncpg://app:p%40ss@localhost:5432/app_test"

    section = build_alembic_engine_section(config, database_url)

    assert section["script_location"].endswith("/alembic")
    assert section["sqlalchemy.url"] == database_url
    assert "%40" in section["sqlalchemy.url"]


def test_alembic_env_does_not_use_configparser_url_setter() -> None:
    env_source = (BACKEND_DIR / "alembic" / "env.py").read_text()

    assert "set_main_option" not in env_source
    assert "build_alembic_engine_section" in env_source
```

Run:

```bash
# workdir: backend
rtk uv run pytest tests/unit/test_alembic_config.py -q
```

Expected: `build_alembic_engine_section` 未定義、または `set_main_option` 残存で FAIL。

- [x] **Step 1.2: Alembic 専用 helper を作成する**

`backend/app/bootstrap/alembic_config.py` を作成する。

```python
from alembic.config import Config as AlembicConfig


def build_alembic_engine_section(
    config: AlembicConfig,
    database_url: str,
) -> dict[str, str]:
    section = dict(config.get_section(config.config_ini_section) or {})
    section["sqlalchemy.url"] = database_url
    return section
```

- [x] **Step 1.3: `env.py` から `set_main_option()` を削除する**

`backend/alembic/env.py` を変更する。

```python
from app.bootstrap.alembic_config import build_alembic_engine_section


async def run_async_migrations() -> None:
    connectable = async_engine_from_config(
        build_alembic_engine_section(config, get_database_url()),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
```

`config.set_main_option("sqlalchemy.url", get_database_url())` は削除する。offline migration の `context.configure(url=get_database_url(), ...)` は ConfigParser interpolation を通らないため維持する。

- [x] **Step 1.4: regression を確認する**

Run:

```bash
# workdir: backend
rtk uv run pytest tests/unit/test_alembic_config.py -q
rtk rg -n "set_main_option" alembic/env.py
```

Expected:
- pytest PASS。
- `rtk rg` は no matches。

## Task 2: `db-downgrade --revision` を CLI 契約へ昇格する

**Files:**
- Modify: `backend/manage.py`
- Modify: `backend/tests/unit/test_manage.py`
- Modify: `README.md`
- Modify: `.claude/settings.local.json`

**Compatibility note:** この変更は `uv run python manage.py db-downgrade base` という positional 呼び出しを壊す。README と allowlist がすでに named option を前提にしているため、Phase 7 では `--revision` を正にする。

- [x] **Step 2.1: failing CLI test を追加する**

`backend/tests/unit/test_manage.py` に追加する。

```python
def test_db_downgrade_accepts_revision_option(monkeypatch):
    calls = []
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://app:app@localhost:5432/app_test")

    class ConfigStub:

        def __init__(self, path):
            calls.append(("config", path))

    class CommandStub:

        @staticmethod
        def downgrade(config, revision):
            calls.append(("downgrade", revision, config))

    monkeypatch.setattr(manage, "AlembicConfig", ConfigStub)
    monkeypatch.setattr(manage, "alembic_command", CommandStub)

    result = CliRunner().invoke(manage.app, ["db-downgrade", "--revision", "base"])

    assert result.exit_code == 0
    assert calls[1][0] == "downgrade"
    assert calls[1][1] == "base"
```

Run:

```bash
# workdir: backend
rtk uv run pytest tests/unit/test_manage.py -q
```

Expected: 現行 CLI では `No such option: --revision` で FAIL。

- [x] **Step 2.2: Typer の既存 style に合わせて required option にする**

`backend/manage.py` を変更する。`db_revision(message: Annotated[str, typer.Option(...)])` と同じく、required value は default を置かない。

```python
@app.command("db-downgrade")
def db_downgrade(
    revision: Annotated[
        str,
        typer.Option("--revision", "-r", help="Target Alembic revision to downgrade to."),
    ],
) -> None:
    _get_explicit_database_settings("db-downgrade")
    alembic_command.downgrade(_alembic_config(), revision)
```

- [x] **Step 2.3: docs / allowlist を named option へ揃える**

`README.md` は `db-downgrade --revision -1` と `db-downgrade --revision base` に統一する。`--revision=-1` も Click としては動くが、Phase 7 では空白区切りへ表記統一するだけであり、機能修正の根拠にはしない。

`.claude/settings.local.json` の `db-downgrade --revision base` は Task 2.2 後に実行可能になるため維持する。確認した結果、positional downgrade の allowlist は存在せず変更不要だった。

- [x] **Step 2.4: CLI help と unit test を確認する**

Run:

```bash
# workdir: backend
rtk uv run pytest tests/unit/test_manage.py -q
rtk uv run python manage.py db-downgrade --help
```

Expected:
- pytest PASS。
- help の Options に `--revision` が表示される。

## Task 3: `issued_at` expiry の mutation guard を厳密化する

**Files:**
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`

- [x] **Step 3.1: mutation guard test を追加する**

この test は現行実装で PASS する regression guard であり、failing TDD test ではない。`auth_usecase.utcnow` を固定し、`created_at` ではなく `issued_at + AUTH_SESSION_ABSOLUTE_TTL_SECONDS` に一致することを直接 assert する。

```python
@pytest.mark.asyncio
async def test_authenticate_session_refreshes_expiry_from_issued_at_not_created_at(
    monkeypatch,
):
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
```

If mutated to `auth_session.created_at`, expected expiry becomes 9 days 23 hours in the past and this test fails. If mutated to idle-only expiry, expected expiry becomes `fixed_now + 86400 seconds` and this test fails.

- [x] **Step 3.2: 対象 test を実行する**

Run:

```bash
# workdir: backend
rtk uv run pytest tests/unit/usecases/test_auth_usecase.py -q
```

Expected: PASS。

## Task 4: Phase 5 migration downgrade の不可逆性を明示する

**Files:**
- Modify: `backend/alembic/versions/20260803_0003_phase5_auth_operational_fields.py`
- Modify: `README.md`
- Modify: `documents/references/backend-app-structure.md`

- [x] **Step 4.1: offline-safe preflight helper を追加する**

`downgrade()` の先頭で呼ぶ helper を同じ migration file に追加する。offline mode では DB query だけを skip し、その後の downgrade operations は通常どおり SQL として出す。

```python
def _assert_no_deleted_email_reuse_for_downgrade() -> None:
    if op.get_context().as_sql:
        return
    connection = op.get_bind()
    duplicated_email = connection.execute(
        sa.text(
            """
            SELECT lower(email) AS email_key
            FROM users
            GROUP BY lower(email)
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).fetchone()
    if duplicated_email is not None:
        raise RuntimeError(
            "Cannot downgrade 20260803_0003 after deleted email reuse. "
            "The previous schema requires lower(email) to be globally unique."
        )
```

`downgrade()` の先頭に追加する。

```python
def downgrade() -> None:
    _assert_no_deleted_email_reuse_for_downgrade()
    op.drop_index("uq_users_email_lower_active", table_name="users")
```

- [x] **Step 4.2: migration コメントを追加する**

Preflight helper の直前に WHY コメントを置く。

```python
# Deleted email reuse is a Phase 5 feature. Once duplicate lower(email)
# values exist across deleted and active users, the previous global unique
# index cannot be restored without deleting or rewriting user data. Offline
# SQL generation cannot inspect data, so it emits downgrade SQL without this
# runtime guard.
```

- [x] **Step 4.3: docs に不可逆性を正確に書く**

`README.md` と `documents/references/backend-app-structure.md` に次の内容を入れる。

```markdown
Phase 5 migration `20260803_0003` の downgrade は destructive です。
削除済み email を同じ DB で再登録済みの場合、旧 schema の global
`lower(email)` unique index を復元できないため `Cannot downgrade 20260803_0003 after deleted email reuse` で停止します。重複 email がない
場合でも、`users.deleted_at`、`auth_sessions.issued_at`、
`auth_sessions.updated_at`、PostgreSQL `INET` 型への変更は rollback 時に失われます。
```

- [x] **Step 4.4: scratch DB smoke を実行する**

Task 2 完了後に実行する。共有 DB / 本番 DB では実行しない。

Scratch DB を作成する。既に存在する場合は保持対象データがないことを確認してから、別名の scratch DB を使うか手動で削除する。

```bash
# workdir: repo root
PGPASSWORD=app rtk psql -h 127.0.0.1 -p "${APP_POSTGRES_PORT:-5432}" -U app -d postgres \
  -c "CREATE DATABASE app_phase7_scratch;"
```

```bash
# workdir: backend
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT:-5432}/app_phase7_scratch" \
  rtk uv run python manage.py db-upgrade --revision head
```

Scratch DB に duplicate lower(email) を作る。

```bash
# workdir: backend
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT:-5432}/app_phase7_scratch" \
  rtk uv run python - <<'PY'
import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


async def main() -> None:
    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.begin() as connection:
        await connection.execute(
            text(
                """
                INSERT INTO users
                  (id, email, password_hash, is_active, created_at, updated_at, deleted_at)
                VALUES
                  ('00000000-0000-0000-0000-000000000101',
                   'reuse@example.com', 'hash', true, now(), now(), now()),
                  ('00000000-0000-0000-0000-000000000102',
                   'reuse@example.com', 'hash', true, now(), now(), NULL)
                """
            )
        )
    await engine.dispose()


asyncio.run(main())
PY
```

If heredoc through `rtk uv run python -` fails, use `psql -c` instead.

```bash
# workdir: repo root
PGPASSWORD=app rtk psql -h 127.0.0.1 -p "${APP_POSTGRES_PORT:-5432}" -U app -d app_phase7_scratch \
  -c "INSERT INTO users (id, email, password_hash, is_active, created_at, updated_at, deleted_at) VALUES ('00000000-0000-0000-0000-000000000101', 'reuse@example.com', 'hash', true, now(), now(), now()), ('00000000-0000-0000-0000-000000000102', 'reuse@example.com', 'hash', true, now(), now(), NULL);"
```

Then:

```bash
# workdir: backend
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT:-5432}/app_phase7_scratch" \
  rtk uv run python manage.py db-downgrade --revision 20260802_0002
```

Expected: `Cannot downgrade 20260803_0003 after deleted email reuse` で停止する。

## Task 5: `mark_user_deleted()` を repository layer で冪等化する

**Files:**
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/tests/unit/services/test_auth_repository.py`
- Modify: `backend/tests/integration/services/test_auth_repository.py`
- Modify: `backend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`

**Scope note:** Phase 7 で冪等化するのは `AuthRepository.mark_user_deleted()` の audit 作成契約である。`AccountDeletionUsecase.delete_account()` 全体は引き続き `delete_all_for_owner()` と `revoke_sessions_for_user()` を呼ぶため、usecase 全体を idempotent API と呼ばない。

- [x] **Step 5.1: test double の rowcount を制御可能にする**

`backend/tests/unit/services/test_auth_repository.py` の `CapturingSession` を変更する。

```python
class CapturingSession:

    def __init__(self, get_result: object | None = None, exec_rowcount: int = 2) -> None:
        self.statements = []
        self.added = []
        self.get_result = get_result
        self.exec_rowcount = exec_rowcount
        self.commit_calls = 0
        self.refresh_calls = 0

    async def exec(self, statement):
        self.statements.append(statement)
        return ResultStub(rowcount=self.exec_rowcount)
```

- [x] **Step 5.2: already-deleted unit test を追加する**

```python
@pytest.mark.asyncio
async def test_mark_user_deleted_does_not_audit_when_user_already_deleted() -> None:
    user_id = uuid4()
    first_deleted_at = utcnow() - timedelta(minutes=5)
    second_deleted_at = utcnow()
    user = User(
        id=user_id,
        email="deleted@example.com",
        password_hash="hashed",
        deleted_at=first_deleted_at,
    )
    session = CapturingSession(user, exec_rowcount=0)
    repository = AuthRepository(unit_of_work=CapturingUnitOfWork(session))

    deleted_user = await repository.mark_user_deleted(
        user_id,
        second_deleted_at,
        session_id=None,
        ip_address=None,
    )

    assert deleted_user.deleted_at == first_deleted_at
    assert all(
        getattr(instance, "event_type", None) != AuthEventType.USER_MARKED_DELETED
        for instance in session.added
    )
```

This unit test verifies repository branching against the test double. Real race safety is verified by Step 5.5.

- [x] **Step 5.3: 既存 missing user unit test を rowcount=0 経路へ更新する**

`test_mark_user_deleted_raises_user_not_found_for_missing_user()` は、実 DB の missing user と同じく UPDATE rowcount が 0 になる経路を検証する。

```python
@pytest.mark.asyncio
async def test_mark_user_deleted_raises_user_not_found_for_missing_user() -> None:
    user_id = uuid4()
    repository = AuthRepository(
        unit_of_work=CapturingUnitOfWork(CapturingSession(None, exec_rowcount=0))
    )

with pytest.raises(UserNotFoundError):
    await repository.mark_user_deleted(user_id, utcnow(), session_id=None, ip_address=None)
```

`test_mark_user_deleted_records_required_audit_log()` は PK update の成功経路に合わせて `CapturingSession(user, exec_rowcount=1)` を明示する。`CapturingSession` の default `exec_rowcount=2` は multi-row delete / revoke 系の既存 unit tests 用に維持する。

- [x] **Step 5.4: repository implementation を rowcount 判定へ変更する**

`backend/app/services/auth_repository.py` の `mark_user_deleted()` を変更する。

```python
async def mark_user_deleted(
    self,
    user_id: UUID,
    deleted_at: datetime,
    *,
    session_id: UUID | None,
    ip_address: str | None,
) -> User:
    """Mark a user deleted once and record exactly one deletion audit event."""
    async with self._unit_of_work.session_scope() as session:
        result = await session.exec(
            update(User)
            .where(
                col(User.id) == user_id,
                col(User.deleted_at).is_(None),
            )
            .values(deleted_at=deleted_at, updated_at=deleted_at)
        )
        if int(result.rowcount or 0) == 0:
            existing_user = await session.get(User, user_id)
            if existing_user is None:
                raise UserNotFoundError(user_id)
            return existing_user

        session.add(
            AuthAuditLog(
                user_id=user_id,
                session_id=session_id,
                event_type=AuthEventType.USER_MARKED_DELETED,
                ip_address=ip_address,
                created_at=deleted_at,
            )
        )
        await self._persist(session)
        deleted_user = await session.get(User, user_id)
        if deleted_user is None:
            # Defensive guard for an inconsistent rowcount / identity map state.
            raise UserNotFoundError(user_id)
        return deleted_user
```

SQLAlchemy 2.0 の ORM-enabled UPDATE は `synchronize_session="auto"` により、評価可能な WHERE では同一 session の identity map を同期する。rowcount=1 後の `session.get()` は返却用 `User` の取得と defensive guard のために残し、追加の `refresh()` は行わない。

- [x] **Step 5.5: 同時実行 integration test を追加する**

`backend/tests/integration/services/test_auth_repository.py` に `import asyncio` と `from app.models.auth_event_type import AuthEventType` を追加し、test を追加する。

```python
async def test_mark_user_deleted_concurrent_calls_audit_once(async_session_factory):
    user_repository = AuthRepository(
        unit_of_work=UnitOfWork(session_factory=async_session_factory)
    )
    user = await user_repository.create_user("delete-race@example.com", "hash")
    first_repository = AuthRepository(
        unit_of_work=UnitOfWork(session_factory=async_session_factory)
    )
    second_repository = AuthRepository(
        unit_of_work=UnitOfWork(session_factory=async_session_factory)
    )

    await asyncio.gather(
        first_repository.mark_user_deleted(
            user.id,
            utcnow(),
            session_id=None,
            ip_address="127.0.0.1",
        ),
        second_repository.mark_user_deleted(
            user.id,
            utcnow(),
            session_id=None,
            ip_address="127.0.0.1",
        ),
    )

    async with async_session_factory() as session:
        audit_logs = (
            await session.exec(
                select(AuthAuditLog).where(
                    AuthAuditLog.user_id == user.id,
                    AuthAuditLog.event_type == AuthEventType.USER_MARKED_DELETED,
                )
            )
        ).all()

    assert len(audit_logs) == 1
```

- [x] **Step 5.6: 逐次 already-deleted integration test を追加する**

同じ file に追加する。

```python
async def test_mark_user_deleted_sequential_calls_keep_first_deleted_at_and_audit_once(
    auth_repository,
    async_session,
):
    user = await auth_repository.create_user("delete-once@example.com", "hash")
    first_deleted_at = utcnow()
    second_deleted_at = first_deleted_at + timedelta(seconds=1)

    first_result = await auth_repository.mark_user_deleted(
        user.id,
        first_deleted_at,
        session_id=None,
        ip_address="127.0.0.1",
    )
    second_result = await auth_repository.mark_user_deleted(
        user.id,
        second_deleted_at,
        session_id=None,
        ip_address="127.0.0.1",
    )

    audit_logs = (
        await async_session.exec(
            select(AuthAuditLog).where(
                AuthAuditLog.user_id == user.id,
                AuthAuditLog.event_type == AuthEventType.USER_MARKED_DELETED,
            )
        )
    ).all()

    assert first_result.deleted_at == first_deleted_at
    assert second_result.deleted_at == first_deleted_at
    assert len(audit_logs) == 1
```

- [x] **Step 5.7: transaction 内の返却値を integration test で固定する**

同じ file に追加する。`UnitOfWork.transaction()` 内で同じ repository を呼び、先に同じ transaction session へ user を load して identity map に載せる。その後に `mark_user_deleted()` を呼び、transaction session 共有時も返却 `User.deleted_at` が更新済みであることを確認する。この test は `deleted_at IS NULL` guard と rowcount 分岐の契約を補完し、`refresh()` 呼び出し自体を守る test ではない。

```python
async def test_mark_user_deleted_returns_updated_user_inside_transaction(
    async_session_factory,
):
    unit_of_work = UnitOfWork(session_factory=async_session_factory)
    repository = AuthRepository(unit_of_work=unit_of_work)
    user = await repository.create_user("delete-in-transaction@example.com", "hash")
    deleted_at = utcnow()

    async with unit_of_work.transaction():
        loaded_user = await repository.find_user_by_id_for_authentication(user.id)
        assert loaded_user is not None
        assert loaded_user.deleted_at is None

        deleted_user = await repository.mark_user_deleted(
            user.id,
            deleted_at,
            session_id=None,
            ip_address="127.0.0.1",
        )

    assert deleted_user.deleted_at == deleted_at
```

- [x] **Step 5.8: 正典の既存記述を書き換える**

`backend/AGENTS.md` の Phase 5 / Phase 6 の既存文を「常に作成」から「最初の削除時だけ作成」へ書き換える。追記だけにしない。

```markdown
- `mark_user_deleted()`、`revoke_sessions_for_user()`、`USER_MARKED_DELETED` は Phase 6 account deletion / role revocation / password change 用の契約である。`mark_user_deleted()` は `deleted_at IS NULL` の user を初めて削除状態にした場合だけ `USER_MARKED_DELETED` audit log を同じ repository 操作内で作成する。すでに削除済みの user では `deleted_at` を上書きせず、audit log も追加しない。
```

`documents/references/backend-app-structure.md` も同じ契約へ書き換える。

- [x] **Step 5.9: 対象 test を実行する**

Run:

```bash
# workdir: backend
rtk uv run pytest tests/unit/services/test_auth_repository.py tests/integration/services/test_auth_repository.py -q
```

Expected: PASS。

## Task 6: OAuth-only account deletion の暫定リスクを正典へ明記する

**Files:**
- Modify: `backend/AGENTS.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/plans/20260803-phase6-account-deletion-handoff.md`

- [x] **Step 6.1: backend AGENTS に caveat を追加する**

Phase 6 Account Deletion 規約に追加する。

```markdown
- OAuth-only user (`password_hash IS NULL`) の削除は OAuth provider reauthentication 実装まで `confirmEmail` のみで許可している。`confirmEmail` は認証要素ではないため、session と CSRF token の両方が奪取された場合は追加の本人確認なしに不可逆削除できる。顧客データ、課金、業務データを扱う派生プロジェクトでは、account deletion 公開前に OAuth reauthentication、削除猶予期間、または復元 workflow を設計する。
```

- [x] **Step 6.2: reference に同じ判断基準を追加する**

`documents/references/backend-app-structure.md` に `OAuth-only account deletion caveat` という見出しを追加し、次の grep 可能な語句を含める。

```markdown
OAuth-only account deletion caveat: `confirmEmail` is not an authentication factor.
```

- [x] **Step 6.3: Phase 6 plan にレビュー後追記を残す**

`documents/plans/20260803-phase6-account-deletion-handoff.md` の末尾に `Phase 7 review note` を追加し、Phase 6 の暫定許容と Phase 7 での caveat 追加を記録する。

## Task 7: README / allowlist / 品質ゲートを正典と同期する

**Files:**
- Modify: `README.md`
- Modify: `.claude/settings.local.json`

- [x] **Step 7.1: DB CLI 例を実行可能な形に揃える**

`README.md` の例を次の形に統一する。

```bash
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app" \
  uv run python manage.py db-upgrade --revision head

DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app" \
  uv run python manage.py db-downgrade --revision -1
```

`.claude/settings.local.json` は Task 2 後の CLI で実行可能な allowlist だけにする。確認した結果、既存 allowlist はすでに `db-downgrade --revision base` で、削除対象の positional entry はなかったため変更不要だった。

- [x] **Step 7.2: integration test 説明を fail-fast 前提へ更新する**

`README.md` に次の意味を明記する。

```markdown
Backend integration test は `TEST_DATABASE_URL` が未設定の場合 skip ではなく fail します。
実行前に PostgreSQL を起動し、`DATABASE_URL` と `TEST_DATABASE_URL` を明示してください。
```

- [x] **Step 7.3: README 品質ゲートを root AGENTS と同じ強さにする**

`README.md` の品質ゲートを次へ寄せる。

```bash
# workdir: backend
uv run ruff check .
uv run isort . --check-only
uv run yapf -dr app/ tests/ alembic/ manage.py
uv run mypy app manage.py
uv run pytest tests/unit
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app_test" \
  uv run python manage.py db-upgrade --revision head
TEST_DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app_test" \
  uv run pytest tests/integration -q -ra
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT}/app_test" \
  uv run python manage.py db-check
```

```bash
# workdir: frontend
npm run check:ci
npm test
npm run build
```

```bash
# workdir: repo root
docker compose config
docker build --target runtime -t python-react-template-runtime .
docker build --target backend-dev -t python-react-template-backend-dev .
```

- [x] **Step 7.4: docs grep を `rg` で確認する**

Run:

```bash
# workdir: repo root
rtk rg -n "skipされる|npm run check$|db-downgrade --revision=" README.md
```

Expected: no matches。

## Task 8: Frontend route regression を実アプリ経路で守る

**Files:**
- Modify: `frontend/src/routes/app.settings.test.tsx`

- [x] **Step 8.1: `/app/settings` 未認証 redirect test を追加する**

401 mock は error envelope 形式にする。

```tsx
test('未認証で /app/settings を開くと login へ redirect する', async () => {
  vi.stubGlobal(
    'fetch',
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          error: { code: 'UNAUTHORIZED', message: 'Unauthorized' },
        }),
        {
          status: 401,
          headers: { 'Content-Type': 'application/json' },
        },
      ),
    ),
  )

  const { router } = renderWithRouter({ initialEntries: ['/app/settings'] })

  await waitFor(() => {
    expect(router.state.location.pathname).toBe('/login')
  })
  expect(router.state.location.search.redirect).toBe('/app/settings')
  expect(screen.queryByRole('heading', { name: 'アカウント設定' })).toBeNull()
})
```

- [x] **Step 8.2: 既存 API error test に cache 保持 assertion を追加する**

既存の `/app/settings は account deletion API error ...` test に `queryClient` seed と cache assertion を追加する。`queryKeys.auth.me` と unrelated cache の両方が残ることを、account deletion API error の全ケースで無条件に確認する。先頭 import に `queryKeys` がなければ追加する。

```tsx
const authUser = {
  id: '00000000-0000-0000-0000-000000000001',
  email: 'user@example.com',
}
const { queryClient } = renderWithRouter({
  initialEntries: ['/app/settings'],
  seed: (client) => {
    client.setQueryData(queryKeys.auth.me, authUser)
    client.setQueryData(['projects'], [{ id: 'project-1' }])
  },
})

// After asserting the alert for the API error:
expect(queryClient.getQueryData(queryKeys.auth.me)).toEqual(authUser)
expect(queryClient.getQueryData(['projects'])).toEqual([{ id: 'project-1' }])
```

- [x] **Step 8.3: frontend 対象 test を実行する**

Run:

```bash
# workdir: frontend
rtk npm test -- app.settings.test.tsx
```

Expected: PASS。

## Task 9: Phase 7 全体の品質ゲート

**Files:** なし。検証のみ。

- [x] **Step 9.1: Backend static gate**

Run:

```bash
# workdir: backend
rtk uv run ruff check .
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
rtk uv run mypy app manage.py
```

Expected: すべて PASS。

- [x] **Step 9.2: Backend unit**

Run:

```bash
# workdir: backend
rtk uv run pytest tests/unit -q
```

Expected: PASS。

- [x] **Step 9.3: Backend migration / integration / db-check**

PostgreSQL が起動していることを確認してから実行する。

```bash
# workdir: backend
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT:-5432}/app_test" \
  rtk uv run python manage.py db-upgrade --revision head
```

```bash
# workdir: backend
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT:-5432}/app_test" \
TEST_DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT:-5432}/app_test" \
  rtk uv run pytest tests/integration -q -ra
```

```bash
# workdir: backend
DATABASE_URL="postgresql+asyncpg://app:app@localhost:${APP_POSTGRES_PORT:-5432}/app_test" \
  rtk uv run python manage.py db-check
```

Expected: PASS、integration skip 0 件、db-check 差分なし。

- [x] **Step 9.4: Frontend**

Run:

```bash
# workdir: frontend
rtk npm run check:ci
rtk npm test
rtk npm run build
```

Expected: すべて PASS。

- [x] **Step 9.5: Docker gate**

Run:

```bash
# workdir: repo root
rtk docker compose config
rtk docker build --target runtime -t python-react-template-runtime .
rtk docker build --target backend-dev -t python-react-template-backend-dev .
```

Expected: すべて PASS。

- [x] **Step 9.6: Documentation grep**

Run:

```bash
# workdir: repo root
rtk rg -n "set_main_option" backend/alembic/env.py
rtk rg -n "skipされる|db-downgrade --revision=" README.md backend/AGENTS.md frontend/AGENTS.md documents/references
rtk rg -n "npm run check$" README.md
```

Expected: no matches。

```bash
# workdir: repo root
rtk rg -n "Cannot downgrade 20260803_0003" README.md
rtk rg -n "Cannot downgrade 20260803_0003" documents/references documents/plans
rtk rg -n "OAuth-only account deletion caveat" backend/AGENTS.md documents/references documents/plans
rtk rg -n "confirmEmail.*not an authentication factor" backend/AGENTS.md documents/references documents/plans
rtk rg -n "Phase 8 Hardening Backlog" documents/plans/20260804-phase8-hardening-backlog.md documents/plans/20260804-phase7-review-stabilization.md
```

Expected: each command returns at least one match in the intended files.

## リスクとロールバック

- Alembic env 変更は全 migration command の起動経路に影響する。問題が出た場合は `backend/alembic/env.py` の online engine config 組み立てだけを戻し、`DATABASE_URL` に `%` を含む環境では Alembic を実行しない。
- `db-downgrade --revision` は positional 呼び出しを廃止する CLI 契約変更である。README / allowlist / help を同時に更新し、古い呼び出しが必要な派生プロジェクトでは compatibility alias を別途検討する。
- `mark_user_deleted()` は repository layer の audit 冪等化であり、account deletion usecase 全体を冪等 API にする変更ではない。usecase 全体の再実行副作用を変える場合は Phase 8 以降で別計画にする。
- Migration downgrade preflight は email reuse 後の分かりにくい `UniqueViolation` を明示 error に変えるだけで、downgrade を安全化するものではない。データ喪失の可能性は docs に残す。

## 完了条件

- `documents/reviews/20260804-phase5-phase6-code-review.md`、`documents/reviews/20260804-phase7-plan-review.md`、`documents/reviews/20260804-phase7-plan-rereview.md`、`documents/reviews/20260804-phase7-plan-third-review.md`、`documents/plans/20260804-phase8-hardening-backlog.md` が存在し、上流レビュー / 計画レビュー / Phase 8 の traceability がある。
- `backend/alembic/env.py` に `set_main_option` が残っていない。
- `uv run python manage.py db-downgrade --revision base` が通り、`db-downgrade base` が互換対象外であることが docs に読める。
- `issued_at + AUTH_SESSION_ABSOLUTE_TTL_SECONDS` を厳密比較する mutation guard test がある。
- `Cannot downgrade 20260803_0003 after deleted email reuse` が migration / docs に出る。
- `mark_user_deleted()` の同時実行 integration test で `USER_MARKED_DELETED` audit log が 1 件に抑えられる。
- `OAuth-only account deletion caveat` と `confirmEmail is not an authentication factor` が docs に出る。
- README の品質ゲートが backend static、unit、db-upgrade、integration、db-check、frontend、Docker を含む。
- `/app/settings` の未認証 redirect と account deletion 失敗時 cache 保持が route test で守られている。
