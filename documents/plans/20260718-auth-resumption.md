# Auth 実装再開・収束計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 2026-04-18 に開始して未コミットのまま停止していた PostgreSQL + Cookie session 認証実装を、競合のない文書、スキップのない統合テスト、独立したセキュリティ／コードレビュー、全品質ゲート、手動 E2E、論理単位のコミットまで収束させる。

**Architecture:** 新機能は追加せず、現在の working tree を復旧対象として扱う。`認証設計の競合解消 → PostgreSQL migration / integration test → frontend 品質ゲート修正 → 全品質ゲート → auth セキュリティ／コードレビュー → same-origin 手動 E2E → 論理単位コミット` の順にゲートを設け、各ゲートが成功するまで次へ進まない。

**Tech Stack:** Python 3.12, FastAPI, SQLModel, SQLAlchemy async, Alembic, PostgreSQL 17, pytest, React 19, TypeScript 5.7, Vite 7, TanStack Router / Query, Vitest, ESLint, Prettier, Docker Compose

## Global Constraints

- 本計画の対象は競合解消、PostgreSQL 統合テスト、品質ゲート、手動 E2E、コミットまでとする。
- GitHub Actions およびその他の CI 実装は対象外とする。
- 認証方式は現在の実装に合わせ、opaque な Cookie session + PostgreSQL 永続化を正とする。JWT / refresh token 方式へ戻さない。
- API surface は `GET /api/auth/csrf`, `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`, `GET /api/auth/me` から増やさない。
- auth の DB integration test は PostgreSQL を正とし、SQLite へ置き換えない。
- frontend の API 呼び出しは相対 `/api/...` とし、same-origin を前提にする。
- 依存追加、DB schema 追加、新しい migration revision は行わない。必要になった場合は計画を停止してユーザー確認を取る。
- `app_test` は本リポジトリ専用の破棄可能な test database としてのみ扱う。共有 DB や保持対象データがある DB では downgrade を実行しない。
- `git reset --hard`, `git clean`, `git checkout --`, volume 削除は使用しない。
- 既存の未コミット変更を保持し、関係のないリファクタリングや警告修正を混ぜない。
- test、品質ゲート、レビューで問題が出た場合、最初は read-only の診断だけを行う。既存 auth contract 内の bugfix でも、変更内容・対象ファイル・追加する回帰テストをユーザーへ提示して承認を得るまで修正しない。
- 修正に依存追加、DB schema / migration、API surface、認証方式、production proxy trust 方針の変更が必要なら本計画を停止し、別計画として再承認を得る。
- Critical / Important のレビュー指摘が 1 件でも未解決なら E2E と commit へ進まない。妥当でない指摘はコードとテストを根拠に理由を記録する。
- shell command はリポジトリの `AGENTS.md` に従い、各 command segment を `rtk` で始める。

---

## Current Baseline

- branch は `feature/db-auth`、HEAD は `eb5db18` で `master` と同じ。
- DB、backend auth、frontend auth の実装は working tree に存在するが、すべて未コミット。
- `documents/plans/20260418-auth-structure.md` に `<<<<<<< ours`, `=======`, `>>>>>>> theirs` が残っている。
- backend test は 36 件収集されるが、`TEST_DATABASE_URL` なしでは 18 passed / 18 skipped。
- frontend test は 6 files / 10 tests が成功し、build も成功する。
- frontend 全体の ESLint は JavaScript config file が TypeScript project に入らず 2 errors になる。
- `.github/workflows/` は存在しないが、本計画では追加しない。

## Failure Recovery Protocol

test、format / lint / build、security / code review、manual E2E のいずれかが予期せず失敗した場合は、失敗した Task に関係なく次を順番どおり実行する。Expected failure と exact fix が事前承認済みの red gate は例外とし、本計画では Task 4 Step 1 の既知 ESLint 2 errors だけが該当する。error の file、件数、理由が Expected と異なる場合は red gate とみなさず本 protocol を適用する。

