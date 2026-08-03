# Phase 5 残 P2/P3 とドキュメント同期 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Worktree、`git add`、`git commit`、`git push` は使用しない。

**Goal:** `documents/reviews/20260801-review.md` の Phase 5 として、Phase 0-4 後に残った P2/P3 指摘を解消し、User Deleted をフィルタ・再登録・セッション失効・監査まで含めて backend domain / auth persistence レベルで完全実装し、AGENTS / references / README を実装と一致させる。

**Architecture:** Phase 5A で backend の設定・DB URL・migration 前提を先に整え、その後に auth operational fields、User Deleted、repository 契約、prune CLI を実装する。Phase 5B で frontend の `lib` alias と Header 逆依存を整理する。Phase 5C でドキュメントを最後に同期し、以後の role / permission、OAuth / OIDC、password reset / email verification へ進める前提を固定する。

**Tech Stack:** Python 3.12、FastAPI、SQLModel、SQLAlchemy、Alembic、PostgreSQL、Typer、Injector、pytest、ruff、mypy、YAPF、isort、React 19、TypeScript 5.7、Vite 7.1、TanStack Router v1.132、TanStack Query v5.90、Vitest

---

## 背景

Phase 0 では migration / model 整合、SPA fallback、static 起動、CSRF 非 ASCII 500、sample の明らかな不備を修正した。Phase 1 では backend の DI、Unit of Work、lifespan、error envelope、docs 制御、認証 context / session result の型を整備した。Phase 2 では Argon2 executor、信頼プロキシ、Secure cookie 既定、CSRF middleware、`password_hash` nullable 化、rate limiter、session touch 間引きを実装した。Phase 3 では frontend の認証 route、query key、global error handling、register UI、logout UX、api client、ErrorState を整えた。Phase 4 では CLI / CI / Docker / tooling / README と、`/api/samples` の user-owned sample CRUD を整備した。

レビュー文書の推奨順序では、Phase 5 は「残りの P2/P3 とドキュメント同期」と定義されている。Phase 4 の対象外にも「全 docs の完全同期。Phase 5 でまとめて扱う」と明記されているため、本計画では新しい role / OAuth 機能には進まず、テンプレート配布前に残る構造的不整合を潰す。

Claude Code の計画レビューで、初版 Phase 5 計画には次の blocking が確認された。

- `ALEMBIC_DATABASE_URL` の参照元が root `README.md`、`.github/workflows/ci.yml`、`docker-compose.yaml`、`backend/.env.example`、`.claude/settings.local.json`、tests に残っているのに、Task 5 の対象ファイルに入っていなかった。
- `AUTH_COOKIE_PREFIX` を全 cookie に適用すると、frontend の `frontend/src/lib/apiClient.ts` が `csrf_token` を読めず unsafe request が壊れる。
- DB URL 一本化の Task が migration autogenerate より後にあり、`manage.py db-revision` の現行 fail-fast と順序が矛盾していた。
- `users.deleted_at` を追加するだけでは不完全で、`find_user_by_email()` の filter、認証専用 ID lookup、既存 session 失効、email 再登録方針、監査、テストまで同一 Phase に含める必要がある。
- PostgreSQL `INET` 化は DB column 型だけでなく、Python 側の戻り値が `str | None` に保たれることを integration test で保証する必要がある。
- `db-prune-auth` は CLI から DI container / AsyncEngine / UnitOfWork を使うため、engine dispose まで含む独立設計が必要である。

このレビューは実コードと照合して妥当だったため、本計画は初版から大きく組み直す。

2 回目の計画レビューでは、`backend/app/bootstrap/csrf.py` の session cookie 名ハードコード、deleted user と missing user の判別不能、P2-9 / P3-13 / `postgrest-compatible-api-spec.md` の Step 漏れ、compose command、partial unique index の `db-check` リスクが指摘された。これらも実コードと計画書に照らして妥当だったため反映する。あわせて、`DELETE /api/auth/me` は Phase 5 の性格を公開 account management API へ広げるため Phase 6 へ送る。

## User Deleted 完全実装の定義

この Phase での「User Deleted 完全実装」は、単に `users.deleted_at` column を追加することではない。次の条件をすべて満たした状態を完全実装と呼ぶ。

1. **削除状態を作れること**: repository が `mark_user_deleted(user_id, deleted_at)` を提供し、対象 `users.deleted_at` に timezone-aware datetime を保存できる。公開 API から削除状態を作る endpoint は Phase 6 に送る。
2. **通常取得から除外されること**: `find_user_by_email()`、login、`GET /api/auth/me`、通常の user lookup は `deleted_at IS NULL` の user だけを有効ユーザーとして扱う。Phase 5 では production caller がなくなる `find_user_by_id()` は interface から削除し、ID lookup が必要な認証パスは `find_user_by_id_for_authentication()` だけを使う。
3. **認証時に削除済みを観測できること**: `authenticate_session()` は通常 lookup ではなく `find_user_by_id_for_authentication()` を使い、missing / deleted / inactive を区別する。deleted user の session token が残っていても認証せず、session を revoke して `SESSION_REVOKED_DELETED_USER` audit log を残す。
4. **email 再登録方針が実装されていること**: `uq_users_email_lower` は `deleted_at IS NULL` を条件にした partial unique index へ移行し、削除済み user の email は新規登録に再利用できる。active user 同士の email 重複は引き続き DB が拒否する。
5. **監査されること**: repository / usecase 経由で user を deleted にする処理は `AuthEventType.USER_MARKED_DELETED` として audit log に残せる契約を持つ。古い session token が削除済み user に紐づく場合は `AuthEventType.SESSION_REVOKED_DELETED_USER` を残す。
6. **公開 API はまだ追加しないこと**: `DELETE /api/auth/me`、退会確認 UI、削除後メール匿名化などの account management workflow は Phase 6 で別計画にする。Phase 5 は削除状態の data/auth layer を正しく扱う土台に限定する。
7. **フィルタ漏れを検出できること**: `select(User)`、`session.get(User, ...)`、`find_user_by_*` の新規使用箇所が削除済み user を誤って扱わないよう、repository / usecase / integration tests と grep checklist を計画に含める。
8. **docs に意味が書かれていること**: `is_active = 凍結`、`deleted_at = 退会または論理削除` と定義し、削除済み email の再登録可否、audit log の扱い、physical delete 時の FK 方針を `backend/AGENTS.md` と references に明記する。

この定義は backend domain / auth persistence レベルの完全実装である。frontend に削除ボタンや account settings UI を作ること、公開 API として `DELETE /api/auth/me` を追加することは Phase 5 の対象外とする。

## 方針とその理由

### 採用方針

1. Phase 5 は 1 つの計画書のまま、実行順序を Phase 5A / 5B / 5C に分ける。backend DB 変更と frontend 構造整理は独立しているが、今回の依頼は Phase 5 計画の修正なので文書を分割しない。
2. DB URL 一本化を最初に行う。`manage.py db-revision --autogenerate` が現状 `ALEMBIC_DATABASE_URL` 明示を要求するため、migration を作る前に設定・CI・compose・README・tests を `DATABASE_URL` 正へ揃える。
3. Alembic は `async_engine_from_config()` を使うため async URL が必要である。helper は `postgresql://` を `postgresql+asyncpg://` へ変換する。逆方向の変換はしない。
4. DB schema 変更は、実装開始前にユーザー確認を取る。対象は `users.deleted_at`、partial unique index、`auth_sessions.issued_at` / `updated_at`、IP `INET` 化、追加 index、FK `ON DELETE` である。
5. User Deleted は filter まで含めて完全実装する。カラムだけ追加して query filter や email 再登録方針を未実装にする中途半端な状態は禁止する。
6. IP address は PostgreSQL `INET` 型に統一しつつ、Python 側の model / repository boundary は `str | None` を維持する。`asyncpg` が `ipaddress.IPv4Address` / `IPv6Address` を返しても public interface へ漏れないよう、`TypeDecorator` または result conversion を実装して integration test で保証する。
7. auth cookie prefix は session cookie にだけ適用する。CSRF cookie は JavaScript が読む double-submit cookie なので、cookie 名 `csrf_token` を維持する。これにより frontend の `apiClient` を壊さない。
8. `AUTH_COOKIE_PREFIX` ではなく `AUTH_SESSION_COOKIE_PREFIX` を追加する。設定名で対象を限定し、CSRF cookie へ誤適用される余地を消す。
9. not-found は domain error へ統一する。`revoke_session(session_id)` は冪等 command として missing session を成功扱いにするが、取得・更新系は `UserNotFoundError` / `AuthSessionNotFoundError` を投げる。
10. `mark_user_deleted()` と `revoke_sessions_for_user()` は Phase 6 の account deletion、権限剥奪、password change のための契約として repository 契約整理 Task に置く。Phase 5 では production caller を持たないため、コード側 docstring と `backend/AGENTS.md` に用途を明記して「未使用なので削除してよい」と誤解されないようにする。
11. `db-prune-auth` は独立 Task とし、CLI container bootstrap、UnitOfWork 利用、AsyncEngine dispose を明示する。
12. `services/` vs `repositories/` は Phase 4 の決定どおり `services/` を正とする。`interfaces/libraries/` は空ではなく `rate_limiter_interface.py` が存在するため、空 directory として扱わない。
13. frontend は `src/libraries/css.ts` を `src/lib/css.ts` へ移し、`components.json` alias を `@/lib` へ揃える。`ui -> @/components/atoms` はこの repo の正として維持する。
14. docs 同期は実装の最後に行う。ただし `ALEMBIC_DATABASE_URL` から `DATABASE_URL` への置換は、CI / compose / README の破壊を避けるため Task 2 で同時に行う。

### 採用理由

- Phase 5 の DB 変更は role / permission と OAuth の前提である。権限剥奪、password change、OAuth account linking は既存 session の扱いに直結するため、session issuance、revocation、pruning、audit が曖昧なまま進めるべきではない。
- `created_at` を business logic に使う設計を残すと、データ移行や復旧で TTL 計算が変わる。`issued_at` を追加すれば、監査時刻とセッション発行時刻を別概念として扱える。
- `deleted_at` は filter と unique index 方針まで同時に入れなければ危険である。削除済み user が login できる、削除済み email が再登録不能になる、というバグを後から作るためである。
- `INET` 型は PostgreSQL 前提と整合する。ただし SQLAlchemy / asyncpg の Python 型は driver 挙動に依存するため、DB 型だけ見て完了扱いにしない。
- CSRF cookie は frontend が読む契約である。prefix を付けたい session cookie と、JS-readable な CSRF cookie はセキュリティ属性も利用者も異なるため、同一設定で扱わない。
- docs は AI / 人間の開発者が次の実装で信じる正典である。実装と docs の乖離を Phase 5 で閉じることが、以降の feature work の手戻りを最も減らす。

## スコープ

### 対象

- `P2-1`: `updated_at` の自動更新、`AuthSession.updated_at` 追加。
- `P2-2`: `AuthSession.issued_at` 追加と expiry 計算の切替。
- `P2-3`: auth session / audit log の IP column を PostgreSQL `INET` に統一し、Python 側 `str | None` を保証。
- `P2-4`: PostgreSQL 一本化に合わせた `aiosqlite` 削除と docs 更新。
- `P2-5`: auth repository not-found domain error 統一。
- `P2-7` / `P3-5`: `DATABASE_URL` 正、`ALEMBIC_DATABASE_URL` 廃止、`alembic.ini` の死に設定整理。
- `P2-9`: model import / metadata 整合 test 強化、models 配置方針の docs 明文化。
- `P2-10` / `P3-11`: operational index と `db-prune-auth` command。
- `P2-11` / `P3-9`: 上記 backend 変更の unit / integration test。
- `P2-20`: settings class と環境変数 docs の同期。
- `P3-1`: `utcnow()` 重複の解消。
- `P3-3`: User Deleted の data/auth layer 完全実装、FK `ON DELETE` と user deletion policy。
- `P3-4`: UUID PK 方針の docs 明文化。
- `P3-7`: `services/` を正とする docs 同期。
- `P3-10`: inactive / deleted user session revocation audit event。
- `P3-12`: auth cookie helper 統合と `AUTH_SESSION_COOKIE_PREFIX`。
- `P3-13`: rate limiter の現行 bounded bucket 仕様を test / docs で固定。
- `P3-14`: frontend `lib` / `libraries` と shadcn alias の同期。
- `P3-17`: Header の route 逆依存解消。

### 対象外

- role / permission の schema と UI。
- OAuth / OIDC provider 連携。
- password reset、email verification、password change。
- account deletion の frontend UI。
- `DELETE /api/auth/me` などの公開 account deletion API。
- sample CRUD の frontend UI。
- `services/` から `repositories/` への全体 rename。
- audit log PK の UUIDv7 実移行。Phase 5 では方針を文書化し、実移行は write volume と採用 library を決める別計画に残す。
- coverage 閾値導入。
- Git 操作。`git add`、`git commit`、`git push` はこの計画でも実行しない。

## 変更予定ファイル

### Backend: 作成するファイル

- `backend/alembic/versions/20260803_0003_phase5_auth_operational_fields.py`
  - User Deleted、auth session operational fields、INET、index、FK `ON DELETE` を扱う migration。
- `backend/app/libraries/sqlalchemy_types.py`
  - PostgreSQL `INET` を DB では `INET`、Python では `str | None` として扱う type helper。
- `backend/app/libraries/auth_cookies.py`
  - session / csrf cookie の set / clear を集約する helper。session prefix はここだけで扱う。
- `backend/app/bootstrap/cli.py`
  - CLI から DI container / repository / AsyncEngine を使い、最後に dispose する helper。
- `backend/tests/unit/models/test_auth_errors.py`
  - auth domain error の contract test。
- `backend/tests/unit/libraries/test_sqlalchemy_types.py`
  - `InetString` の bind / result conversion test。
- `backend/tests/unit/libraries/test_auth_cookies.py`
  - cookie helper と `AUTH_SESSION_COOKIE_PREFIX` の test。
- `backend/tests/unit/bootstrap/test_cli.py`
  - CLI bootstrap と engine dispose の test。
- `backend/tests/integration/test_manage_cli.py`
  - `db-prune-auth` が application container / repository / UnitOfWork で実行できることを確認する integration test。

### Backend: 変更するファイル

- `README.md`
- `.github/workflows/ci.yml`
- `.claude/settings.local.json`
- `docker-compose.yaml`
- `AGENTS.md`
- `backend/.env.example`
- `backend/AGENTS.md`
- `backend/README.md`
- `backend/pyproject.toml`
- `backend/uv.lock`
- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/manage.py`
- `backend/app/config/database.py`
- `backend/app/config/auth.py`
- `backend/app/models/user.py`
- `backend/app/models/auth_session.py`
- `backend/app/models/auth_audit_log.py`
- `backend/app/models/auth_errors.py`
- `backend/app/models/auth_event_type.py`
- `backend/app/interfaces/services/auth_repository_interface.py`
- `backend/app/services/auth_repository.py`
- `backend/app/usecases/auth_usecase.py`
- `backend/app/bootstrap/csrf.py`
- `backend/app/controllers/auth_controller.py`
- `backend/app/controllers/auth_dependencies.py`
- `backend/tests/integration/conftest.py`
- `backend/tests/integration/test_auth_controller.py`
- `backend/tests/integration/test_auth_schema.py`
- `backend/tests/integration/test_manage_cli.py`
- `backend/tests/integration/test_migration_consistency.py`
- `backend/tests/integration/services/test_auth_repository.py`
- `backend/tests/unit/bootstrap/test_csrf_middleware.py`
- `backend/tests/unit/config/test_database_settings.py`
- `backend/tests/unit/config/test_auth_settings.py`
- `backend/tests/unit/models/test_auth_models.py`
- `backend/tests/unit/models/test_metadata.py`
- `backend/tests/unit/services/test_auth_repository.py`
- `backend/tests/unit/usecases/test_auth_usecase.py`
- `backend/tests/unit/controllers/test_auth_controller_helpers.py`
- `backend/tests/unit/test_manage.py`

### Frontend: 作成するファイル

- `frontend/src/components/organisms/Header/AuthMenu.tsx`
- `frontend/src/components/organisms/Header/AuthMenu.test.tsx`
- `frontend/src/components/organisms/Header/Header.structure.test.tsx`
- `frontend/src/components/organisms/Header/HeaderNav.tsx`
- `frontend/src/components/organisms/Header/HeaderNav.test.tsx`
- `frontend/src/components/organisms/Header/types.ts`
- `frontend/src/components/organisms/LandingPage/data.ts`
- `frontend/src/lib/css.ts`

### Frontend: 変更・削除するファイル

- Modify: `frontend/components.json`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/routes/__root.tsx`
- Modify: `frontend/src/routes/index.tsx`
- Delete: `frontend/src/routes/index.data.ts`
- Delete: `frontend/src/libraries/css.ts`

### Documentation: 変更するファイル

- `documents/references/backend-app-structure.md`
- `documents/references/frontend-app-structure.md`
- `documents/references/postgrest-compatible-api-spec.md`
- `documents/plans/20260803-phase5-residual-p2-p3-doc-sync.md`

## 具体的なタスク

### Task 1: Phase 5 baseline と review ID 対応表を固定する

**Review IDs:** Phase 5 全体

**Files:**

- Modify: `documents/plans/20260803-phase5-residual-p2-p3-doc-sync.md`

- [x] **Step 1.1: working tree を確認する**

  Run:

  ```bash
  rtk git status --short
  ```

  Expected:

  - Phase 5 実装開始時点の差分を把握する。
  - ユーザーまたは他エージェントの未完了差分がある場合、そのファイルを上書きしない。
  - この計画の実装中も `git add` と `git commit` は実行しない。

- [x] **Step 1.2: Phase 0-4 の完了範囲を確認する**

  Run:

  ```bash
  rtk grep -n "Phase 5|対象外|残|P2-|P3-" documents/plans/20260801-phase0-review-fixes.md documents/plans/20260801-phase1-backend-foundation.md documents/plans/20260802-phase2-auth-security.md documents/plans/20260802-phase2-review-fixes.md documents/plans/20260802-phase3-frontend-structure.md documents/plans/20260802-phase4-tooling-dx-sample-crud.md
  ```

  Expected:

  - Phase 0-4 で対応済みの review ID を再実装しない。
  - 巻末の「Phase 5 対応表」と実態がずれる場合は、実装前にこの計画書を修正する。