1. 直ちに次 Task への進行と staging / commit を止める。
2. failing command、exit status、passed / skipped / failed 件数、再現操作を記録する。evidence file 作成前なら一時的に Task output として保持し、Task 6 Step 4 で転記する。
3. `superpowers:systematic-debugging` を使い、file を変更せず root cause を特定する。
4. 既存 auth contract 内の bugfix か、scope expansion かを判定する。依存、schema、migration、API surface、認証方式、production proxy trust 方針の変更が必要なら本計画を停止する。
5. 既存 contract 内で修正できる場合も、security impact、変更 file、追加する automated regression test、最小修正、再検証範囲をユーザーへ提示し、承認を得る。
6. 承認後、既存 pytest / Vitest で failing regression test を先に追加し、意図した理由で FAIL することを確認する。既存依存で自動化できない場合は実装せず、別計画として再承認を得る。
7. 最小修正を実装し、targeted regression test を PASS させる。
8. Task 3〜5 の影響する個別 gate と Task 5 の full gate を再実行する。
9. fresh reviewer で Task 6 を再実行し、Critical 0、Important 0、`Ready to commit: Yes` を得る。
10. manual E2E 開始後の修正なら Task 7 を最初から再実行する。
11. evidence には失敗した attempt を削除せず、`Superseded` として root cause / disposition を残し、最新の test count、exit status、review verdict、E2E 結果を追記する。
12. Task 8 の code commit 後に failure が判明した場合は既存 commit を amend / rebase せず、承認済み regression test と fix を `fix(auth): ...` の追加 commit にする。追加 commit と理由を evidence に記録する。
13. 最新 attempt が全 gate で 0 skipped / 0 failed になるまで進行を再開しない。

## File Structure

### Resolve and document

- Modify: `documents/plans/20260418-auth-structure.md` — Cookie session 設計を正として競合を解消する。
- Keep: `documents/plans/20260418-auth-db-migration.md` — DB 実装の履歴資料として保持する。
- Keep: `documents/plans/20260418-auth-backend-flow.md` — backend 実装の履歴資料として保持する。
- Keep: `documents/plans/20260418-auth-frontend-integration.md` — frontend 実装の履歴資料として保持する。
- Keep: `documents/plans/20260418-auth-delivery-notes.md` — 環境変数と E2E 方針の参照元として保持する。
- Create: `documents/plans/20260718-auth-resumption.md` — 再開後の single source of truth。
- Create during execution: `documents/plans/20260718-auth-resumption-evidence.md` — review verdict、品質ゲート、手動 E2E の実測結果を残す。
- Out of scope follow-up: `documents/plans/20260718-admin-user-seed-design.md` — ユーザーから別途依頼されたlocal用seedの設計。Task 8の認証本体commitには混在させず、本計画のreview gate完了後に再開する。

### Verify and minimally adjust

- Verify: `backend/alembic/versions/20260418_0001_create_auth_tables.py`
- Verify: `backend/tests/integration/conftest.py`
- Verify: `backend/tests/integration/test_auth_schema.py`
- Verify: `backend/tests/integration/test_auth_controller.py`
- Review: `backend/app/config/auth.py`, auth controllers / dependencies, auth libraries, repository / usecase, auth models / migration
- Review: `frontend/src/lib/`, `frontend/src/hooks/useAuthSession.ts`, login / protected routes, Header auth flow
- Modify: `frontend/tsconfig.json` — ESLint が root の JavaScript config files を解析できるよう `allowJs` を有効化する。
- Modify: `docker-compose.yaml` — frontend container の Vite proxy を `http://backend:8000` へ向ける。

### Commit groups

1. Local auth infrastructure
2. PostgreSQL persistence + Backend auth flow
3. Frontend auth flow + frontend test
4. Guides, plans, and verification evidence

---

### Task 1: 作業ツリーを復旧対象として固定する

**Files:**
- Inspect: repository root and all untracked auth files

**Interfaces:**
- Consumes: current `feature/db-auth` working tree
- Produces: 復旧対象ファイル一覧と、破壊的操作を行わないための baseline gate

- [x] **Step 1: branch、HEAD、変更一覧を記録する**

Run:

```bash
rtk git status --short --branch
rtk git log --oneline --decorate -5
rtk git diff --stat
rtk git diff --check
```

Expected:

- current branch が `feature/db-auth`
- HEAD が `eb5db18`
- auth 関連の modified / untracked files が表示される
- `git diff --check` は whitespace error なし

- [x] **Step 2: 復旧対象の未追跡ファイルを確認する**

Run:

```bash
rtk git ls-files --others --exclude-standard
```

Expected: `backend/alembic/`, backend auth files/tests, frontend auth files/tests, `docker/postgres/init/`, 本計画書が含まれる。

- [x] **Step 3: destructive command を使わないことを確認して次へ進む**

Run: なし

Expected: stash、reset、clean、checkout、volume 削除を行わず、現在の working tree をそのまま復旧対象にする。

- [x] **Step 4: baseline が計画の前提と一致することを判定する**

Run: なし

Expected: branch、HEAD、変更ファイルが `Current Baseline` と一致し、表示される変更がすべて auth 復旧対象である。一致しない場合、または unrelated な変更が 1 件でもある場合はファイルを変更せずに停止し、差分をユーザーへ報告して本計画の staging list と最終 assertion を更新する。現在確認済みの baseline では unrelated な変更は 0 件。

---

### Task 2: 認証設計文書の競合を Cookie session 方針で解消する

**Files:**
- Modify: `documents/plans/20260418-auth-structure.md:1`