- [x] **Step 1.3: `ALEMBIC_DATABASE_URL` と cookie 名の参照元を固定する**

  Run:

  ```bash
  rtk grep -n "ALEMBIC_DATABASE_URL" .github README.md AGENTS.md backend docker-compose.yaml .claude/settings.local.json
  ```

  Expected:

  - root `README.md`、`.github/workflows/ci.yml`、`docker-compose.yaml`、`backend/.env.example`、`AGENTS.md`、`backend/AGENTS.md`、`backend/README.md`、backend tests、backend app code が出る。
  - `.claude/settings.local.json` はローカル設定であるため、削除対象ではなく「必要ならコマンド許可設定を追随させる」対象として扱う。

  Run:

  ```bash
  rtk grep -n "csrf_token|session_token|readCookie" frontend/src backend/app
  ```

  Expected:

  - frontend は `csrf_token` cookie 名を読む。
  - Phase 5 では CSRF cookie 名を変えない方針を確認する。

### Task 2: DB URL を `DATABASE_URL` 正へ先行統一する

**Review IDs:** `P2-4`, `P2-7`, `P2-20`, `P3-5`

**Files:**

- Modify: `README.md`
- Modify: `.github/workflows/ci.yml`
- Modify: `.claude/settings.local.json`
- Modify: `docker-compose.yaml`
- Modify: `AGENTS.md`
- Modify: `backend/.env.example`
- Modify: `backend/AGENTS.md`
- Modify: `backend/README.md`
- Modify: `backend/pyproject.toml`
- Modify: `backend/uv.lock`
- Modify: `backend/alembic.ini`
- Modify: `backend/alembic/env.py`
- Modify: `backend/manage.py`
- Modify: `backend/app/config/database.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/tests/integration/test_migration_consistency.py`
- Modify: `backend/tests/unit/config/test_database_settings.py`
- Modify: `backend/tests/unit/test_manage.py`

- [x] **Step 2.1: DB URL contract tests を先に更新する**

  Required assertions:

  - `DatabaseSettings.DATABASE_URL` は async SQLAlchemy URL を正とする。
  - helper は `postgresql://app:app@db:5432/app` を `postgresql+asyncpg://app:app@db:5432/app` へ変換する。
  - helper は `postgresql+asyncpg://...` をそのまま返す。
  - `sqlite://`、空文字、不正 URL は `get_alembic_database_url()` の helper validation で拒否する。
  - `ALEMBIC_DATABASE_URL` は新規 contract から消える。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/config/test_database_settings.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 2.2: `manage.py` の DB command tests を更新する**

  Required assertions:

  - `db-check` は `DATABASE_URL` が明示設定されていない場合 exit code 2。
  - `db-revision --autogenerate` は `DATABASE_URL` が明示設定されていない場合 exit code 2。
  - stderr は `DATABASE_URL must be configured explicitly` を含む。
  - `ALEMBIC_DATABASE_URL` だけを設定しても新規 contract では成功しない。
  - `DATABASE_URL=postgresql+asyncpg://app:secret@db.example:6543/app_test` の表示は password を含まない。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/test_manage.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 2.3: database settings と Alembic env を実装する**

  Required changes:

  - `backend/app/config/database.py` から `ALEMBIC_DATABASE_URL` field を削除する。
  - `get_alembic_database_url(settings: DatabaseSettings) -> str` を追加し、`postgresql://` を `postgresql+asyncpg://` へ変換する。
  - `backend/alembic/env.py` は `get_alembic_database_url(get_database_settings())` を使う。
  - `backend/manage.py` は `DATABASE_URL` の明示設定を `settings.model_fields_set` で確認する。
  - `backend/alembic.ini` の `sqlalchemy.url` は実接続先として使わないことをコメントで明記する。

  Run:

  ```bash
  rtk grep -n "ALEMBIC_DATABASE_URL" backend/app backend/manage.py backend/alembic backend/tests
  ```

  Expected:

  - 新規 contract の tests や移行説明以外に `ALEMBIC_DATABASE_URL` が残らない。

- [x] **Step 2.4: CI / compose / env / README を更新する**

  Required changes:

  - `.github/workflows/ci.yml` の migration / db-check job env は `DATABASE_URL: postgresql+asyncpg://app:app@localhost:5432/app_test` にする。
  - `docker-compose.yaml` の backend environment から `ALEMBIC_DATABASE_URL` を削除する。
  - `backend/.env.example` から `ALEMBIC_DATABASE_URL` を削除する。
  - root `README.md` と `backend/README.md` の command examples を `DATABASE_URL=postgresql+asyncpg://...` に直す。
  - `AGENTS.md` と `backend/AGENTS.md` の品質ゲートから `ALEMBIC_DATABASE_URL` を削除する。
  - `.claude/settings.local.json` に古い allowlist が残る場合は、削除または `DATABASE_URL=...` のコマンドへ置換する。これはローカル許可設定なので、必要な最小変更に留める。

  Run:

  ```bash
  rtk grep -n "ALEMBIC_DATABASE_URL" .github README.md AGENTS.md backend docker-compose.yaml .claude/settings.local.json
  ```

  Expected:

  - 履歴文書 `documents/plans/*` と `documents/reviews/*` 以外には残らない。

- [x] **Step 2.5: `aiosqlite` を runtime dependency から削除する**

  Required changes:

  - `backend/pyproject.toml` の `dependencies` から `aiosqlite` を削除する。
  - `backend/uv.lock` を更新する。
  - SQLite fallback が存在しないことを docs に書く。backend は PostgreSQL を正とする。

  Run:

  ```bash
  cd backend && rtk uv remove aiosqlite
  ```

  Expected:

  - `backend/pyproject.toml` に `aiosqlite` が残らない。
  - backend import / tests が SQLite dependency に依存していない。

- [x] **Step 2.6: compose 経由 migration を検証対象へ入れる**

  Run:

  ```bash
  rtk docker compose config
  ```

  Expected:

  - PASS。
  - backend service に `ALEMBIC_DATABASE_URL` が表示されない。

  Run:

  ```bash
  rtk docker compose up -d postgres
  ```

  Expected:

  - PostgreSQL service が healthy になる。

  Run:

  ```bash
  rtk docker compose run --rm backend sh -c "uv sync --frozen --group dev && uv run python manage.py db-upgrade"
  ```

  Expected:

  - compose の `DATABASE_URL` だけで dependency sync 後に migration が head まで適用される。

### Task 3: User Deleted と auth operational fields の schema / model を実装する

**Review IDs:** `P2-1`, `P2-2`, `P2-3`, `P2-10`, `P2-11`, `P3-1`, `P3-3`, `P3-9`

**Files:**

- Create: `backend/alembic/versions/20260803_0003_phase5_auth_operational_fields.py`
- Create: `backend/app/libraries/sqlalchemy_types.py`
- Create: `backend/tests/unit/libraries/test_sqlalchemy_types.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/models/auth_session.py`
- Modify: `backend/app/models/auth_audit_log.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/models/test_auth_models.py`
- Modify: `backend/tests/unit/models/test_metadata.py`
- Modify: `backend/tests/integration/test_migration_consistency.py`
- Modify: `backend/tests/integration/test_auth_schema.py`

- [x] **Step 3.1: DB schema 変更の実装許可を取る**

  実装前にユーザーへ確認する。確認対象は次の通り。

  - `users.deleted_at TIMESTAMPTZ NULL`
  - `uq_users_email_lower` を `WHERE deleted_at IS NULL` 付き partial unique index へ移行
  - `auth_sessions.issued_at TIMESTAMPTZ NOT NULL`
  - `auth_sessions.updated_at TIMESTAMPTZ NOT NULL`
  - `auth_sessions.ip_address INET`
  - `auth_audit_logs.ip_address INET`
  - `auth_sessions.expires_at` index
  - `auth_audit_logs.created_at` index
  - `auth_sessions.user_id` FK の `ON DELETE CASCADE`
  - `auth_audit_logs.user_id` FK の `ON DELETE SET NULL`
  - `auth_audit_logs.session_id` FK の `ON DELETE SET NULL`

  Expected:

  - ユーザーが許可するまで migration file を作らない。
  - 2026-08-03 の「では実装に進んでください」により、Phase 5 計画に列挙した DB schema 変更の実装許可を得たものとして扱う。

- [x] **Step 3.2: `InetString` の tests を追加する**

  Required assertions:

  - bind value `"192.0.2.1"` は DB へ渡せる。
  - result value `IPv4Address("192.0.2.1")` は `"192.0.2.1"` に変換される。
  - result value `IPv6Address("2001:db8::1")` は `"2001:db8::1"` に変換される。
  - result value `None` は `None` のまま。
  - invalid IP string は bind 時に `ValueError`。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/libraries/test_sqlalchemy_types.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 3.3: `InetString` を実装する**

  Required implementation:

  - `backend/app/libraries/sqlalchemy_types.py` に `InetString(TypeDecorator[str | None])` を追加する。
  - `impl = postgresql.INET` とする。
  - `cache_ok = True` とする。
  - `process_bind_param()` は `None` を許可し、文字列は `ipaddress.ip_address(value)` で検証してから `str(value)` を返す。
  - `process_result_value()` は `None` を許可し、それ以外は `str(value)` を返す。

- [x] **Step 3.4: model metadata tests を追加する**

  Required assertions:

  - `User.updated_at.sa_column.onupdate` が `None` ではない。
  - `User.deleted_at` が nullable な timezone-aware `DateTime` column。
  - `users` table に `uq_users_email_lower_active` partial unique index が存在し、`postgresql_where` に `deleted_at IS NULL` 相当がある。
  - `AuthSession.issued_at` と `AuthSession.updated_at` が存在する。
  - `AuthSession.updated_at.sa_column.onupdate` が `None` ではない。
  - `AuthSession.ip_address` と `AuthAuditLog.ip_address` が `InetString` を使う。
  - `auth_sessions` table に `ix_auth_sessions_expires_at` が存在する。
  - `auth_audit_logs` table に `ix_auth_audit_logs_created_at` が存在する。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/models/test_auth_models.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 3.5: `utcnow()` の import 元を一本化し model fields を追加する**

  Required changes:

  - `backend/app/models/user.py` と `backend/app/services/auth_repository.py` から local `utcnow()` 定義を削除する。
  - `from app.libraries.clock import utcnow` を使う。
  - `User.updated_at` に `onupdate=utcnow` を追加する。
  - `User.deleted_at` を追加する。
  - `User.__table_args__` の unique index を `uq_users_email_lower_active` partial unique index へ変更する。
  - `AuthSession.issued_at`、`AuthSession.updated_at` を追加する。
  - `AuthSession.ip_address` と `AuthAuditLog.ip_address` に `InetString` を使う。
  - `ix_auth_sessions_expires_at`、`ix_auth_audit_logs_created_at` を追加する。

  Run:

  ```bash
  rtk grep -n "def utcnow" backend/app
  ```

  Expected:

  - `backend/app/libraries/clock.py` だけが表示される。

- [x] **Step 3.6: repository / usecase の session 発行 contract を `issued_at` へ変更する**

  Required changes:

  - `AuthRepositoryInterface.create_session()` に `issued_at: datetime` parameter を追加する。
  - `AuthRepository.create_session()` は `AuthSession(issued_at=issued_at, ...)` を設定する。
  - `AuthUsecase._issue_session()` は `issued_at = utcnow()` を作り、`created_at`、`issued_at`、`last_seen_at` を同じ値で渡す。
  - `AuthUsecase._calculate_session_expiry()` の first parameter 名を `issued_at` にする。
  - `authenticate_session()` の touch 時は `self._calculate_session_expiry(auth_session.issued_at, now)` を使う。
  - `auth_session.created_at` は expiry 計算に使わない。

  Run:

  ```bash
  rtk grep -n "calculate_session_expiry|auth_session.created_at" backend/app/usecases/auth_usecase.py
  ```

  Expected:

  - `_calculate_session_expiry()` は `issued_at` を引数名にしている。
  - touch 時の expiry 計算に `auth_session.created_at` が出てこない。

- [x] **Step 3.7: migration を作成し手修正する**

  Run:

  ```bash
  cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run python manage.py db-revision --message "phase5 auth operational fields" --autogenerate --rev-id 20260803_0003
  ```

  Required migration behavior:

  - `auth_sessions.issued_at` は既存行に対して `created_at` で backfill する。
  - `auth_sessions.updated_at` は既存行に対して `last_seen_at` で backfill する。
  - IP `String` から `INET` へは、空文字や不正値を `NULL` に寄せてから `postgresql_using` で cast する。既存 dirty data で migration が落ちないよう防御的に書く。
  - `users.deleted_at` は nullable で追加する。
  - `uq_users_email_lower` を drop し、`uq_users_email_lower_active` を partial unique index として作る。
  - FK の `ON DELETE` を変更する場合は、既存 constraint 名を drop して同名で作り直す。
  - `ix_auth_sessions_expires_at` と `ix_auth_audit_logs_created_at` を作る。
  - downgrade は逆順で index / FK / column / type を戻す。

  Expected:

  - migration file が上記 behavior を満たす。

  Run:

  ```bash
  cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
  cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
  ```

  Expected:

  - DB を新規 revision まで upgrade した後、partial unique index を含めても metadata diff が clean である。
  - `db-check` が partial unique function index を恒常的に差分検出する場合は、include-object で隠さない。`uq_users_email_lower_active` を諦めて「削除済み email は再登録不可」へ方針変更するか、User Deleted の再登録要件を別 Phase に送る判断をユーザーに戻す。

- [x] **Step 3.8: INET roundtrip integration test を追加する**

  Required assertions:

  - `"192.0.2.1"` を `auth_sessions.ip_address` に保存して SELECT し直すと `isinstance(value, str)` が true。
  - `"2001:db8::1"` を `auth_audit_logs.ip_address` に保存して SELECT し直すと `isinstance(value, str)` が true。
  - DB column type は `inet`。

  Run:

  ```bash
  cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/test_auth_schema.py -q -ra
  ```

  Expected:

  - PostgreSQL 接続がある場合は PASS。
  - `TEST_DATABASE_URL` 未設定なら Phase 4 の contract 通り FAIL。

- [x] **Step 3.9: model import / metadata 整合 test を強化する**

  Required assertions:

  - table model files と `SQLModel.metadata.tables` の数が一致する。
  - `users`、`auth_sessions`、`auth_audit_logs`、`sample_items` が metadata に存在する。
  - DTO / errors / enum は table model count に含めない。
  - `app.models.__init__` が table models を import する責務を持つことを test 名で明示する。
  - `User.deleted_at`、`AuthSession.issued_at`、`AuthSession.updated_at` が metadata から落ちていない。

  Run:

  ```bash
  cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/unit/models/test_metadata.py tests/integration/test_migration_consistency.py -q -ra
  ```

  Expected:

  - PASS。

### Task 4: User Deleted filtering と auth repository 契約を実装する

**Review IDs:** `P2-5`, `P2-11`, `P3-3`, `P3-9`, `P3-10`

**Files:**

- Create: `backend/tests/unit/models/test_auth_errors.py`
- Create: `backend/tests/integration/services/test_auth_repository.py`
- Modify: `backend/app/models/auth_errors.py`
- Modify: `backend/app/models/auth_event_type.py`
- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/services/test_auth_repository.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`

- [x] **Step 4.1: domain error tests を追加する**

  Required assertions:

  - `UserNotFoundError(user_id).user_id == user_id`
  - `AuthSessionNotFoundError(session_id).session_id == session_id`
  - `str(error)` に entity 名と UUID が含まれる。
  - どちらも `Exception` を継承し、HTTP response DTO に依存しない。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/models/test_auth_errors.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 4.2: repository filter tests を unit / integration に分けて追加する**

  Unit test required assertions (`backend/tests/unit/services/test_auth_repository.py`):

  - `find_user_by_email()` が組み立てる `select(User)` に `lower(User.email) == normalized_email` と `User.deleted_at.is_(None)` が含まれる。
  - `find_user_by_id()` は production caller がなくなるため、interface と implementation から削除される。
  - `find_user_by_id_for_authentication()` が組み立てる `select(User)` に `User.id == user_id` が含まれ、`User.deleted_at.is_(None)` は含まれない。
  - `record_user_login()` は fake user の `deleted_at` が `None` ではない場合 `UserNotFoundError` を投げる。
  - `mark_user_deleted()` は missing user で `UserNotFoundError`。

  Integration test required assertions (`backend/tests/integration/services/test_auth_repository.py`):

  - `find_user_by_email()` は `deleted_at IS NULL` の user だけ返す。
  - `find_user_by_id_for_authentication()` は missing user なら `None`、deleted user なら `User`、inactive user なら `User`、active user なら `User` を返す。
  - active user と deleted user が同じ normalized email を持てる。
  - active user 同士の同じ normalized email は実 DB の partial unique index により `EmailAlreadyRegisteredError` になる。
  - `mark_user_deleted(user_id, deleted_at)` は active user を deleted にし、updated `User` を返す。
  - `revoke_sessions_for_user(user_id, revoked_at)` は対象 user の未 revoke session だけ更新し、件数を返す。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/services/test_auth_repository.py -q
  cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/services/test_auth_repository.py -q -ra
  ```

  Expected:

  - 実装前は FAIL。
  - partial unique index と `rowcount` に依存する assertion は integration test にだけ置く。

- [x] **Step 4.3: auth repository contract を実装する**

  Required changes:

  - `UserNotFoundError` と `AuthSessionNotFoundError` を `backend/app/models/auth_errors.py` に追加する。
  - `find_user_by_email()` は `User.deleted_at.is_(None)` を条件に含める。
  - `find_user_by_id()` は interface と implementation から削除し、既存 tests / fakes も `find_user_by_id_for_authentication()` へ置き換える。
  - `find_user_by_id_for_authentication(user_id: UUID) -> User | None` を追加する。この method は `deleted_at` で filter せず、`authenticate_session()` が deleted / inactive / active を判定できるようにする。
  - `update_session_csrf_token_hash()` は missing session で `AuthSessionNotFoundError`。
  - `touch_session()` は missing session で `AuthSessionNotFoundError`。
  - `record_user_login()` は missing or deleted user で `UserNotFoundError`。
  - `revoke_session()` は idempotent command として missing session では return する。
  - `mark_user_deleted(user_id, deleted_at) -> User` を追加する。
  - `revoke_sessions_for_user(user_id, revoked_at) -> int` を追加する。
  - `mark_user_deleted()` と `revoke_sessions_for_user()` は Phase 6 account deletion / role revocation / password change で使う先行契約であり、Phase 5 では production caller を持たないことを docstring に書く。
  - 素の `ValueError("Auth session not found")` と `ValueError("User not found")` は消す。

  Run:

  ```bash
  rtk grep -n "ValueError(\"Auth session not found\"|ValueError(\"User not found\"|select(User)|session.get(User" backend/app
  ```

  Expected:

  - `ValueError` は該当なし。
  - `select(User)` / `session.get(User` の使用箇所は削除済み user を扱う意図があるか、`deleted_at IS NULL` filter がある。
  - 削除済み user を返す例外的な method は `find_user_by_id_for_authentication()` だけである。
  - `find_user_by_id(` は interface / implementation / tests のいずれにも残らない。