**Interfaces:**
- Consumes: backend / frontend がすでに実装している Cookie session contract
- Produces: 競合マーカーがなく、他の認証計画と整合する設計文書

- [x] **Step 1: 競合状態を再確認する**

Run:

```bash
rtk grep -n '^<<<<<<<|^=======|^>>>>>>>' documents/plans/20260418-auth-structure.md
```

Expected: line 1, 363, 695 の 3 箇所が検出される。

- [x] **Step 2: `ours` の Cookie session 設計だけを残す**

編集規則:

- `<<<<<<< ours` を削除する。
- `=======` から `>>>>>>> theirs` までの古い JWT / refresh token 設計を削除する。
- `# 認証アーキテクチャ決定メモ（2026-04-18）` から始まる Cookie session 設計本文は保持する。
- session-bound CSRF、`SameSite=Lax`、PostgreSQL の `auth_sessions`、5 endpoint の記述は保持する。

- [x] **Step 3: conflict marker と文書差分を検査する**

Run:

```bash
rtk grep -n '^<<<<<<<|^=======|^>>>>>>>' documents/plans/20260418-auth-structure.md
rtk git diff --check
rtk git diff -- documents/plans/20260418-auth-structure.md
```

Expected:

- conflict marker の検索結果が 0 件
- whitespace error なし
- JWT / refresh token 側の重複文書だけが削除され、Cookie session 側の追加事項が残る

- [x] **Step 4: 実装計画との用語整合を確認する**

Run:

```bash
rtk grep -n 'Cookie session|auth_sessions|/api/auth/csrf|/api/auth/me' documents/plans/20260418-auth-structure.md documents/plans/20260418-auth-backend-flow.md documents/plans/20260418-auth-frontend-integration.md
```

Expected: 3 文書が同じ Cookie session と 5 endpoint を参照する。

---

### Task 3: PostgreSQL migration と integration test をスキップなしで通す

**Files:**
- Verify: `docker-compose.yaml`
- Verify: `docker/postgres/init/01-create-test-database.sql`
- Verify: `backend/alembic/versions/20260418_0001_create_auth_tables.py`
- Test: `backend/tests/integration/test_auth_schema.py`
- Test: `backend/tests/integration/test_auth_controller.py`

**Interfaces:**
- Consumes: PostgreSQL 17 service, synchronous Alembic URL, asynchronous pytest URL
- Produces: upgrade / downgrade 可能な test schema と、18 件すべて成功する PostgreSQL integration test

- [x] **Step 1: PostgreSQL 17 を起動する**

Run from repository root:

```bash
rtk docker compose up -d postgres
rtk docker compose ps postgres
```

Expected: `postgres` が `running (healthy)` になる。

- [x] **Step 2: `app_test` database の存在を確認する**

Run:

```bash
rtk docker compose exec -T postgres psql -U app -d postgres -tAc "SELECT datname FROM pg_database WHERE datname = 'app_test';"
```

Expected: `app_test` が 1 行返る。

If no row is returned, run exactly once:

```bash
rtk docker compose exec -T postgres psql -U app -d postgres -c "CREATE DATABASE app_test;"
```

Expected: `CREATE DATABASE`。

- [x] **Step 3: destructive migration test の対象と承認を確認する**

Run:

```bash
rtk docker compose exec -T postgres psql -U app -d app_test -tAc "SELECT current_database(), current_user;"
```

Expected: `app_test|app` が返る。実行者は、`app_test` が本リポジトリ専用で保持対象データを含まないことをユーザーへ示し、downgrade 実行の承認を得る。共有 DB、database 名の不一致、保持対象データの可能性がある場合は停止する。

- [x] **Step 4: test DB で upgrade → downgrade → upgrade を検証する**

Run from `backend/`:

```bash
rtk uv run python manage.py --help
rtk uv run python manage.py db-upgrade --help
rtk uv run python manage.py db-downgrade --help
rtk proxy env ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run python manage.py db-upgrade --revision head
rtk proxy env ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run python manage.py db-downgrade --revision base
rtk proxy env ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run python manage.py db-upgrade --revision head
```

Expected: help に `db-upgrade`, `db-downgrade` と `--revision` が表示され、6 commands が exit 0。最後に `users`, `auth_sessions`, `auth_audit_logs` が存在する。

- [x] **Step 5: schema integration test を通す**

Run from `backend/`:

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_schema.py -v
```

Expected: baseline の 2 件以上が passed、0 skipped、0 failed。

- [x] **Step 6: auth controller integration test を通す**

Run from `backend/`:

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration/test_auth_controller.py -v
```

Expected: baseline の 16 件以上が passed、0 skipped、0 failed。register / login / me / logout、session rotation、CSRF、rate limit が成功する。

- [x] **Step 7: integration test に skip がないことを明示確認する**