- [x] **Step 4.4: authentication usecase の deleted / inactive 判定 tests を追加する**

  Required assertions:

  - `authenticate_session()` は `find_user_by_id_for_authentication()` を使う。
  - deleted user の login は generic 401 と同じ user-facing error になる。
  - delete 済み user の古い session が見つかった場合、`SESSION_REVOKED_DELETED_USER` audit log が残る。
  - inactive user の古い session が見つかった場合、`SESSION_REVOKED_INACTIVE_USER` audit log が残る。
  - missing user の古い session が見つかった場合、deleted / inactive 専用 event は残さず既存の rejected-session path を使う。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/usecases/test_auth_usecase.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 4.5: authentication usecase の deleted / inactive 判定を実装する**

  Required changes:

  - `AuthEventType.USER_MARKED_DELETED = "user_marked_deleted"` を追加する。Phase 5 では repository / internal usecase 契約用に定義し、公開 API からは使わない。
  - `AuthEventType.SESSION_REVOKED_DELETED_USER = "session_revoked_deleted_user"` を追加する。
  - `AuthEventType.SESSION_REVOKED_INACTIVE_USER = "session_revoked_inactive_user"` を追加する。
  - `USER_MARKED_DELETED` は `mark_user_deleted()` が同じ repository 操作内で発行する。Phase 6 の account deletion API は `mark_user_deleted()` を経由して、この監査契約を利用する。
  - `AuthUsecase.authenticate_session()` は `find_user_by_id_for_authentication()` を使う。
  - `authenticate_session()` は user missing / deleted / inactive を認証不可として扱う。deleted user では session revoke と `SESSION_REVOKED_DELETED_USER` audit log、inactive user では session revoke と `SESSION_REVOKED_INACTIVE_USER` audit log を行う。

- [x] **Step 4.6: User Deleted の公開 API を Phase 6 に送るメモを残す**

  Required content:

  - `documents/plans/20260803-phase5-residual-p2-p3-doc-sync.md` の実行結果または未対応事項に、`DELETE /api/auth/me` は Phase 6 account management の候補として残す。
  - Phase 6 で決める論点として、削除後も email を保持するか、匿名化するか、再登録を許可するか、本人確認を再要求するかを書く。
  - Phase 5 では public route、controller method、frontend UI を追加しない。
  - 2026-08-03 に `documents/plans/20260803-phase6-account-deletion-handoff.md` を作成済み。`DELETE /api/auth/me`、email 保持/匿名化、再登録、本人確認、frontend UI は Phase 6 の設計対象として申し送り済み。

### Task 5: auth pruning CLI を独立実装する

**Review IDs:** `P2-10`, `P2-11`, `P3-11`

**Files:**

- Create: `backend/app/bootstrap/cli.py`
- Create: `backend/tests/unit/bootstrap/test_cli.py`
- Modify: `backend/manage.py`
- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/tests/integration/services/test_auth_repository.py`
- Modify: `backend/tests/unit/services/test_auth_repository.py`
- Modify: `backend/tests/unit/test_manage.py`

- [x] **Step 5.1: repository prune API の tests を追加する**

  Required repository methods:

  - `delete_expired_sessions(expired_before: datetime) -> int`
  - `delete_audit_logs_created_before(created_before: datetime) -> int`

  Unit test required assertions (`backend/tests/unit/services/test_auth_repository.py`):

  - `delete_expired_sessions()` は `delete(AuthSession)` に `AuthSession.expires_at < expired_before` を含める。
  - `delete_audit_logs_created_before()` は `delete(AuthAuditLog)` に `AuthAuditLog.created_at < created_before` を含める。
  - repository は `UnitOfWorkInterface.session_scope()` を使う。

  Integration test required assertions (`backend/tests/integration/services/test_auth_repository.py`):

  - expired session delete は `expires_at < expired_before` の行だけ削除する。
  - active session は削除されない。
  - audit log delete は `created_at < created_before` の行だけ削除する。
  - audit log prune は session prune の前後どちらでも FK error にならない。Task 3 で `ON DELETE SET NULL` にしたため、順序理由を FK 回避とは書かない。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/services/test_auth_repository.py -q
  cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/services/test_auth_repository.py -q -ra
  ```

  Expected:

  - 実装前は missing method で FAIL。
  - 実 DB の削除件数と対象行だけ削除されることは integration test にだけ置く。

- [x] **Step 5.2: repository prune API を実装する**

  Required implementation:

  - SQLAlchemy `delete()` を使い、対象件数は `result.rowcount or 0` で返す。
  - repository は `UnitOfWorkInterface.session_scope()` を使う。
  - transaction session 内では `flush()`、transaction 外では `commit()` する。
  - command の実行順序は audit log prune、expired session prune とする。理由は「古い audit log を先に減らし、その後 session を減らすと削除件数の出力が読みやすい」ためであり、FK 回避ではない。

- [x] **Step 5.3: CLI bootstrap tests を追加する**

  Required assertions:

  - CLI helper は application と同じ DI modules で repository を解決できる。
  - CLI helper は async operation 完了後に `AsyncEngine.dispose()` を必ず呼ぶ。
  - operation が例外を投げても `AsyncEngine.dispose()` を呼ぶ。
  - UnitOfWork の ContextVar transaction が CLI でも request なしで使える。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/bootstrap/test_cli.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 5.4: CLI bootstrap helper を実装する**

  Required implementation:

  - `backend/app/bootstrap/cli.py` に `async def run_with_container(operation: Callable[[Injector], Awaitable[T]]) -> T` を追加する。
  - `create_container()` と同じ module 構成を使う。
  - operation 後、container から `AsyncEngine` を取得できる場合は `await engine.dispose()` を呼ぶ。
  - dispose は `finally` で実行する。
  - CLI 専用 helper は FastAPI app を作らない。middleware / route / static mount は不要。

- [x] **Step 5.5: `db-prune-auth` CLI test を追加する**

  Required command contract:

  - `python manage.py db-prune-auth --expired-sessions-before 2026-08-01T00:00:00+00:00` は expired session prune だけを呼ぶ。
  - `python manage.py db-prune-auth --audit-logs-before 2026-08-01T00:00:00+00:00` は audit log prune だけを呼ぶ。
  - 両方指定した場合は audit log prune、expired session prune の順で実行する。
  - どちらも未指定なら exit code 2。
  - naive datetime は exit code 2。
  - stdout に `Deleted expired sessions: N` と `Deleted audit logs: M` を表示する。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/test_manage.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 5.6: `db-prune-auth` を実装する**

  Required implementation:

  - `@app.command("db-prune-auth")` を追加する。
  - ISO 8601 datetime は `datetime.fromisoformat()` で parse し、`tzinfo is None` を拒否する。
  - Task 2 の `DATABASE_URL` explicit check を使う。
  - repository 呼び出しは `run_with_container()` 経由にする。
  - engine dispose は `run_with_container()` に任せる。

### Task 6: auth cookie helper を frontend-compatible に統合する

**Review IDs:** `P3-12`

**Files:**

- Create: `backend/app/libraries/auth_cookies.py`
- Create: `backend/tests/unit/libraries/test_auth_cookies.py`
- Modify: `backend/app/bootstrap/csrf.py`
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/tests/unit/bootstrap/test_csrf_middleware.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_helpers.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `frontend/src/lib/apiClient.test.ts`

- [x] **Step 6.1: cookie helper contract を test で固定する**

  Required assertions:

  - session cookie と CSRF cookie は同じ low-level helper を使う。
  - `AUTH_SESSION_COOKIE_PREFIX=""` の場合、session cookie 名は `session_token`。
  - `AUTH_SESSION_COOKIE_PREFIX="__Host-"` の場合、session cookie 名は `__Host-session_token`。
  - CSRF cookie 名は prefix 設定に関係なく常に `csrf_token`。
  - `__Host-` prefix 使用時は `Secure=True`、`Path="/"`、`Domain` 未指定を validation で強制する。
  - `SameSite`、`HttpOnly`、`Max-Age`、`Expires` の現行 contract を壊さない。
  - `AUTH_SESSION_COOKIE_PREFIX="__Host-"` の場合でも CSRF middleware は `__Host-session_token` を読み、認証済み unsafe request で `auth_sessions.csrf_token_hash` との session-bound CSRF 検証を実行する。
  - session cookie prefix 設定時に `session_token` が存在しないことだけを理由に session-bound CSRF 検証をスキップしない。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/libraries/test_auth_cookies.py tests/unit/bootstrap/test_csrf_middleware.py tests/unit/config/test_auth_settings.py -q
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 6.2: frontend の CSRF cookie 名 contract test を追加する**

  Required assertion:

  - `frontend/src/lib/apiClient.ts` は unsafe request 前に `csrf_token` を読む。
  - backend の session cookie prefix 設定に関係なく、CSRF bootstrap 後に `csrf_token` があれば request が進む。

  Run:

  ```bash
  cd frontend && rtk npm test -- apiClient
  ```

  Expected:

  - PASS。frontend code の変更が不要なら test だけで contract を固定する。

- [x] **Step 6.3: backend helper を実装し controller / dependency を差し替える**

  Required implementation:

  - `backend/app/libraries/auth_cookies.py` に `session_cookie_name(settings)`、`csrf_cookie_name()`、`set_auth_cookie()`、`clear_auth_cookie()` を置く。
  - `session_cookie_name()` だけが `AUTH_SESSION_COOKIE_PREFIX` を見る。
  - `csrf_cookie_name()` は常に `"csrf_token"` を返す。
  - `auth_controller.py` の set / clear cookie 処理を helper に置き換える。
  - `auth_dependencies.py` は session cookie 名を helper から取得する。
  - `backend/app/bootstrap/csrf.py` は session cookie 名と CSRF cookie 名を helper から取得する。
  - CSRF middleware / controller は CSRF cookie 名を helper から取得する。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/bootstrap/test_csrf_middleware.py tests/unit/controllers/test_auth_controller_helpers.py tests/integration/test_auth_controller.py -q -ra
  ```

  Expected:

  - PASS。

### Task 7: rate limiter の bounded bucket 仕様を固定する

**Review IDs:** `P3-13`, adjacent `P2-24`

**Files:**

- Modify: `backend/app/libraries/auth_rate_limiter.py`
- Modify: `backend/tests/unit/libraries/test_auth_rate_limiter.py`
- Modify: `backend/AGENTS.md`

- [x] **Step 7.1: 現行実装を確認する**

  Run:

  ```bash
  rtk read backend/app/libraries/auth_rate_limiter.py
  ```

  Expected:

  - request ごとの全 bucket 走査がない。
  - `AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` 到達時は expired bucket の償却 reclaim を行う。
  - 期限切れ掃除後も満杯なら新規 bucket は fail-open になる。

- [x] **Step 7.2: mutation-resistant tests を追加する**

  Required assertions:

  - active bucket が上限に達した状態で新規 key を silent eviction しない。
  - expired bucket がある場合だけ reclaim する。
  - reclaim しても空きがない場合は fail-open になり、既存 bucket の counters は壊れない。
  - `is_allowed()` は対象 key の window trim を行い、全 key を毎回 trim しない。

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit/libraries/test_auth_rate_limiter.py -q
  ```

  Expected:

  - PASS。

- [x] **Step 7.3: rate limiter docs を現行仕様へ同期する**

  Required changes:

  - `backend/AGENTS.md` に、in-memory rate limiter は single-process 向けの最小防御であることを維持して書く。
  - `AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` 到達時は expired bucket だけを償却 reclaim することを書く。
  - expired bucket 掃除後も満杯の場合、新規 bucket は fail-open になり warning を出すことを書く。
  - request ごとの全 bucket 走査や shared overflow bucket を追加しないことを書く。

  Run:

  ```bash
  rtk grep -n "AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE|fail-open|overflow bucket|全 bucket" backend/AGENTS.md
  ```

  Expected:

  - `backend/AGENTS.md` が Phase 2/5 後の bounded bucket 仕様を説明している。

### Task 8: frontend `lib` / shadcn alias を実態と docs に揃える

**Review IDs:** `P3-14`

**Files:**

- Create: `frontend/src/lib/css.ts`
- Delete: `frontend/src/libraries/css.ts`
- Modify: `frontend/components.json`
- Modify: frontend import files that reference `@/libraries` or `@/libraries/css`
- Modify: `frontend/AGENTS.md`
- Modify: `documents/references/frontend-app-structure.md`

- [x] **Step 8.1: import 使用箇所を確認する**

  Run:

  ```bash
  rtk grep -n "@/libraries|libraries/css|@/lib|from '../libraries|from './libraries" frontend/src frontend/components.json
  ```

  Expected:

  - `frontend/src/libraries/css.ts` 由来の import が一覧化される。
  - `frontend/src/lib` は既に存在するため、`css.ts` をそこへ移すだけでよい。

- [x] **Step 8.2: `css.ts` を `src/lib` へ移す**

  Required changes:

  - `frontend/src/lib/css.ts` を作る。
  - `frontend/src/libraries/css.ts` を削除する。
  - `cn()` の実装は変更しない。
  - import は `@/lib/css` に統一する。
  - `components.json` は `"utils": "@/lib/css"`、`"lib": "@/lib"` に変更する。
  - `"ui": "@/components/atoms"` は維持する。
  - `frontend/src/libraries/` は空 directory として残さない。

  Run:

  ```bash
  rtk grep -n "@/libraries|libraries/css" frontend/src frontend/components.json
  ```

  Expected:

  - 該当なし。

### Task 9: Header の route 逆依存を解消する

**Review IDs:** `P3-17`

**Files:**

- Create: `frontend/src/components/organisms/Header/AuthMenu.tsx`
- Create: `frontend/src/components/organisms/Header/AuthMenu.test.tsx`
- Create: `frontend/src/components/organisms/Header/Header.structure.test.tsx`
- Create: `frontend/src/components/organisms/Header/HeaderNav.tsx`
- Create: `frontend/src/components/organisms/Header/HeaderNav.test.tsx`
- Modify: `frontend/src/components/organisms/Header/index.tsx`
- Modify: `frontend/src/components/organisms/Header/index.test.tsx`
- Modify: `frontend/src/routes/__root.tsx`
- Modify: `frontend/src/routes/index.tsx`
- Delete: `frontend/src/routes/index.data.ts`

- [x] **Step 9.1: Header の test を props 境界へ書き換える**

  Required assertions:

  - `Header` に `navigationItems` を渡すと desktop nav と mobile nav が表示される。
  - `navigationItems` を渡さない場合、landing nav は表示されない。
  - `Header` は `routes/index.data.ts` を import しない。
  - logged-in user の email と logout button は `AuthMenu` に表示される。
  - logout failure は role alert を表示する。

  Run:

  ```bash
  cd frontend && rtk npm test -- Header
  ```

  Expected:

  - 実装前は FAIL。

- [x] **Step 9.2: `NavigationItem` 型を Header 側に定義する**

  Required decision:

  - `NavigationItem` は `frontend/src/components/organisms/Header/index.tsx` または Header-local type file に置く。
  - shape は `{ href: string; label: string }` とする。
  - `landingNavigation` の要素に `id` があっても、構造的型付けにより Header へ渡せる。
  - component から `routes/index.data.ts` は import しない。

- [x] **Step 9.3: `AuthMenu` と `HeaderNav` を分離する**

  Required behavior:

  - `AuthMenu` は `useAuthSession()` と `useNavigate()` を持つ。
  - `HeaderNav` は `items: NavigationItem[]` と `onNavigate?: () => void` を受ける pure component にする。
  - `Header` は menu open / close と shell layout を担当する。
  - `Header` の props は `navigationItems?: NavigationItem[]` とする。

- [x] **Step 9.4: root route から landing navigation を注入する**

  Required changes:

  - `frontend/src/routes/__root.tsx` は router state の pathname が `/` のときだけ `landingNavigation` を Header に渡す。
  - `Header` は route pathname を直接読まない。
  - landing 以外の page では mobile menu button が表示されない。

  Run:

  ```bash
  rtk grep -n "from '@/routes|from '../../routes|from '../../../routes|routes/index.data" frontend/src/components
  ```

  Expected:

  - 該当なし。

### Task 10: AGENTS と references を Phase 5 後の正典へ同期する

**Review IDs:** Phase 5 docs sync、`P2-4`, `P2-7`, `P2-9`, `P2-20`, `P3-3`, `P3-4`, `P3-7`, `P3-12`, `P3-14`

**Files:**

- Modify: `AGENTS.md`
- Modify: `backend/AGENTS.md`
- Modify: `frontend/AGENTS.md`
- Modify: `README.md`
- Modify: `backend/README.md`
- Modify: `documents/references/backend-app-structure.md`
- Modify: `documents/references/frontend-app-structure.md`
- Modify: `documents/references/postgrest-compatible-api-spec.md`

- [x] **Step 10.1: docs の矛盾を検索する**

  Run:

  ```bash
  rtk grep -n "aiosqlite|ALEMBIC_DATABASE_URL|repositories/|components/ui|libraries/|utcnow|created_at.*expires|Status|db-prune|AUTH_COOKIE_PREFIX|AUTH_SESSION_COOKIE_PREFIX|deleted_at|UUIDv7|services/" AGENTS.md backend/AGENTS.md frontend/AGENTS.md README.md backend/README.md documents/references
  ```

  Expected:

  - 実装と矛盾する記述が一覧化される。
  - 履歴文書である `documents/reviews/20260801-review.md` は検索対象に含めない。

- [x] **Step 10.2: User Deleted 完全実装の定義を docs に反映する**

  Required docs:

  - `is_active = 凍結`、`deleted_at = 退会または論理削除`。
  - active user query は `deleted_at IS NULL` を必ず含む。
  - 削除済み user は login / `/api/auth/me` / session authentication で認証不可。
  - 削除済み user の email は partial unique index により再登録可能。
  - Phase 5 は公開 account deletion API を追加しない。
  - `DELETE /api/auth/me` と frontend account deletion UI は Phase 6 account management の候補として残す。
  - physical delete 時、sessions は CASCADE、audit logs は SET NULL。

- [x] **Step 10.3: backend docs を更新する**

  Required content:

  - `DATABASE_URL` を正とし、Alembic も同じ設定から async URL を導出する。
  - `AuthSession.issued_at` は absolute TTL 起点、`created_at` は作成監査時刻。
  - IP address columns は PostgreSQL `INET` だが、Python model boundary は `str | None`。
  - repository は domain error を投げ、HTTP error を投げない。
  - `revoke_session()` は idempotent。
  - `mark_user_deleted()`、`revoke_sessions_for_user()`、`USER_MARKED_DELETED` は Phase 6 account deletion / role revocation / password change 用の先行契約であり、Phase 5 では production caller を持たない。
  - `find_user_by_id()` は削除し、認証時の ID lookup は `find_user_by_id_for_authentication()` だけを使う。
  - `db-prune-auth` の使い方。
  - `AUTH_SESSION_COOKIE_PREFIX="__Host-"` の条件。
  - CSRF cookie 名は `csrf_token` 固定。
  - audit log PK は現時点では UUIDv4 を維持し、高 write volume の product では UUIDv7 を別計画で検討する。
  - `services/` を repository implementation の正式置き場とする。
  - `interfaces/libraries/` は `rate_limiter_interface.py` の置き場であり空 directory ではない。
  - rate limiter の bounded bucket / fail-open 仕様は Task 7 と同じ内容に揃える。