Run from `backend/`:

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest tests/integration -q
```

Expected: baseline の 18 件以上が passed、0 skipped、0 failed。1 件でも skipped / failed があれば Task 4 へ進まず、Global Constraints の失敗時フローに従って `superpowers:systematic-debugging` で read-only 診断する。

---

### Task 4: Frontend の正式な品質ゲートと Docker Compose proxy を修正する

**Files:**
- Modify: `frontend/tsconfig.json`
- Modify: `docker-compose.yaml`
- Test: frontend whole-tree ESLint
- Test: Docker Compose rendered config

**Interfaces:**
- Consumes: TanStack ESLint config and `VITE_BACKEND_ORIGIN`
- Produces: root config files を含めて成功する ESLint と、frontend container から backend service へ到達する `/api` proxy

- [x] **Step 1: whole-tree ESLint の既知エラーを再現する**

Run from `frontend/`:

```bash
rtk proxy npx eslint .
```

Expected: `eslint.config.js` と `prettier.config.js` に対し、`parserOptions.project` の project 対象外 error が合計 2 件出る。

- [x] **Step 2: TypeScript project で JavaScript config files を許可する**

`frontend/tsconfig.json` の `compilerOptions` に次を追加する。

```json
{
  "compilerOptions": {
    "allowJs": true
  }
}
```

既存の `target`, `jsx`, `module`, `strict`, `paths` は変更しない。
`include` に残っている実在しない `vite.config.js` は削除する。実ファイル `vite.config.ts` は既存の `**/*.ts` で対象になるため、個別追加しない。

- [x] **Step 3: whole-tree ESLint と TypeScript build を通す**

Run from `frontend/`:

```bash
rtk proxy npx eslint .
rtk npm run build
```

Expected: 両方 exit 0。build 時の既存 `%VITE_SITE_URL%` warning は本計画の auth scope 外とし、build failure として扱わない。

- [x] **Step 4: frontend container の proxy target を backend service 名へ向ける**

`docker-compose.yaml` の `frontend` service に次を追加する。

```yaml
environment:
  VITE_BACKEND_ORIGIN: http://backend:8000
```

既存の `depends_on`, `ports`, `volumes` は保持する。

- [x] **Step 5: Compose の解決済み設定を検査する**

Run from repository root:

```bash
rtk docker compose config
```

Expected: `frontend.environment.VITE_BACKEND_ORIGIN` が `http://backend:8000`、backend の `DATABASE_URL` が `postgresql+asyncpg://app:app@postgres:5432/app` と表示される。

- [x] **Step 6: 正式な frontend check を通す**

Run from `frontend/`:

```bash
rtk npm run check
rtk proxy npx prettier --check .
rtk proxy npx eslint .
```

Expected: format / lint error なし。`npm run check` が変更したファイルは Prettier / ESLint による機械的差分だけであることを `rtk git diff -- frontend` で確認する。

---

### Task 5: Backend / Frontend の全品質ゲートを連続で通す

**Files:**
- Test: `backend/app/`, `backend/tests/`, `backend/alembic/`
- Test: `frontend/src/`, frontend config files

**Interfaces:**
- Consumes: Task 2〜4 で安定化した working tree
- Produces: commit 前の green baseline

- [x] **Step 1: backend full test を PostgreSQL 付きで通す**

Run from `backend/`:

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest
```

Expected: baseline の 36 件以上が passed、0 skipped、0 failed。

- [x] **Step 2: backend import / format gate を通す**

Run from `backend/`:

```bash
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/
```

Expected: isort exit 0、yapf の diff 出力なし。

- [x] **Step 3: frontend test を通す**

Run from `frontend/`:

```bash
rtk npm test
```

Expected: baseline の 6 test files / 10 tests 以上が passed、0 skipped、0 failed。

- [x] **Step 4: frontend check と build を通す**

Run from `frontend/`:

```bash
rtk npm run check
rtk npm test
rtk npm run build
```

Expected: `npm run check` と build が exit 0、`npm test` は baseline の 6 files / 10 tests 以上が passed、0 skipped、0 failed。build output は `backend/static/` に生成されるが Git 管理対象にはならない。

- [x] **Step 5: repository 全体の機械的問題を確認する**

Run from repository root:

```bash
rtk git diff --check
rtk proxy rg -n --glob '!frontend/node_modules/**' '^<<<<<<< |^=======$|^>>>>>>> ' backend frontend documents
rtk git status --short
```

Expected: whitespace error と conflict marker が 0 件。`rg` は no match のため exit 1 になるが、出力が空ならこの検査は成功と扱う。status には認証実装と本計画に関係する変更だけが残る。

---

### Task 6: Auth 実装を独立したセキュリティ／コードレビューへ通す

**Files:**
- Review: `backend/app/config/auth.py`
- Review: `backend/app/controllers/auth_controller.py`
- Review: `backend/app/controllers/auth_dependencies.py`
- Review: `backend/app/libraries/password_hasher.py`
- Review: `backend/app/libraries/session_tokens.py`
- Review: `backend/app/libraries/auth_rate_limiter.py`
- Review: `backend/app/services/auth_repository.py`
- Review: `backend/app/usecases/auth_usecase.py`
- Review: `backend/app/models/user.py`
- Review: `backend/app/models/auth_session.py`
- Review: `backend/app/models/auth_audit_log.py`
- Review: `backend/alembic/versions/20260418_0001_create_auth_tables.py`
- Review: `frontend/src/lib/apiClient.ts`
- Review: `frontend/src/lib/authApi.ts`
- Review: `frontend/src/hooks/useAuthSession.ts`
- Review: `frontend/src/routes/login.tsx`
- Review: `frontend/src/routes/app.tsx`
- Review: `frontend/src/components/organisms/Header/index.tsx`
- Create: `documents/plans/20260718-auth-resumption-evidence.md`

**Interfaces:**
- Consumes: Task 2〜5 で競合解消・統合検証・品質ゲートを通した working tree
- Produces: Critical / Important が 0 件の独立レビュー verdict、または承認済み回帰テスト付き bugfix と再レビュー結果

- [x] **Step 1: review baseline と対象差分を固定する**

Run from repository root:

```bash
rtk git rev-parse HEAD
rtk git status --short
rtk git diff --stat eb5db18
rtk git diff --check
```

Expected: base が `eb5db18`、対象は current working tree の tracked diff と untracked auth files。レビュー中は working tree、index、HEAD を変更しない。

- [x] **Step 2: `superpowers:requesting-code-review` で fresh reviewer を起動する**

Reviewer input:

- Description: PostgreSQL-backed opaque Cookie session authentication for FastAPI + React SPA
- Requirements: `documents/plans/20260418-auth-structure.md`, `documents/plans/20260418-auth-db-migration.md`, `documents/plans/20260418-auth-backend-flow.md`, `documents/plans/20260418-auth-frontend-integration.md`, 本計画の Global Constraints
- Base: `eb5db18`
- Head: current uncommitted working tree。`git diff eb5db18` に加え、`git status --short` の untracked files を直接読む
- Mode: read-only。working tree、index、HEAD、branch、database、container を変更しない

Reviewer must inspect and report file:line evidence for:

1. password policy、Argon2 hash / verify、存在しない user と password mismatch の timing差
2. session token entropy / hash、absolute / idle expiry、login / register 時の rotation、logout revoke、session fixation
3. `HttpOnly`, `Secure`, `SameSite`, `Path`, `Max-Age` と production / reverse proxy 判定
4. CSRF double-submit の timing-safe 比較、session-bound CSRF、token 再発行時の整合
5. `X-Forwarded-For` / client IP の trust boundary、rate-limit key、register / login bucket、single-process 制約と bypass 可能性
6. email enumeration、status code、error body、audit log に secret / raw token / password が残らないこと
7. DB constraints、unique / lookup index、timezone-aware expiry、migration downgrade
8. frontend redirect allowlist、401 と network / 5xx の区別、credentials / relative `/api`、logout cache invalidation
9. controller → usecase → repository の依存方向と transaction / race condition
10. test が上記の security contract を実際に検証し、mock だけで成立していないこと

Expected: Strengths、Critical / Important / Minor、file:line、修正理由、`Ready to commit: Yes | No | With fixes` を含む review report。

- [x] **Step 3: review feedback を技術的に判定する**

Procedure:

1. `superpowers:receiving-code-review` を使う。
2. 各指摘を現行コード、既存 contract、test で再検証する。
3. Critical / Important が妥当なら commit を block する。
4. 妥当でない指摘は、反証する file:line と test 名を evidence に記録する。
5. Minor は auth security、correctness、data loss に関係するものだけ本計画で扱い、それ以外は follow-up として evidence に記録する。

Expected: 採用／不採用／保留の理由が全指摘について一意になる。

- [x] **Step 4: review と品質ゲートの実測証跡を作る**

`documents/plans/20260718-auth-resumption-evidence.md` を作成し、次を実測値で記載する。

- 実行日時と branch / base SHA
- migration upgrade / downgrade / upgrade の結果
- backend passed / skipped / failed 件数
- frontend test file / test passed / skipped / failed 件数
- isort / yapf / Prettier / ESLint / build の exit status
- review の reviewer、Critical / Important / Minor 件数、各指摘の disposition、最終 verdict
- 手動 E2E は Task 7 完了後に、使用した timestamp email、確認項目、結果を追記する

Expected: 空欄、`TBD`、推測値を含まず、実行済みの結果だけが記録される。Task 7 未実行時点では manual E2E section 自体をまだ作らない。

- [x] **Step 5: Critical / Important がある場合は修正前に停止する**

Expected: まず read-only で root cause と最小修正案を特定する。ユーザーへ次を提示して承認を得るまで file を変更しない。

- 指摘と security impact
- 変更対象 file と既存 contract への影響
- 先に追加する failing regression test と期待 failure
- 最小 implementation change
- 依存、schema、migration、API、proxy trust 方針の変更有無

- [x] **Step 6: 承認された bugfix を test-first で適用する**

Applicable only when Step 5 でユーザー承認を得た場合:

1. 指摘を再現する regression test を追加する。
2. targeted test を実行し、意図した理由で FAIL することを確認する。
3. 既存 auth contract 内の最小修正を実装する。
4. targeted test が PASS することを確認する。
5. Task 3〜5 の該当ゲートをすべて再実行する。
6. Step 2 の fresh reviewer で再レビューする。
7. Failure Recovery Protocol に従い、失敗 attempt を `Superseded` として保持したまま最新結果を evidence に追記する。

Expected: Critical / Important が 0 件になるまで Task 7 へ進まない。依存、schema、migration、API、認証方式、proxy trust 方針の変更が必要と判明した場合は実装せず、本計画を停止する。

- [ ] **Step 7: review gate を閉じる**

Expected: evidence に記録された最新 review verdict が `Ready to commit: Yes`、Critical 0、Important 0。Minor の未対応項目は理由付きで evidence に残る。

---

### Task 7: same-origin の手動 E2E を完走する

**Files:**
- Verify: `docker-compose.yaml`
- Verify: `frontend/vite.config.ts`
- Verify: `backend/app/controllers/auth_controller.py`
- Verify: browser routes `/login` and `/app`

**Interfaces:**
- Consumes: Docker Compose frontend → backend `/api` proxy、PostgreSQL app database
- Produces: browser reload をまたいで成立する register / login / me / logout / route guard の確認結果

- [ ] **Step 1: Docker build と依存取得の前提を確認する**

Run from repository root:

```bash
rtk docker compose images
rtk docker compose ps
```

Expected: Docker engine が利用できる。backend image build や空の `frontend_node_modules` volume により image download / `npm ci` が必要な場合は、依存取得を伴うことをユーザーへ示して承認を得る。承認前に build を開始しない。

- [ ] **Step 2: full local stack を build して起動する**

Run from repository root:

```bash
rtk docker compose up -d --build postgres backend frontend
rtk docker compose ps
```

Expected: postgres が healthy、backend と frontend が running。frontend は `http://localhost:3000`、backend は `http://localhost:8000` で応答する。

- [ ] **Step 3: runtime DB に migration を適用する**

Before Run: `docker-compose.yaml` の `ALEMBIC_DATABASE_URL=postgresql://app:app@postgres:5432/app` をユーザーへ示し、runtime DB への migration 実行承認を得る。承認前に実行しない。

Run:

```bash
rtk docker compose exec -T backend uv run python manage.py db-upgrade --revision head
rtk proxy curl -fsS http://localhost:8000/api/healthz
```

Expected: migration exit 0、health endpoint が 2xx を返す。

- [ ] **Step 4: API 経由で E2E ユーザーを登録する**

Run in zsh from repository root:

```bash
auth_e2e_cookie_jar=/private/tmp/python-react-template-auth-e2e.cookies
auth_e2e_email="auth-e2e-$(rtk proxy date +%s)@example.com"
auth_e2e_csrf_token="$(rtk proxy curl -fsS -c "$auth_e2e_cookie_jar" http://localhost:3000/api/auth/csrf | rtk proxy python3 -c 'import json,sys; print(json.load(sys.stdin)["csrfToken"])')"
rtk proxy curl -fsS -b "$auth_e2e_cookie_jar" -c "$auth_e2e_cookie_jar" -H 'Content-Type: application/json' -H "X-CSRF-Token: $auth_e2e_csrf_token" -d "{\"email\":\"$auth_e2e_email\",\"password\":\"Password123!\"}" http://localhost:3000/api/auth/register
rtk proxy printf '%s\n' "$auth_e2e_email"
```

Expected: register response と最後の出力に、timestamp を含む同じ E2E email address が表示される。以降の browser 操作では、最後に表示された email address を使う。

- [ ] **Step 5: browser で invalid credential を確認する**

Actions:

1. `http://localhost:3000/login` を開く。
2. Task 7 Step 4 の最後に表示された email、password に `WrongPassword123!` を入力する。
3. submit する。

Expected: `/app` へ遷移せず、credential error が表示される。

- [ ] **Step 6: browser で login、me、reload を確認する**

Actions:

1. Task 7 Step 4 の最後に表示された email、password に `Password123!` を入力して login する。
2. `/app` に遷移することを確認する。
3. 同じ browser session で `http://localhost:3000/api/auth/me` を開く。
4. browser back で `/app` へ戻り、reload する。

Expected: `/api/auth/me` の `email` が Task 7 Step 4 で表示された email と完全一致し、reload 後も `/app` を維持する。Header に表示される account identity も同じ email と一致する。

- [ ] **Step 7: logout と protected route guard を確認する**

Actions:

1. Header の logout を実行する。
2. `/login` に戻ることを確認する。
3. address bar から `http://localhost:3000/app` を直接開く。

Expected: `/login?redirect=%2Fapp` 相当へ redirect され、protected content が表示されない。

- [ ] **Step 8: 手動 E2E の実測結果を evidence に追記する**

`documents/plans/20260718-auth-resumption-evidence.md` に次の実測値を追記する。

- 実行日時
- Task 7 Step 4 で生成した email
- invalid credential が拒否された結果
- login 後の route と `/api/auth/me` の一致 email
- reload 後の session 維持結果
- logout 後の redirect と `/app` guard 結果
- 使用した frontend / backend URL

Expected: 全項目が実測値と `PASS` / `FAIL` で記録される。1 項目でも `FAIL` なら commit へ進まず、Global Constraints の失敗時フローへ戻る。

- [ ] **Step 9: 最終検証のため container を稼働したままにする**

Run: なし

Expected: Task 8 の PostgreSQL-backed final gate が完了するまで postgres、backend、frontend を停止しない。

---

### Task 8: 検証済み変更を論理単位でコミットする

**Files:**
- Commit group 1: Docker Compose / PostgreSQL init / local proxy infrastructure
- Commit group 2: PostgreSQL persistence / Backend auth / backend tests
- Commit group 3: Frontend auth / frontend tests
- Commit group 4: AGENTS guides / auth plans / resumption plan / verification evidence

**Interfaces:**
- Consumes: Task 5 の全品質ゲート、Task 6 の review gate、Task 7 の手動 E2E が成功した working tree
- Produces: 依存順に review できる基準 4 commits、必要な場合だけ承認済み `fix(auth): ...` commits、完全に clean な working tree

- [ ] **Step 1: local auth infrastructure を stage して検査する**

Run from repository root:

```bash
rtk git add docker-compose.yaml docker/postgres/init
rtk git diff --cached --check
rtk git diff --cached --stat
rtk docker compose config
```

Expected: PostgreSQL 17、`app_test` init、backend / frontend service、`VITE_BACKEND_ORIGIN=http://backend:8000` の infrastructure 差分だけが staged される。

- [ ] **Step 2: local auth infrastructure commit を作る**

Run:

```bash
rtk git commit -m "feat(infra): add local postgres auth stack"
```

Expected: commit 成功。

- [ ] **Step 3: PostgreSQL persistence と Backend auth を stage する**

Run from repository root:

```bash
rtk git add backend/.env.example backend/alembic.ini backend/alembic backend/app/bootstrap/container.py backend/app/bootstrap/route.py backend/app/config/auth.py backend/app/config/database.py backend/app/controllers/auth_controller.py backend/app/controllers/auth_dependencies.py backend/app/interfaces/services backend/app/interfaces/usecases backend/app/libraries/auth_rate_limiter.py backend/app/libraries/database_engine.py backend/app/libraries/password_hasher.py backend/app/libraries/session_tokens.py backend/app/models backend/app/services backend/app/usecases backend/manage.py backend/pyproject.toml backend/uv.lock backend/tests
rtk git diff --cached --check
rtk git diff --cached --stat
```

Expected: PostgreSQL config / migration / models、Backend auth、全 backend tests だけが staged される。integration fixture は `create_app()` 経由で Backend auth を import するため、DB と Backend を分割しない。

- [ ] **Step 4: staged 状態で Backend の全品質ゲートを再確認する**

Run from `backend/`:

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/
```

Expected: baseline の 36 件以上が passed / 0 skipped / 0 failed、isort / yapf clean。

- [ ] **Step 5: PostgreSQL + Backend auth commit を作る**

Run:

```bash
rtk git commit -m "feat(backend/auth): add postgres cookie sessions"
```

Expected: commit 成功。

- [ ] **Step 6: Frontend auth を stage して検査する**

Run:

```bash
rtk git add frontend/tsconfig.json frontend/vite.config.ts frontend/src/main.tsx frontend/src/routeTree.gen.ts frontend/src/routes/__root.tsx frontend/src/routes/login.tsx frontend/src/routes/app.tsx frontend/src/routes/app.test.tsx frontend/src/components/organisms/Auth frontend/src/components/organisms/Header frontend/src/components/organisms/LandingPage/index.test.tsx frontend/src/hooks frontend/src/lib
rtk git diff --cached --check
rtk git diff --cached --stat
```

Expected: frontend auth、route guard、Header、tests、ESLint project 修正だけが staged される。`docker-compose.yaml` の frontend proxy は infrastructure commit に含まれている。

- [ ] **Step 7: staged 状態で Frontend の全品質ゲートを再確認する**

Run from `frontend/`:

```bash
rtk proxy npx prettier --check .
rtk proxy npx eslint .
rtk npm test
rtk npm run build
```

Expected: non-mutating format / lint が clean、baseline の 6 files / 10 tests 以上が passed、0 skipped、0 failed、build exit 0。

- [ ] **Step 8: Frontend auth commit を作る**

Run:

```bash
rtk git commit -m "feat(frontend/auth): add login and protected session flow"
```

Expected: commit 成功。

- [ ] **Step 9: code commits 後の最終品質ゲートを非破壊コマンドで再実行する**

Run from `backend/`:

```bash
rtk proxy env TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run pytest
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/
```

Run from `frontend/`:

```bash
rtk proxy npx prettier --check .
rtk proxy npx eslint .
rtk npm test
rtk npm run build
```

Expected: backend baseline 36 件以上 passed / 0 skipped / 0 failed、frontend baseline 6 files / 10 tests 以上 passed / 0 skipped / 0 failed、format / lint / build が exit 0。

- [ ] **Step 10: final gate の実測値を evidence に追記する**

`documents/plans/20260718-auth-resumption-evidence.md` に Task 8 Step 9 の各 command、件数、exit status を追記する。

Expected: pre-commit gate と code commits 後の final gate が区別され、実測値だけが記録される。

- [ ] **Step 11: local container を volume を残して停止する**

Run from repository root:

```bash
rtk docker compose stop frontend backend postgres
```

Expected: container は停止するが、volume は削除されない。

- [ ] **Step 12: guides、plans、verification evidence を stage して検査する**

Run:

```bash
rtk git add backend/AGENTS.md frontend/AGENTS.md documents/plans/20260418-auth-structure.md documents/plans/20260418-auth-db-migration.md documents/plans/20260418-auth-backend-flow.md documents/plans/20260418-auth-frontend-integration.md documents/plans/20260418-auth-delivery-notes.md documents/plans/20260718-auth-resumption.md documents/plans/20260718-auth-resumption-evidence.md
rtk git diff --cached --check
rtk git diff --cached --stat
```

Expected: auth guide、競合解消済み設計、既存計画の実施記録、本再開計画、review / quality / E2E / final gate の実測 evidence だけが staged される。evidence に空欄、`TBD`、未実行の成功記録がない。

- [ ] **Step 13: documentation and evidence commit を作る**

Run:

```bash
rtk git commit -m "docs(auth): record implementation and recovery verification"
```

Expected: commit 成功。

- [ ] **Step 14: clean working tree と commit history を厳密確認する**

Run from repository root:

```bash
rtk git status --short --branch
rtk git log --oneline --decorate -6
```

Expected:

- `git status --short` の出力が空。Task 1 baseline で unrelated change は 0 件なので、1 行でも残れば完了にしない
- `feature/db-auth` に infrastructure、PostgreSQL + backend auth、frontend auth、docs + evidence の基準 4 commits が順に存在する。承認済み failure recovery が発生した場合だけ、対応する `fix(auth): ...` commit が追加されている
- `backend/static/` の build artifact は status に現れない

---

## Completion Criteria

次をすべて満たした時だけ本計画を完了とする。

- `20260418-auth-structure.md` に conflict marker がない。
- test DB で Alembic upgrade → downgrade → upgrade が成功する。
- backend test が baseline の 36 件以上 passed / 0 skipped / 0 failed。
- backend isort / yapf が clean。
- frontend test が baseline の 6 files / 10 tests 以上 passed / 0 skipped / 0 failed。
- frontend の正式な `npm run check` と build が成功する。
- auth security / code review が Critical 0、Important 0、`Ready to commit: Yes` で閉じている。
- test、品質ゲート、review failure への修正は、ユーザー承認、failing regression test、再レビューを経ている。
- Docker Compose の frontend `/api` proxy が backend service へ到達する。
- browser で invalid login、valid login、`/app`、`/api/auth/me`、reload、logout、route guard を確認する。
- review、品質ゲート、manual E2E の実測値が `20260718-auth-resumption-evidence.md` に記録されている。
- 変更が infrastructure、PostgreSQL + backend auth、frontend auth、docs + evidence の基準 4 commits に分かれている。承認済み failure recovery の追加 commit がある場合は evidence に理由が記録されている。
- `git status --short` の出力が空で、列挙 staging の取りこぼしがない。
- GitHub Actions は追加されていない。