- [x] **Step 10.4: frontend docs を更新する**

  Required content:

  - shadcn generated atoms は `src/components/atoms`。
  - wrappers は `molecules` 以上。
  - shared utilities は `src/lib`。
  - `components` から `routes` を import しない。
  - Header は navigation props を受け、route-specific data は route layer が注入する。
  - `components/ui` はこの repo では採用しない。将来 shadcn default へ戻す場合は別計画で alias と import をまとめて変更する。

- [x] **Step 10.5: `postgrest-compatible-api-spec.md` を確認・更新する**

  Required changes:

  - `documents/references/postgrest-compatible-api-spec.md` は現行 API 契約ではなく、未実装の将来検討メモとして位置づける。
  - `documents/references/postgrest-compatible-api-spec.md` に `/api/sample/`、`Status` success envelope、snake_case public JSON など Phase 4/5 後の実装と矛盾する記述があれば修正する。
  - `/api/samples` は REST resource として camelCase request / response を正にする。
  - Phase 5 では `DELETE /api/auth/me` を追加しないため、account deletion API はこの spec に追加しない。
  - User Deleted は backend domain / auth persistence の方針として `backend/AGENTS.md` と `backend-app-structure.md` に書き、public API spec には露出させない。

  Run:

  ```bash
  rtk grep -n "/api/sample/|/api/samples|Status|snake_case|DELETE /api/auth/me|deleted_at" documents/references/postgrest-compatible-api-spec.md
  ```

  Expected:

  - Phase 4/5 後の public API と矛盾する記述がない。
  - `DELETE /api/auth/me` は登場しない。

### Task 11: Phase 5 全体の品質ゲートを実行する

**Review IDs:** Phase 5 全体

**Files:**

- No direct file changes expected. Failures が出た場合は該当実装 task に戻って修正する。

- [x] **Step 11.1: backend static checks を実行する**

  Run:

  ```bash
  cd backend && rtk uv run ruff check .
  cd backend && rtk uv run isort . --check-only
  cd backend && rtk uv run yapf -dr app/ tests/ alembic/ manage.py
  cd backend && rtk uv run mypy app manage.py
  ```

  Expected:

  - すべて PASS。

- [x] **Step 11.2: backend unit / integration / Alembic を実行する**

  Run:

  ```bash
  cd backend && rtk uv run pytest tests/unit
  cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
  cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra
  cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
  ```

  Expected:

  - すべて PASS。
  - integration tests は skip 0 件。

- [x] **Step 11.3: frontend checks を実行する**

  Run:

  ```bash
  cd frontend && rtk npm run check:ci
  cd frontend && rtk npm test
  cd frontend && rtk npm run build
  ```

  Expected:

  - すべて PASS。
  - build output は `backend/static/` に出るが、生成物は commit 対象にしない。

- [x] **Step 11.4: Docker / compose migration を実行する**

  Run:

  ```bash
  rtk docker compose config
  rtk docker build --target runtime .
  rtk docker build --target backend-dev .
  rtk docker compose up -d postgres
  rtk docker compose run --rm backend sh -c "uv sync --frozen --group dev && uv run python manage.py db-upgrade"
  ```

  Expected:

  - すべて PASS。
  - compose backend は `DATABASE_URL` だけで migration できる。
  - compose config に `ALEMBIC_DATABASE_URL` が出ない。

### Task 12: 実行結果と未対応事項を計画書へ反映する

**Review IDs:** Phase 5 全体

**Files:**

- Modify: `documents/plans/20260803-phase5-residual-p2-p3-doc-sync.md`

- [x] **Step 12.1: 実行結果セクションを更新する**

  Required content:

  - 実行した command。
  - PASS / FAIL / 未実行。
  - FAIL または未実行の場合の理由。
  - DB schema 変更に対するユーザー確認の有無。
  - 生成された migration revision ID。
  - compose 経由 migration の結果。

- [x] **Step 12.2: Phase 5 対応表を最終状態へ更新する**

  Required content:

  - 完了した review ID は `完了` と書く。
  - Phase 5 対象外にした ID は対象外理由を書く。
  - 次 Phase に送る ID は、なぜ Phase 5 で扱わないかを書く。

- [x] **Step 12.3: git 操作をしていないことを確認する**

  Run:

  ```bash
  rtk git status --short
  ```

  Expected:

  - Phase 5 の実装差分が working tree に残っている。
  - staging area に追加されたファイルがない。
  - `git add` と `git commit` は実行されていない。

## Phase 5 対応表

| Review ID | Phase 5 での扱い | 対応 Task |
|---|---|---|
| `P2-1` | 完了。`updated_at` 自動更新と `AuthSession.updated_at` を追加した。 | Task 3 |
| `P2-2` | 完了。`AuthSession.issued_at` を追加し、絶対 TTL の起点へ切り替えた。 | Task 3 |
| `P2-3` | 完了。auth session / audit log の IP column を PostgreSQL `INET` に統一し、Python 側 `str \| None` を保証した。 | Task 3 |
| `P2-4` | 完了。PostgreSQL 前提へ dependency と docs を揃えた。 | Task 2, Task 10 |
| `P2-5` | 完了。auth repository の not-found を domain error へ統一した。 | Task 4 |
| `P2-6` | Phase 2 で対応済み。metadata naming convention と migration constraint 名は導入済み。 | 対象外 |
| `P2-7` | 完了。`DATABASE_URL` を正とし、Alembic URL 解決を整理した。 | Task 2 |
| `P2-8` | Phase 1 で対応済み。UnitOfWork による session 共有へ移行済み。 | 対象外 |
| `P2-9` | 完了。model import / metadata 整合 test と docs 方針を強化した。 | Task 3, Task 10 |
| `P2-10` | 完了。session / audit log の運用 index と prune command を追加した。 | Task 3, Task 5 |
| `P2-11` | 完了。Phase 5 の DB / repository / CLI 変更へ tests を追加した。 | Task 3, Task 4, Task 5 |
| `P2-12` | Phase 0 で対応済み。 | 対象外 |
| `P2-13` | Phase 2 で対応済み。 | 対象外 |
| `P2-14` | Phase 2 で対応済み。 | 対象外 |
| `P2-15` | Phase 2 で対応済み。 | 対象外 |
| `P2-16` | Phase 2 で設計判断を docs 化済み。 | 対象外 |
| `P2-17` | Phase 1 で対応済み。 | 対象外 |
| `P2-18` | Phase 1 で対応済み。 | 対象外 |
| `P2-19` | Phase 2 で対応済み。 | 対象外 |
| `P2-20` | 完了。settings と docs を Phase 5 後の PostgreSQL 前提へ同期した。 | Task 2, Task 10 |
| `P2-21` | Phase 1 で対応済み。 | 対象外 |
| `P2-22` | Phase 0 / Phase 4 で対応済み。 | 対象外 |
| `P2-23` | Phase 4 で対応済み。 | 対象外 |
| `P2-24` | 完了。Phase 2 の interface 化を前提に、Phase 5 では `P3-13` として bounded bucket 仕様を test / docs で固定した。 | Task 7 |
| `P2-25` | Phase 4 で対応済み。 | 対象外 |
| `P2-26` | Phase 3 で対応済み。 | 対象外 |
| `P2-27` | Phase 3 で対応済み。 | 対象外 |
| `P2-28` | Phase 3 で対応済み。 | 対象外 |
| `P2-29` | Phase 3 で対応済み。 | 対象外 |
| `P2-30` | Phase 3 で対応済み。 | 対象外 |
| `P2-31` | Phase 3 で対応済み。 | 対象外 |
| `P2-32` | Phase 3 で対応済み。 | 対象外 |
| `P2-33` | Phase 3 で対応済み。 | 対象外 |
| `P2-34` | 完了。Phase 3 の主要対応を前提に、Phase 5 変更分の tests を各 task に追加した。 | Task 6, Task 8, Task 9 |
| `P2-35` | Phase 4 で対応済み。 | 対象外 |
| `P3-1` | 完了。`utcnow()` を `app/libraries/clock.py` に一本化した。 | Task 3 |
| `P3-2` | Phase 1 で対応済み。 | 対象外 |
| `P3-3` | 完了。User Deleted をフィルタまで含めて完全実装し、FK `ON DELETE` と deletion policy を整えた。 | Task 3, Task 4, Task 10 |
| `P3-4` | 完了。Phase 5 では実移行せず、UUID PK 方針を docs に明記した。 | Task 10 |
| `P3-5` | 完了。`P2-7` と同時に `alembic.ini` の死に設定を整理した。 | Task 2 |
| `P3-6` | 完了。Phase 4 の CLI 主要対応を前提に、Phase 5 では `db-prune-auth` を `P3-11` として追加した。 | Task 5 |
| `P3-7` | 完了。`services/` 正式採用と `interfaces/libraries/` の実態を docs に同期した。 | Task 10 |
| `P3-8` | Phase 4 で対応済み。 | 対象外 |
| `P3-9` | 完了。Phase 5 変更分の tests を追加した。 | Task 3, Task 4, Task 5 |
| `P3-10` | 完了。inactive / deleted user session revoke audit event を追加した。 | Task 4 |
| `P3-11` | 完了。`db-prune-auth` を追加した。 | Task 5 |
| `P3-12` | 完了。auth cookie helper を統合し、session cookie prefix を frontend-compatible に追加した。 | Task 6 |
| `P3-13` | 完了。現行 bounded bucket 仕様を test / docs で固定した。 | Task 7 |
| `P3-14` | 完了。frontend `lib` と alias / docs を同期した。 | Task 8, Task 10 |
| `P3-15` | Phase 4 で対応済み。 | 対象外 |
| `P3-16` | Phase 3 で carry-over として対応済み。 | 対象外 |
| `P3-17` | 完了。Header の route 逆依存を解消した。 | Task 9 |
| `P3-18` | Phase 4 で対応済み。 | 対象外 |

## 実行結果

2026-08-03 時点で Phase 5 の実装と検証を完了した。DB schema 変更は、ユーザーの「では実装に進んでください。終わったタスクはチェックを入れて」という明示指示に基づいて実施した。生成した migration revision ID は `20260803_0003`。

実行したコマンドと結果:

| Command | Result | Notes |
|---|---:|---|
| `cd backend && rtk uv run ruff check .` | PASS | `app/bootstrap/cli.py` の `TypeVar` は YAPF 互換のため `# noqa: UP047` を付与。 |
| `cd backend && rtk uv run isort . --check-only` | PASS |  |
| `cd backend && rtk uv run yapf -dr app/ tests/ alembic/ manage.py` | PASS |  |
| `cd backend && rtk uv run mypy app manage.py` | PASS |  |
| `cd backend && rtk uv run pytest tests/unit` | PASS | 247 passed。FastAPI / Starlette 由来の deprecation warning が 1 件。 |
| `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade` | PASS | `20260802_0002` から `20260803_0003` へ upgrade。 |
| `cd backend && TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q -ra` | PASS | 60 passed。FastAPI / Starlette 由来の deprecation warning が 4 件。 |
| `cd backend && DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run python manage.py db-check` | PASS | Alembic head と metadata の整合を確認。 |
| `cd frontend && rtk npm run check:ci` | PASS | 初回は Prettier 差分で FAIL したため `npm run check` で整形後に再実行して PASS。 |
| `cd frontend && rtk npm test` | PASS | 15 files / 80 tests passed。jsdom の `window.scrollTo` 未実装 warning と、エラー応答 test の `ApiError` log は非致命。 |
| `cd frontend && rtk npm run build` | PASS | `%VITE_SITE_URL% is not defined` warning が 3 件。既存の Vite 置換 warning で build は成功。 |
| `rtk docker compose config` | PASS | `ALEMBIC_DATABASE_URL` が出ないことを確認。 |
| `rtk docker build --target runtime .` | PASS | 初回は Docker socket permission で失敗し、承認後に再実行して成功。frontend build と同じ `%VITE_SITE_URL%` warning あり。 |
| `rtk docker build --target backend-dev .` | PASS | 初回は Docker socket permission で失敗し、承認後に再実行して成功。 |
| `rtk docker compose up -d postgres` | PASS | `python-react-template-postgres-1` が Running。 |
| `rtk docker compose run --rm backend sh -c "uv sync --frozen --group dev && uv run python manage.py db-upgrade"` | PASS | compose backend は `DATABASE_URL` だけで migration 成功。 |
| `rtk git status --short` | PASS | Phase 5 の差分は working tree に未ステージで残っている。`git add` と `git commit` は実行していない。 |

Claude Code review 後の追加反映:

- `frontend/src/components/organisms/Header/AuthMenu.test.tsx` と `Header.structure.test.tsx` を追加し、AuthMenu の logout 表示・失敗表示、Header の props 境界、`routes/index.data.ts` 非依存を検証する。
- `frontend/src/routes/index.data.ts` の re-export shim を削除し、`__root.tsx` から `LandingPage/data.ts` を直接 import する。
- 空ディレクトリ `frontend/src/libraries/` を削除した。
- `documents/references/postgrest-compatible-api-spec.md` を未実装の将来検討メモとして明確化した。
- `backend/app/config/auth.py` で `AUTH_SESSION_COOKIE_PREFIX=__Host-` と `AUTH_COOKIE_SECURE=false` の組み合わせを settings validation で拒否する。
- `backend/app/bootstrap/cli.py` は engine dispose 失敗を握り潰さず log に残す。
- `backend/manage.py` の `db-upgrade` / `db-downgrade` も明示 `DATABASE_URL` を要求する。`db-prune-auth` は datetime 検証を `DATABASE_URL` 検証より先に行う。
- `backend/app/services/auth_repository.py` の `mark_user_deleted()` は `USER_MARKED_DELETED` audit log を同じ repository 操作内で作成する。
- pytest は `--import-mode=importlib` を既定にし、衝突回避用の `tests/**/__init__.py` は削除した。
- 追加検証対象として、repository の SQL 条件 / domain error、CLI bootstrap dispose logging、実 container 経由の `db-prune-auth` integration test を加えた。
- 追加 review R1 として、bare `alembic current/upgrade` が `manage.py` の明示 `DATABASE_URL` guard を通らない抜け道を確認した。`alembic/env.py` 側にも明示 `DATABASE_URL` check を追加し、既定 URL だけで Alembic migration env が動かないようにした。

Claude Code review 後に追加で実行したコマンドと結果:

| Command | Result | Notes |
|---|---:|---|
| `cd backend && rtk uv run pytest tests/unit/config/test_auth_settings.py tests/unit/libraries/test_sqlalchemy_types.py tests/unit/bootstrap/test_cli.py tests/unit/services/test_auth_repository.py tests/unit/test_manage.py -q` | PASS | 70 passed。 |
| `cd backend && rtk uv run ruff check .` | PASS |  |
| `cd backend && rtk uv run isort . --check-only` | PASS |  |
| `cd backend && rtk uv run yapf -dr app/ tests/ alembic/ manage.py` | PASS |  |
| `cd backend && rtk uv run mypy app manage.py` | PASS |  |
| `cd backend && rtk uv run pytest tests/unit` | PASS | 263 passed。FastAPI / Starlette 由来の deprecation warning が 1 件。 |
| `cd backend && UV_CACHE_DIR=... TEST_DATABASE_URL=... uv run pytest tests/integration/test_manage_cli.py tests/integration/services/test_auth_repository.py -q -ra` | PASS | 8 passed。sandbox 内 uv panic 回避のため権限外実行。 |
| `cd backend && UV_CACHE_DIR=... DATABASE_URL=... uv run python manage.py db-upgrade` | PASS | sandbox 内 uv panic 回避のため権限外実行。 |
| `cd backend && UV_CACHE_DIR=... TEST_DATABASE_URL=... uv run pytest tests/integration -q -ra` | PASS | 61 passed。FastAPI / Starlette 由来の warning が 4 件。sandbox 内 uv panic 回避のため権限外実行。 |
| `cd backend && UV_CACHE_DIR=... DATABASE_URL=... uv run python manage.py db-check` | PASS | No new upgrade operations detected。sandbox 内 uv panic 回避のため権限外実行。 |
| `cd frontend && rtk npm run check` | PASS | Prettier / ESLint fix / typecheck。 |
| `cd frontend && rtk npm test -- Header` | PASS | 4 files / 17 tests passed。jsdom の `window.scrollTo` warning は非致命。 |
| `cd frontend && rtk npm run check:ci` | PASS |  |
| `cd frontend && rtk npm test` | PASS | 17 files / 88 tests passed。jsdom warning と意図的な 500 test の `ApiError` log は非致命。 |
| `cd frontend && rtk npm run build` | PASS | `%VITE_SITE_URL% is not defined` warning が 3 件。既存の Vite 置換 warning で build は成功。 |
| route import grep for `index.data` / `@/routes` excluding tests | PASS | 実コード側は 0 matches。 |
| `rtk find '' frontend/src/libraries` | PASS | 0 files。空 directory 削除済み。 |
| `rtk docker compose run --rm backend sh -c "uv sync --frozen --group dev && uv run python manage.py db-upgrade"` | PASS | 明示 `DATABASE_URL` 必須化後も compose backend migration 成功。 |
| `cd backend && rtk uv run pytest tests/unit/test_alembic_env.py tests/unit/test_manage.py tests/unit/config/test_database_settings.py -q` | PASS | bare Alembic の明示 `DATABASE_URL` guard を追加検証。 |
| `env -u DATABASE_URL uv --project backend run alembic -c backend/alembic.ini current` from a directory without `.env` | PASS | `DATABASE_URL must be configured explicitly for Alembic.` で失敗することを確認。sandbox 内 uv panic 回避のため権限外実行。 |
| `DATABASE_URL=... uv --project backend run alembic -c backend/alembic.ini current` from a directory without `.env` | PASS | `20260803_0003 (head)` を確認。sandbox 内 uv panic 回避のため権限外実行。 |
| `cd backend && rtk uv run pytest tests/unit` | PASS | 264 passed。FastAPI / Starlette 由来の deprecation warning が 1 件。 |
| `cd backend && DATABASE_URL=... uv run python manage.py db-check` | PASS | No new upgrade operations detected。sandbox 内 uv panic 回避のため権限外実行。 |

未対応事項:

- Phase 5 対象の Review ID は、Claude Code review で指摘されたチェック漏れを含めて完了。
- Phase 6 に送る内容は `documents/plans/20260803-phase6-account-deletion-handoff.md` に申し送りとして分離済み。Phase 5 では public account deletion API は追加しない。
