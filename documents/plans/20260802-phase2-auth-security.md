# Phase 2 認証セキュリティ強化 実装計画

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Worktree、`git add`、`git commit`、`git push`は使用しない。

**Goal:** `documents/reviews/20260801-review.md`のPhase 2で指定された認証セキュリティ項目を、Phase 1で整えたDI / UoW / error envelope基盤の上に実装する。

**Architecture:** 認証境界の既定値を安全側へ倒し、unsafe API requestは純ASGI middlewareでCSRF検証を必ず通す。認証usecaseはArgon2を専用executorへ逃がし、同時実行数を設定で制限する。rate limitは「失敗時に記録」へ変更し、session touch、CSRF status、DB schema正典を明示的な型と設定で制御する。

**Tech Stack:** Python 3.12、FastAPI、Starlette middleware、Injector、SQLModel、SQLAlchemy/Alembic、pwdlib[argon2]、pytest、pytest-asyncio、PostgreSQL

---

## Global Constraints

- Worktreeは使わず、現在のbranchとworking treeで作業する。
- `git add`、`git commit`、`git push`、`git reset`、`git checkout --`、`git clean`は実行しない。
- DB schema変更を含むため、実装者はTask 2開始前にユーザーへ「初期migrationを書き換える」方針でよいか確認する。
- 新規Alembic revisionは作らない。現時点では初期revision 1本だけなので、Phase 2では既存初期migrationをテンプレート正典として更新する。
- 既存のローカル開発DBを破壊的に作り直す操作は、ユーザーの明示確認なしで実行しない。検証は`app_test`などtest DBを使う。
- 依存追加はしない。Argon2 thread化は専用`ThreadPoolExecutor`で実装し、executorの`max_workers`で同時実行数とArgon2メモリ使用量の上限を制御する。
- frontend配下は変更しない。register UIやfrontend error message整理はPhase 3で扱う。
- Phase 2の主対象は`P1-10`、`P1-11`、`P1-12`、`P1-14`、`P1-20`、`P2-6`、`P2-13`、`P2-14`、`P2-15`、`P2-16`、`P2-19`とする。
- `P2-24`のrate limiter interface化は、Phase 2でrate limiterを触るため同時に最小実装する。ただし共有store実装は行わない。
- ユーザーが本依頼で`git add` / `git commit`を禁止しているため、小さなcommit単位には分けない。代わりにTaskごとに`.superpowers/checkpoints/phase2/`へpatchとuntracked一覧を保存する。

## 背景

Phase 0では、SQLModel metadataとAlembic migrationの整合、SPA fallback、static起動、非ASCII CSRF 500、sample controllerの誤ったHTTP statusを修正した。Phase 1では、controllerの`Depends`化、Injector module/provider化、`AsyncEngine.dispose()`、Unit of Work、error envelope、docs制御、`AuthenticatedSessionContext`移設、`IssuedAuthSession`導入を完了した。

レビュー文書の推奨順序では、次のPhase 2が「セキュリティ強化」として定義されている。

- `P1-10`: Argon2のhash/verifyがasync関数内でevent loopをブロックしている。
- `P1-11`: リバースプロキシ配下で`request.client.host`だけを見るため、全ユーザーのrate limitと監査ログIPがプロキシIPへ潰れる。
- `P1-12`: `AuthSettings.ENVIRONMENT`未設定時にSecure cookieが外れる危険側の既定値になっている。
- `P1-14`: CSRF検証がrouteごとの`Depends(require_csrf)`に依存し、新規unsafe endpointで書き忘れが起きる。
- `P1-20`: OAuth追加前に`users.password_hash`をnullableへ変える必要がある。
- `P2-6`: SQLModel metadataにnaming conventionがなく、将来のconstraint操作やテンプレート一貫性に支障がある。
- `P2-13`: email単独のrate limit bucketがなく、分散IPから単一アカウントへのpassword sprayを止められない。
- `P2-14`: `validate_session_csrf()`の`bool | None`戻り値が壊れやすい。
- `P2-15`: 認証済みrequestごとに`touch_session()`のUPDATEが走る。
- `P2-16`: registerの409がユーザー列挙経路になっている。
- `P2-19`: login成功時にrate limit bucketがresetされず、正常ログインもquotaを消費する。

Phase 1の未対応事項にも、Phase 2へ渡す追加注意が残っている。`/api/auth/me`の401に`Cache-Control: no-store`が付かない問題、`database_engine`のURL parameter露出防止は、認証セキュリティ作業と同時に扱う。pre-session CSRF cookieの信頼境界は、Phase 2では現行のdouble-submit許可を維持し、`__Host-` cookie prefixやcookie helper統合と一緒に後続Phaseへ送る。

## 現行コードの分析

- `backend/app/config/auth.py`の`AuthSettings.ENVIRONMENT`は`"local"`が既定値であり、Phase 1の`backend/AGENTS.md`は「Phase 2で反転するまで安易に揃えない」と明記している。
- `backend/app/controllers/auth_controller.py`の`is_secure_request()`は、HTTPS schemeまたは`ENVIRONMENT not in {"local", "development", "test"}`でSecure cookieを決めている。明示的な`AUTH_COOKIE_SECURE`設定はない。
- `backend/app/controllers/auth_controller.py`の`register`、`login`、`logout`は`dependencies=[Depends(require_csrf)]`で個別にCSRFを指定している。
- `backend/app/controllers/auth_dependencies.py`の`get_client_ip()`は`request.client.host`だけを採用し、`X-Forwarded-For`を信頼できる場合の処理がない。
- `backend/app/usecases/auth_usecase.py`はasync関数内で同期`hash_password()` / `verify_password()`を直接呼ぶ。
- `AuthUsecase.validate_session_csrf()`は`True`、`False`、`None`を返す。controllerとdependencyは`is not False`や`is False`に依存している。
- `AuthUsecase.authenticate_session()`はPhase 1で1 transaction化されたが、認証済みrequestごとに`touch_session()`を呼ぶ。
- `InMemoryLoginRateLimiter`はemail+IP bucketとIP bucketだけを持つ。email単独bucket、失敗時記録、成功時のemail+IP部分reset、抽象interfaceはない。
- `User.password_hash`と初期migrationの`users.password_hash`は`nullable=False`である。
- `SQLModel.metadata.naming_convention`は設定されていない。初期migrationのFK/PK制約にも明示名がない。
- `backend/.env.example`には`AUTH_COOKIE_SECURE=false`や`AUTH_TRUSTED_PROXY_IPS`などPhase 2用の設定がない。

## 方針とその理由

### 採用方針

1. DB schema正典を先に整える。`password_hash nullable`とnaming conventionは将来のOAuth/role migrationの前提なので、認証ロジック変更より先にテストで固定する。
2. Argon2 hash/verifyを専用`PasswordHashExecutor`へ逃がし、`AUTH_PASSWORD_HASH_CONCURRENCY`で同時実行数を制限する。待機中のrequestはexecutorの内部queueで短時間待たせ、同時ログインが数件重なっただけで503にしない。
3. client IP解決をcontrollerから独立した小さなlibraryへ移し、信頼済みproxyから来たrequestだけ`X-Forwarded-For`を採用する。CIDR parse結果はrequestごとに再parseせずcacheする。
4. cookie Secure判定は`AUTH_COOKIE_SECURE`を最優先にし、未設定時は`True`へfail closedする。localは`.env.example`で明示的に`false`へ落とす。
5. `SessionCsrfStatus(StrEnum)`を導入してからCSRF middleware化する。三値の意味を先に型で固定し、middleware実装の条件分岐を読み間違えないようにする。
6. unsafe API requestのCSRF検証はmiddlewareへ移し、route個別の`Depends(require_csrf)`を削除する。将来のOAuth callbackなどを考え、除外pathは設定/定数で明示的に管理できる形にする。
7. rate limiterはinterface経由にし、login/register失敗rateはemail+IP、IP、email単独bucketで評価する。試行開始時には記録せず、認証/登録失敗時だけbucketへ記録する。login成功時は該当email+IP bucketだけをresetし、IP bucketとemail単独bucketは消さない。登録成功は別のregistration bucketへ記録し、成功するaccount creationをIP単位で制限する。
8. session touchは`AUTH_SESSION_TOUCH_INTERVAL_SECONDS`で間引く。既定値は300秒とし、0以下なら従来通り毎回touchできるようにする。
9. registerのemail列挙は、現行の「即時password login + session発行」仕様では完全には隠せない。409 statusを維持したままmessageだけ隠してもセキュリティ価値はないため、Phase 2では設定分岐を追加せず、設計判断と限界をAGENTS.mdへ明記する。
10. 401 error responseの`Cache-Control: no-store`、SQLAlchemy engineの`hide_parameters=True`は認証情報漏えい・キャッシュ防止としてPhase 2に含める。

### 採用理由

- `P1-20`と`P2-6`は後続のOAuth/role schemaに直接効く。ここを後回しにすると、Phase 3以降でmigrationを作るたびにconstraint名やnullable制約の手戻りが発生する。
- Argon2 thread化はevent loop blockingを避ける一方、無制限にthread poolへ流すとArgon2のメモリ使用量でDoSになる。専用executorと同時実行gateを持たせることで、CPU/メモリ消費の上限をテンプレート側で表現できる。
- 信頼proxy処理は「XFFを常に信じる」実装にすると即spoofing脆弱性になる。`request.client.host`が明示allowlist内のときだけ右から信頼hopを剥がす方式に限定する。
- CSRF middleware化は「unsafe methodは既定で守られる」という不変条件をコードで表すための変更である。Phase 1でerror envelopeとDIが整ったため、middlewareからも一貫した403を返せる。
- register email列挙は、メール確認や非同期通知がない現在の仕様では完全解決できない。半端な成功偽装や同じ409でのmessage差し替えはAPI利用者を壊すか、守れていないものを守れているように見せるため採用しない。

## スコープ外

- OAuth/OIDCログイン実装、`auth_identities`テーブル追加。
- password reset、email verification、register UI。
- Role/permission実装。
- Redisなど共有storeのrate limiter実装。
- `auth_sessions.issued_at`、INET型化、expires_at/created_at index、session pruningなど、レビューのPhase 2に含まれていないDB改善。
- frontend query key、401/403 global handler、frontend error message整理。
- ruff/mypy/CI導入。
- sample APIのREST化/CRUD化。
- pre-session CSRF cookieの信頼境界強化、cookie helper統合、`__Host-` prefix導入。Phase 2ではsessionなしdouble-submitを現行通り許可する。

## チェックポイント方針

この作業ではユーザー指示により`git add`と`git commit`を使わない。13個のTaskが1つの巨大diffにならないよう、各Task完了後に復旧用patchとuntracked一覧を`.superpowers/checkpoints/phase2/`へ保存する。

- 各Task開始前に`rtk git status --short`で既存変更を確認する。
- 各Task完了後に次を実行する。`<N>`と`<short-name>`はTask番号と短い説明へ置き換える。

```bash
rtk proxy mkdir -p .superpowers/checkpoints/phase2/task<N>-<short-name>
rtk git diff --binary -- > .superpowers/checkpoints/phase2/task<N>-<short-name>/tracked.patch
rtk git ls-files --others --exclude-standard > .superpowers/checkpoints/phase2/task<N>-<short-name>/untracked-files.txt
```

- `untracked-files.txt`が空でない場合だけ、次を実行する。

```bash
rtk proxy tar -czf .superpowers/checkpoints/phase2/task<N>-<short-name>/untracked-files.tgz -T .superpowers/checkpoints/phase2/task<N>-<short-name>/untracked-files.txt
```

- patch保存後に`rtk git diff --check`を実行し、whitespace errorを早期に潰す。
- 復旧が必要な場合は、人間に確認してから保存済みpatchとuntracked archiveを使う。計画実行者の判断だけで`git reset`、`git checkout --`、`git clean`は実行しない。

## 変更予定ファイル

### 作成するファイル

- `backend/app/models/metadata.py`
  - SQLModel metadata naming conventionを1箇所で定義する。
- `backend/app/models/auth_csrf.py`
  - `SessionCsrfStatus(StrEnum)`を定義する。
- `backend/app/interfaces/libraries/rate_limiter_interface.py`
  - rate limiterの抽象interfaceを定義する。
- `backend/app/libraries/client_ip.py`
  - trusted proxy / X-Forwarded-Forを含むclient IP解決とuser-agent切り詰めを定義する。
- `backend/app/bootstrap/csrf.py`
  - unsafe API requestへCSRF検証を適用するStarlette middlewareを定義する。
- `backend/tests/unit/models/test_metadata.py`
  - naming conventionがmetadataへ設定されることを検証する。
- `backend/tests/unit/models/test_auth_csrf.py`
  - `SessionCsrfStatus`の値を固定する。
- `backend/tests/unit/libraries/test_client_ip.py`
  - trusted proxy / untrusted XFF / invalid IP / IPv6を検証する。
- `backend/tests/unit/bootstrap/test_csrf_middleware.py`
  - unsafe methodのCSRF必須化、safe method除外、明示除外path、error envelopeを検証する。

### 変更するファイル

- `backend/app/models/__init__.py`
  - table model import前にmetadata naming conventionを適用する。
- `backend/app/models/user.py`
  - `password_hash: str | None`、`nullable=True`へ変更する。
- `backend/alembic/versions/20260418_0001_create_auth_tables.py`
  - `password_hash nullable=True`、PK/FK constraint名をnaming conventionに沿って明示する。
- `backend/tests/unit/models/test_auth_models.py`
  - `password_hash` nullableとconstraint namingのmetadata期待を追加する。
- `backend/tests/integration/test_migration_consistency.py`
  - 初期migration更新後もautogenerate差分がないことを維持する。
- `backend/app/libraries/password_hasher.py`
  - `PasswordHashExecutor`とasync hash/verify methodを追加する。
- `backend/tests/unit/libraries/test_password_hasher.py`
  - async wrapperが専用executorへ処理を逃がし、同時実行上限を超えると失敗することを検証する。
- `backend/app/config/auth.py`
  - `AUTH_COOKIE_SECURE`、`AUTH_TRUSTED_PROXY_IPS`、`AUTH_PASSWORD_HASH_CONCURRENCY`、`AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP`、`AUTH_RATE_LIMIT_FAILURES_PER_IP`、`AUTH_RATE_LIMIT_FAILURES_PER_EMAIL`、`AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP`、`AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS`、`AUTH_SESSION_TOUCH_INTERVAL_SECONDS`、`AUTH_CSRF_EXEMPT_PATHS`を追加し、`AuthSettings.ENVIRONMENT`を削除する。
- `backend/.env.example`
  - local用の明示設定とproxy/rate limit/touch/register設定コメントを追加する。
- `backend/app/controllers/auth_controller.py`
  - Secure判定、client IP/user-agent helper import、CSRF route dependency削除へ追随する。
- `backend/app/controllers/auth_dependencies.py`
  - client IP/user-agent helperをlibraryへ委譲し、`require_csrf`を削除する。CSRF検証のcoverageはmiddleware testへ移す。
- `backend/app/bootstrap/create_app.py`
  - CSRF middlewareをroute登録前後の適切な位置に追加する。
- `backend/app/bootstrap/error_handlers.py`
  - middlewareから使える公開`json_error_response()`を追加し、401へ`Cache-Control: no-store`を付ける。
- `backend/app/interfaces/usecases/auth_usecase_interface.py`
  - `validate_session_csrf()`戻り値を`SessionCsrfStatus`へ変更する。
- `backend/app/usecases/auth_usecase.py`
  - async password hasher、CSRF status enum、失敗時記録rate limit、success時email+IP reset、touch interval、nullable password_hash、`__init__ -> None`修正を反映する。
- `backend/app/interfaces/services/auth_repository_interface.py`
  - `create_user()`の`password_hash`型を`str | None`へ変更する。
- `backend/app/services/auth_repository.py`
  - `create_user()`の`password_hash`型を`str | None`へ変更する。
- `backend/app/libraries/auth_rate_limiter.py`
  - email単独bucket、registration bucket、`is_allowed()`、`record_failure()`、`record_success()`、`is_registration_allowed()`、`record_registration()`、抽象interfaceに合わせたmethodを追加する。
- `backend/app/bootstrap/modules.py`
  - `LoginRateLimiterInterface`を`InMemoryLoginRateLimiter`へbindし、新設定を渡す。`PasswordHashExecutor`もsingleton providerで生成する。
- `backend/tests/integration/conftest.py`
  - integration testでは`AUTH_COOKIE_SECURE=false`を明示し、rate limiter resetはinterface経由で行う。
- `backend/app/libraries/database_engine.py`
  - `create_async_engine(..., hide_parameters=True)`を設定する。
- `backend/AGENTS.md`
  - Phase 2で確立したsecurity default、trusted proxy、CSRF middleware、rate limit、register enumeration方針を追記する。
- `documents/plans/20260802-phase2-auth-security.md`
  - 実装中に進捗と検証結果を更新する。

### 変更しないファイル

- `frontend/*`
- `docker-compose.yaml`
- `backend/alembic.ini`
- `backend/app/models/auth_audit_log.py`
- `backend/app/models/auth_session.py`
- `backend/app/models/auth_schemas.py`。ただしregister duplicateのresponse model変更が必要になった場合は、実装前に計画を更新してユーザーへ確認する。

## 具体的なタスク

### Task 1: baselineとPhase 2境界を固定する

**Files:**
- Inspect: `documents/reviews/20260801-review.md`
- Inspect: `documents/plans/20260801-phase0-review-fixes.md`
- Inspect: `documents/plans/20260801-phase1-backend-foundation.md`
- Inspect: `backend/AGENTS.md`
- Inspect: `backend/app/config/auth.py`
- Inspect: `backend/app/controllers/auth_controller.py`
- Inspect: `backend/app/controllers/auth_dependencies.py`
- Inspect: `backend/app/usecases/auth_usecase.py`
- Inspect: `backend/app/libraries/auth_rate_limiter.py`
- Inspect: `backend/alembic/versions/20260418_0001_create_auth_tables.py`

- [x] **Step 1.1: working treeと禁止事項を確認する**

```bash
rtk git status --short
rtk git branch --show-current
rtk git rev-parse --short HEAD
```

Expected:

- 既存の未コミット変更があればPhase 2と競合しないか読む。
- 既存変更をreset、checkout、cleanしない。
- `git add`、`git commit`、`git push`を実行しない。

- [x] **Step 1.2: Phase 2対象IDをレビュー本文で再確認する**

```bash
rtk rg -n -C 4 "P1-10|P1-11|P1-12|P1-14|P1-20|P2-6|P2-13|P2-14|P2-15|P2-16|P2-19|Phase 2" documents/reviews/20260801-review.md
```

Expected:

- Phase 2の並びが`P1-10`、`P1-11`、`P1-12`、`P1-14`、`P1-20`、`P2-13`から`P2-16`、`P2-19`であることを確認する。
- `P1-20`は`P2-6`と同時に扱う必要があることを確認する。

- [x] **Step 1.3: Phase 1から渡された未対応事項を確認する**

```bash
rtk rg -n "Phase 2|P1-10|P1-11|P1-12|P1-14|P1-20|P2-13|P2-14|P2-15|P2-16|P2-19|P2-24|M-1|M-2|M-3|M-4|M-5|M-7" documents/plans/20260801-phase1-backend-foundation.md
```

Expected:

- rate limiter interface化、401 no-store、database URL parameter秘匿など、Phase 2で拾う項目を確認する。
- pre-session CSRF cookieの信頼境界はPhase 2で現行維持とし、未対応事項へ送ることを確認する。
- 405 error code名や`api_error`命名など、Phase 2の認証セキュリティに直結しない項目は未対応事項へ残す。

- [x] **Step 1.4: backend baselineテストを実行する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest -q
```

Expected:

- Phase 2着手前のbackend full pytestが成功する。
- PostgreSQL integration testsのskipが0件である。
- PostgreSQLが起動していない場合は`rtk docker compose up -d postgres`を実行してから再実行する。
- baselineが失敗した場合はPhase 2実装に入らず、失敗内容を本計画の「実行結果」へ記録して原因を切り分ける。

### Task 2: naming conventionと`password_hash` nullable化を先に固定する

**Review IDs:** `P1-20`, `P2-6`

**Files:**
- Create: `backend/app/models/metadata.py`
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/models/user.py`
- Modify: `backend/app/interfaces/services/auth_repository_interface.py`
- Modify: `backend/app/services/auth_repository.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/alembic/versions/20260418_0001_create_auth_tables.py`
- Create: `backend/tests/unit/models/test_metadata.py`
- Modify: `backend/tests/unit/models/test_auth_models.py`
- Modify: `backend/tests/unit/services/test_auth_repository.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/integration/test_migration_consistency.py`

- [x] **Step 2.1: DB schema変更方針についてユーザー確認を取る**

Run: なし。

Expected:

- 「初期migrationを書き換え、test DBで検証する。既存local DBの破壊的再作成はしない」方針についてユーザーの承認を得る。
- 承認がない場合はTask 2以降のDB schema変更へ進まない。

- [x] **Step 2.2: naming conventionのRED testを書く**

`backend/tests/unit/models/test_metadata.py`を作成し、次を検証する。

- `SQLModel.metadata.naming_convention`に`ix`、`uq`、`ck`、`fk`、`pk`が存在する。
- `AuthSession.__table__.foreign_key_constraints`のFK名が`fk_auth_sessions_user_id_users`である。
- `AuthAuditLog`の`user_id` / `session_id` FK名がそれぞれ`fk_auth_audit_logs_user_id_users`、`fk_auth_audit_logs_session_id_auth_sessions`である。

Expected:

- 現状はnaming convention未設定または既存constraint名なしで失敗する。

- [x] **Step 2.3: `password_hash nullable`のRED testを書く**

`backend/tests/unit/models/test_auth_models.py`へ次を追加する。

- `User.__table__.c.password_hash.nullable is True`
- `User.model_fields["password_hash"].annotation`が`str | None`相当である。
- `AuthRepositoryInterface.create_user()`と`AuthRepository.create_user()`の`password_hash`引数型が`str | None`相当である。

Expected:

- 現状は`nullable=False`と`str`で失敗する。

- [x] **Step 2.4: `password_hash=None`のpassword login拒否RED testを書く**

`backend/tests/unit/usecases/test_auth_usecase.py`へ、`user.password_hash is None`のユーザーに対して`login()`が`InvalidCredentialsError`を投げるtestを追加する。

Expected:

- 現状は`verify_password(password, None)`経由で想定外例外になり失敗する。
- このtestをTask 2に置くことで、nullable schemaだけ入ってloginが500になる中間状態を防ぐ。

- [x] **Step 2.5: metadata naming conventionを実装する**

`backend/app/models/metadata.py`に次の定義を置く。

```python
from sqlmodel import SQLModel

NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def configure_metadata() -> None:
    SQLModel.metadata.naming_convention = NAMING_CONVENTION
```

`backend/app/models/__init__.py`ではtable model importより前に`configure_metadata()`を呼ぶ。

- [x] **Step 2.6: `User.password_hash`とrepository signatureをnullableへ変更する**

`backend/app/models/user.py`、`backend/app/interfaces/services/auth_repository_interface.py`、`backend/app/services/auth_repository.py`を次の方針で変更する。

- 型を`str | None`へ変更する。
- `Column(String(length=255), nullable=True)`へ変更する。
- `create_user(email, password_hash)`の`password_hash`引数も`str | None`へ変更する。

- [x] **Step 2.7: `password_hash=None`のpassword login拒否を実装する**

`backend/app/usecases/auth_usecase.py`の`login()`では次の順序を守る。

- `user is None`の場合は従来通り`DUMMY_PASSWORD_HASH`を検証する。
- `user is not None and user.password_hash is None`の場合も`DUMMY_PASSWORD_HASH`を検証し、結果に関係なく`InvalidCredentialsError`へ進む。
- `user.password_hash`が文字列の場合だけ実hashを検証する。
- `user.is_active`判定は従来通りpassword verify後に行い、timing等化を崩さない。

- [x] **Step 2.8: 初期migrationをnaming conventionとnullableへ合わせる**

`backend/alembic/versions/20260418_0001_create_auth_tables.py`を次の方針で変更する。

- `users.password_hash`を`nullable=True`にする。
- `sa.PrimaryKeyConstraint("id", name="pk_users")`
- `sa.PrimaryKeyConstraint("id", name="pk_auth_sessions")`
- `sa.PrimaryKeyConstraint("id", name="pk_auth_audit_logs")`
- `sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_sessions_user_id_users")`
- `sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_auth_audit_logs_user_id_users")`
- `sa.ForeignKeyConstraint(["session_id"], ["auth_sessions.id"], name="fk_auth_audit_logs_session_id_auth_sessions")`
- 既存index名は維持する。

- [x] **Step 2.9: schema targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/models/test_metadata.py tests/unit/models/test_auth_models.py tests/unit/services/test_auth_repository.py tests/unit/usecases/test_auth_usecase.py -q
```

Expected:

- metadata / model testsがすべて成功する。
- `password_hash=None`のpassword login拒否testが成功する。

- [x] **Step 2.10: test DBを明示的に作り直してAlembic整合を確認する**

既存の`app_test`に古いconstraint名が残っている場合、`alembic upgrade head`と`db-check`だけではPK/FK名差分を検出できない。Phase 2では初期migrationの正典を検証するため、test DBだけを明示的に作り直す。

```bash
cd backend
rtk psql postgresql://app:app@localhost:5432/postgres -c "DROP DATABASE IF EXISTS app_test;"
rtk psql postgresql://app:app@localhost:5432/postgres -c "CREATE DATABASE app_test;"
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration/test_migration_consistency.py -q
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
```

Expected:

- migration consistency testが成功する。
- `db-check`が`No new upgrade operations detected.`で成功する。
- 作り直すのは`app_test`だけであり、local開発DBの`app`は触らない。

### Task 3: Argon2 hash/verifyをthread化する

**Review ID:** `P1-10`

**Files:**
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/libraries/password_hasher.py`
- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/tests/unit/libraries/test_password_hasher.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`

- [x] **Step 3.1: password hash concurrency settingsのRED testを書く**

`backend/tests/unit/config/test_auth_settings.py`へ次を追加する。

- `AUTH_PASSWORD_HASH_CONCURRENCY`の既定値は4である。
- envから1以上の整数を指定できる。
- 0以下を指定するとsettings validationで失敗する。
- 既定値4は、現行Argon2設定のm=64MiBを前提に、1 processあたり約256MiBまでpassword hash用メモリを使う上限として採用する。小さいmemory limitの派生プロジェクトでは`.env`で下げる。

- [x] **Step 3.2: async password hasher executorのRED testを書く**

`backend/tests/unit/libraries/test_password_hasher.py`へ次を追加する。

- `PasswordHashExecutor(max_workers=1)`が専用`ThreadPoolExecutor`で同期`hash_password()` / `verify_password()`を呼ぶ。
- `max_workers=1`で2件同時に呼んだ場合、2件目は即時503相当の例外にならず、executor内部queueで待って完了する。
- async round-tripで正しいpasswordが`True`、誤ったpasswordが`False`になる。
- `shutdown()`がexecutorを閉じる。

Expected:

- 現状は`PasswordHashExecutor`未定義で失敗する。

- [x] **Step 3.3: usecaseがexecutorをawaitするRED testを書く**

`backend/tests/unit/usecases/test_auth_usecase.py`で、`register()`と`login()`が同期`hash_password` / `verify_password`ではなく注入された`PasswordHashExecutor`をawaitすることをstubで検証する。

Expected:

- 現状は同期関数を直接呼ぶため失敗する。

- [x] **Step 3.4: `PasswordHashExecutor`を実装する**

`backend/app/libraries/password_hasher.py`へ次の構成を追加する。

```python
import asyncio
from concurrent.futures import ThreadPoolExecutor


class PasswordHashExecutor:

    def __init__(self, max_workers: int) -> None:
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix="password-hash",
        )

    async def hash(self, raw_password: str) -> str:
        return await self._run(hash_password, raw_password)

    async def verify(self, raw_password: str, hashed_password: str) -> bool:
        return await self._run(verify_password, raw_password, hashed_password)

    async def _run(self, func, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._executor, func, *args)

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
```

同期版`hash_password()` / `verify_password()`は既存testと低レベル用途のため残す。

- [x] **Step 3.5: DIとlifespanをexecutorへ追随させる**

`backend/app/bootstrap/modules.py`では`PasswordHashExecutor`をsingleton providerで作成し、`AUTH_PASSWORD_HASH_CONCURRENCY`を渡す。`create_app()`のlifespan shutdownでは、`AsyncEngine.dispose()`に加えて`PasswordHashExecutor.shutdown()`を呼ぶ。dispose失敗とshutdown失敗は個別にlogし、起動中例外の扱いをPhase 1のlifespan方針に合わせる。

- [x] **Step 3.6: `AuthUsecase`をexecutorへ差し替える**

`backend/app/usecases/auth_usecase.py`を次の方針で変更する。

- `__init__`で`PasswordHashExecutor`を受け取る。
- `__init__`の戻り値注釈を誤った`-> IssuedAuthSession`から`-> None`へ直す。
- `register()`内の`hash_password(password)`を`await self._password_hash_executor.hash(password)`へ変更する。
- `login()`内の`verify_password(password, password_hash)`を`await self._password_hash_executor.verify(password, password_hash)`へ変更する。
- `user.password_hash is None`の場合は、OAuth-only userとしてpassword loginを常に失敗させる。ただしユーザー不在時と同じくdummy hash verifyは実行し、timing差を広げない。

- [x] **Step 3.7: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/config/test_auth_settings.py tests/unit/libraries/test_password_hasher.py tests/unit/usecases/test_auth_usecase.py tests/unit/bootstrap/test_create_app.py -q
```

Expected:

- password hasherとauth usecase unit testsが成功する。
- dummy hash検証の既存testが維持される。

### Task 4: trusted proxy対応のclient IP解決を導入する

**Review ID:** `P1-11`

**Files:**
- Create: `backend/app/libraries/client_ip.py`
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Create: `backend/tests/unit/libraries/test_client_ip.py`
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/.env.example`

- [x] **Step 4.1: trusted proxy settingsのRED testを書く**

`backend/tests/unit/config/test_auth_settings.py`へ次を追加する。

- `AUTH_TRUSTED_PROXY_IPS`の既定値が空文字である。
- envで`"127.0.0.1,10.0.0.0/8"`を指定できる。

- [x] **Step 4.2: client IP解決のRED testを書く**

`backend/tests/unit/libraries/test_client_ip.py`を作成し、次を検証する。

- trusted proxy未設定では`X-Forwarded-For`を無視して`request.client.host`を返す。
- `request.client.host`が`AUTH_TRUSTED_PROXY_IPS`に含まれる場合だけ`X-Forwarded-For`を採用する。
- XFF chainは`client, proxy1, proxy2`の順として、右からtrusted hopを剥がし、最初のuntrusted IPを返す。
- XFFにinvalid IPが含まれる場合はspoofing防止として`request.client.host`へfallbackする。
- IPv6 addressとCIDRが動作する。
- `request.client`がない場合は`None`を返す。
- `parse_trusted_proxy_networks()`は同じ設定文字列を2回parseしても同じtuple objectを返すか、少なくとも`lru_cache`のhitが増える。

- [x] **Step 4.3: `AuthSettings`にtrusted proxy設定を追加する**

`backend/app/config/auth.py`へ次を追加する。

```python
AUTH_TRUSTED_PROXY_IPS: str = ""
```

`.env.example`へ、localでは空のままでよいこと、nginx/ALB/Ingress配下では信頼できるproxyのIP/CIDRだけを指定することをコメントで書く。

- [x] **Step 4.4: `client_ip.py`を実装する**

実装方針:

- `resolve_client_ip(request: Request, trusted_proxy_ips: str) -> str | None`
- `get_user_agent(request: Request) -> str | None`
- `trusted_proxy_ips`はcomma-separatedのIP/CIDRとして`ipaddress.ip_network(..., strict=False)`でparseする。
- parse関数は`functools.lru_cache`でcacheし、requestごとにCIDR文字列をparseしない。
- direct peerがtrusted networkに含まれない場合はXFFを無視する。
- XFF parseに失敗した場合はdirect peerへfallbackする。
- direct peer自体がinvalidなら`None`を返す。

- [x] **Step 4.5: controller/dependencyを新helperへ差し替える**

`auth_dependencies.py`の`get_client_ip()` / `get_user_agent()`は、後方互換のため残す場合でも`client_ip.py`へ委譲する。

`auth_controller.py`では、request処理時に`auth_settings.AUTH_TRUSTED_PROXY_IPS`を渡してclient IPを解決する。register/login/logout/get_csrf/require_current_sessionの全経路で同じhelperを使う。

- [x] **Step 4.6: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/config/test_auth_settings.py tests/unit/libraries/test_client_ip.py tests/unit/controllers/test_auth_dependencies.py tests/integration/test_auth_controller.py -q
```

Expected:

- client IP unit testsが成功する。
- integration testsで監査ログIPの期待が壊れていない。

### Task 5: Secure cookieの既定値を安全側へ反転する

**Review ID:** `P1-12`

**Files:**
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/tests/unit/bootstrap/test_container.py`
- Modify: `backend/tests/unit/bootstrap/test_dependencies.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_helpers.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/.env.example`
- Modify: `backend/AGENTS.md`

- [x] **Step 5.1: Secure cookie設定のRED testを書く**

`backend/tests/unit/controllers/test_auth_controller_helpers.py`へ次を追加/変更する。

- `AuthSettings()`の`AUTH_COOKIE_SECURE is None`ではHTTP local requestでもSecure cookie判定が`True`になる。
- `AuthSettings(AUTH_COOKIE_SECURE=False)`ではHTTP local requestでSecure cookie判定が`False`になる。
- `AuthSettings(AUTH_COOKIE_SECURE=True)`ではHTTP/HTTPSに関係なく`True`になる。
- `X-Forwarded-Proto`だけではSecure判定を変更しない。

既存の`test_is_secure_request_accepts_https_in_local_environment`は、新方針に合わせて「明示falseがない限りSecure」を期待する形へ更新する。

`backend/tests/integration/test_auth_controller.py`のSecure cookie期待は、fixtureが`AUTH_COOKIE_SECURE=false`を明示する前提の期待へ更新する。

- [x] **Step 5.2: `AuthSettings`に`AUTH_COOKIE_SECURE`を追加する**

`backend/app/config/auth.py`へ次を追加し、`AuthSettings.ENVIRONMENT`は削除する。

```python
AUTH_COOKIE_SECURE: bool | None = None
```

- `Config.ENVIRONMENT`はdocs/logging用に残る。
- auth cookie secure判定では`ENVIRONMENT`を使わない。
- `backend/AGENTS.md`の「Phase 2でAuthSettings側も安全側へ反転するまで」という注記は、`AUTH_COOKIE_SECURE`へ置き換える。
- `backend/tests/unit/bootstrap/test_container.py`、`backend/tests/unit/bootstrap/test_dependencies.py`、`backend/tests/unit/controllers/test_auth_controller_dependency.py`、`backend/tests/unit/controllers/test_auth_dependencies.py`に残る`AuthSettings(ENVIRONMENT=...)`は、`extra="ignore"`により黙って無視されるfalse greenになるため、`AUTH_COOKIE_SECURE`または他の実在fieldを使うtestへ更新する。

- [x] **Step 5.3: Secure判定helperを設定優先へ変更する**

`auth_controller.py`の`is_secure_request()`は次の順序にする。

1. `auth_settings.AUTH_COOKIE_SECURE is not None`ならその値を返す。
2. 未設定なら`True`を返す。

`request.url.scheme`や`ENVIRONMENT`はSecure cookie既定判定には使わない。TLS終端がproxyにある構成でschemeに依存すると事故るためである。

- [x] **Step 5.4: integration fixtureでlocal opt-outを明示する**

`backend/tests/integration/conftest.py`の`client(monkeypatch)` fixtureへ次を追加する。

```python
monkeypatch.setenv("AUTH_COOKIE_SECURE", "false")
```

理由:

- Secure属性付きcookieは`http://testserver`へ送り返されない。
- integration testsはHTTP TestClientでcookie round-tripを検証するため、local opt-outをfixtureで明示する。

- [x] **Step 5.5: `.env.example`でlocal opt-outを明示する**

`backend/.env.example`へ次を追加する。

```env
# Local HTTP development must opt out explicitly. Production should omit this or set true.
AUTH_COOKIE_SECURE=false
```

`backend/AGENTS.md`へ、本番で`AUTH_COOKIE_SECURE=false`を使わないこと、local HTTPだけ明示opt-outすることを追記する。

- [x] **Step 5.6: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/controllers/test_auth_controller_helpers.py tests/integration/test_auth_controller.py -q
```

Expected:

- 明示local設定があるintegration fixtureでは既存local cookie期待が通る。
- 未設定時はSecureが付くことをunit testで保証する。
- `rtk rg -nU --multiline "AuthSettings\\((\\s|\\n)*ENVIRONMENT" backend/tests`が0件である。

### Task 6: rate limiterをinterface化し、失敗時記録へ変更する

**Review IDs:** `P2-13`, `P2-19`, adjacent `P2-24`

**Files:**
- Create: `backend/app/interfaces/libraries/rate_limiter_interface.py`
- Modify: `backend/app/libraries/auth_rate_limiter.py`
- Modify: `backend/app/bootstrap/modules.py`
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/tests/unit/libraries/test_auth_rate_limiter.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/tests/integration/conftest.py`
- Modify: `backend/.env.example`
- Modify: `backend/AGENTS.md`

- [x] **Step 6.1: rate limiter behaviorのRED testを書く**

`backend/tests/unit/libraries/test_auth_rate_limiter.py`へ次を追加する。

- `is_allowed(ip, email)`はbucketへappendせず、現在の失敗数だけで判定する。
- `record_failure(ip, email)`後、同じemailに対してIPを変えても、`max_failures_per_email`を超えたらblockされる。
- `record_failure(ip, email)`後、同じIP+emailは`max_failures_per_email_ip`でblockされる。
- `record_failure(ip, email)`後、同じIPでemailを変えても、`max_failures_per_ip`を超えたらblockされる。
- `record_success(ip, email)`は該当email+IP bucketだけをclearし、IP bucketとemail単独bucketは消さない。
- `record_success(ip, email)`は別emailや別IPのbucketを消さない。
- `is_registration_allowed(ip)`はregistration bucketだけで判定し、bucketへappendしない。
- `record_registration(ip)`は成功した登録作成をIP bucketへ記録し、`max_registrations_per_ip`を超えると以後のregisterをblockできる。
- registration bucketは失敗rate用の`window_seconds`ではなく`registration_window_seconds`でtrimされる。
- `reset()`はtest fixture用として全bucketをclearする。

- [x] **Step 6.2: rate limit settingsのRED testを書く**

`backend/tests/unit/config/test_auth_settings.py`へ次を追加する。

- `AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP`の既定値は5である。
- `AUTH_RATE_LIMIT_FAILURES_PER_IP`の既定値は20である。
- `AUTH_RATE_LIMIT_FAILURES_PER_EMAIL`の既定値は20である。
- `AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP`の既定値は10である。
- `AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS`の既定値は3600である。
- 旧`AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP` / `AUTH_RATE_LIMIT_ATTEMPTS_PER_IP`をenvに設定しても、`AuthSettings.model_fields_set`に入らず、実在fieldへ影響しない。

- [x] **Step 6.3: usecase success resetのRED testを書く**

`backend/tests/unit/usecases/test_auth_usecase.py`へ次を追加する。

- login/registerの開始時は`is_allowed(ip, email)`で判定するが、この時点ではbucketへ記録しない。
- login失敗時は`record_failure(ip, normalized_email)`が呼ばれる。
- login成功時は`record_success(ip, normalized_email)`が呼ばれる。
- registerのduplicate emailやその他register失敗時は`record_failure(ip, normalized_email)`が呼ばれる。
- register開始時は`is_registration_allowed(ip)`も確認する。
- register成功時は失敗bucketを増やさず、`record_registration(ip)`で作成rateだけを記録する。

- [x] **Step 6.4: interfaceを定義する**

`backend/app/interfaces/libraries/rate_limiter_interface.py`に次を定義する。

```python
from abc import ABCMeta, abstractmethod


class LoginRateLimiterInterface(metaclass=ABCMeta):

    @abstractmethod
    def is_allowed(self, ip_address: str, normalized_email: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def record_failure(self, ip_address: str, normalized_email: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def record_success(self, ip_address: str, normalized_email: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def is_registration_allowed(self, ip_address: str) -> bool:
        raise NotImplementedError

    @abstractmethod
    def record_registration(self, ip_address: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def reset(self) -> None:
        raise NotImplementedError
```

- [x] **Step 6.5: `InMemoryLoginRateLimiter`を拡張する**

`auth_rate_limiter.py`を次の方針で変更する。

- `LoginRateLimiterInterface`を継承する。
- constructor引数は`window_seconds`、`registration_window_seconds`、`max_failures_per_email_ip`、`max_failures_per_ip`、`max_failures_per_email`、`max_registrations_per_ip`へ揃える。
- `_email_buckets: dict[str, deque[float]]`を追加する。
- `_registration_ip_buckets: dict[str, deque[float]]`を追加する。
- `is_allowed()`はemail+IP、IP、emailの3 bucketをtrim後に評価し、どれかが上限以上なら`False`を返す。どのbucketにもappendしない。
- `record_failure()`は3 bucketをtrimしてから`now`をappendする。
- `record_success()`は該当email+IP keyのbucketだけを削除する。IP bucketとemail単独bucketは削除しない。
- `is_registration_allowed()`はregistration bucketをtrim後に評価し、appendしない。
- `record_registration()`はregistration bucketをtrimしてから`now`をappendする。

- [x] **Step 6.6: DIとsettingsを更新する**

`AuthSettings`へ次を追加する。

```python
AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP: int = 5
AUTH_RATE_LIMIT_FAILURES_PER_IP: int = 20
AUTH_RATE_LIMIT_FAILURES_PER_EMAIL: int = 20
AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP: int = 10
AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS: int = 3600
```

`backend/app/bootstrap/modules.py`では`LoginRateLimiterInterface`を`InMemoryLoginRateLimiter`へbindし、providerはinterface型を返す。`AuthUsecase.__init__`は具象`InMemoryLoginRateLimiter`ではなく`LoginRateLimiterInterface`を受け取る。

`.env.example`と`backend/AGENTS.md`へ、email単独bucketは分散IPから同一アカウントへ向かうpassword spray防止であり、失敗時だけ記録してlockout DoSを抑えることを書く。失敗系の3設定はすべて`FAILURES`で命名を揃え、旧`AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP` / `AUTH_RATE_LIMIT_ATTEMPTS_PER_IP`は削除する。`AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP=10`と`AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS=3600`は、成功するアカウント作成スパムをIP単位で「10件/時」に制限する別bucketとして説明する。

`backend/tests/integration/conftest.py`は次のようにinterface経由でresetする。

```python
from app.interfaces.libraries.rate_limiter_interface import LoginRateLimiterInterface

app.state.injector.get(LoginRateLimiterInterface).reset()
```

- [x] **Step 6.7: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/config/test_auth_settings.py tests/unit/libraries/test_auth_rate_limiter.py tests/unit/bootstrap/test_container.py tests/unit/usecases/test_auth_usecase.py tests/integration/test_auth_controller.py -q
```

Expected:

- rate limiter unit testsが成功する。
- containerがinterfaceを解決できる。
- login/register rate limit integration testsが新しい3 bucketでも通る。

### Task 7: `SessionCsrfStatus`を導入し、三値boolを廃止する

**Review ID:** `P2-14`

**Files:**
- Create: `backend/app/models/auth_csrf.py`
- Modify: `backend/app/interfaces/usecases/auth_usecase_interface.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Create: `backend/tests/unit/models/test_auth_csrf.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/integration/test_auth_controller.py`

- [x] **Step 7.1: enumのRED testを書く**

`backend/tests/unit/models/test_auth_csrf.py`を作成し、次を検証する。

```python
assert SessionCsrfStatus.VALID == "valid"
assert SessionCsrfStatus.MISMATCH == "mismatch"
assert SessionCsrfStatus.NO_SESSION == "no_session"
```

- [x] **Step 7.2: usecase戻り値のRED testを更新する**

既存の`validate_session_csrf()`関連testを次の期待へ変更する。

- sessionなしまたは失効済みsessionは`SessionCsrfStatus.NO_SESSION`
- hash一致は`SessionCsrfStatus.VALID`
- hash不一致は`SessionCsrfStatus.MISMATCH`

- [x] **Step 7.3: enumを実装する**

`backend/app/models/auth_csrf.py`に次を追加する。

```python
from enum import StrEnum


class SessionCsrfStatus(StrEnum):
    VALID = "valid"
    MISMATCH = "mismatch"
    NO_SESSION = "no_session"
```

- [x] **Step 7.4: interface/usecase/controller/dependencyをenumへ移行する**

変更方針:

- `AuthUsecaseInterface.validate_session_csrf()`戻り値を`SessionCsrfStatus`へ変更する。
- `AuthUsecase.validate_session_csrf()`は`None`/`True`/`False`を返さない。
- `get_csrf()`は`status in {SessionCsrfStatus.VALID, SessionCsrfStatus.NO_SESSION}`なら既存cookieを再利用し、`MISMATCH`なら再発行する。
- CSRF検証側は`MISMATCH`だけ403にする。`NO_SESSION`はpre-session double-submitとして許可する。

- [x] **Step 7.5: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/models/test_auth_csrf.py tests/unit/usecases/test_auth_usecase.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_controller_dependency.py tests/integration/test_auth_controller.py -q
```

Expected:

- `bool | None`を期待するtestが残っていない。
- `rtk rg -n "is False|is not False|bool \\| None" backend/app backend/tests`で、CSRF statusに対する同一性bool比較や`bool | None`戻り値型が残っていない。
- `validate_session_csrf`というメソッド名自体は残る。

### Task 8: CSRF検証をmiddleware化し、route単位のオプトインを廃止する

**Review ID:** `P1-14`

**Files:**
- Create: `backend/app/bootstrap/csrf.py`
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/bootstrap/create_app.py`
- Modify: `backend/app/bootstrap/error_handlers.py`
- Modify: `backend/app/controllers/auth_controller.py`
- Modify: `backend/app/controllers/auth_dependencies.py`
- Modify: `backend/tests/unit/bootstrap/test_error_handlers.py`
- Create: `backend/tests/unit/bootstrap/test_csrf_middleware.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/tests/unit/controllers/test_auth_dependencies.py`
- Modify: `backend/tests/unit/controllers/test_auth_controller_dependency.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/AGENTS.md`

- [x] **Step 8.1: middleware behaviorのRED testを書く**

`backend/tests/unit/bootstrap/test_csrf_middleware.py`を作成し、最小FastAPI appで次を検証する。

- `POST /api/protected`はCSRF cookie/headerがなければ403 error envelopeを返す。
- `POST /api/protected`はcookie/header不一致なら403を返す。
- `POST /api/protected`はcookie/header一致かつsession cookieなしなら通る。
- `POST /api/protected`はsession cookieありで`SessionCsrfStatus.MISMATCH`なら403を返す。
- `POST /api/protected`はsession cookieありで`VALID`なら通る。
- `GET /api/protected`はCSRFなしで通る。
- `/api`以外のpathはmiddleware対象外。
- 明示除外pathはunsafe methodでもmiddleware対象外になる。
- 403 responseは`{"error":{"code":"CSRF_VALIDATION_FAILED",...}}`形式である。
- `validate_session_csrf()`が例外を投げた場合は、素の500ではなく500 error envelopeを返す。
- 存在しない`POST /api/unknown`もrouting前のmiddlewareで403になる。これは「unsafe `/api` requestはCSRFが先」という意図的なAPI契約変更として固定する。

- [x] **Step 8.2: CSRF exempt settingのRED testを書く**

`backend/tests/unit/config/test_auth_settings.py`へ次を追加する。

- `AUTH_CSRF_EXEMPT_PATHS`の既定値は空文字である。
- envで`"/api/auth/oauth/callback,/api/webhooks/example"`のようなcomma-separated pathを指定できる。

- [x] **Step 8.3: 既存auth routesから個別dependency削除のRED testを書く**

`backend/tests/unit/controllers/test_auth_controller_dependency.py`で、`router.routes`の`/register`、`/login`、`/logout`に`Depends(require_csrf)`相当のroute dependencyが残っていないことを検証する。

- [x] **Step 8.4: middlewareから使えるerror response helperを公開する**

`backend/app/bootstrap/error_handlers.py`の`_json_error_response()`をpublicな`json_error_response()`へ変更するか、wrapperを追加する。既存handlerは同じhelperを使う。

401の場合はheadersに`Cache-Control: no-store`を必ず付ける。既存headersがある場合は上書きせず、不足時だけ追加する。

`backend/tests/unit/bootstrap/test_error_handlers.py`へ次を追加する。

- `api_error(401, ...)`をhandlerに通すと`Cache-Control: no-store`が付く。
- 既に`Cache-Control` headerが明示されている場合は意図せず消さない。

`backend/tests/integration/test_auth_controller.py`の`GET /api/auth/me`未認証401 testにも`Cache-Control: no-store` assertionを追加する。

- [x] **Step 8.5: `AuthSettings`に`AUTH_CSRF_EXEMPT_PATHS`を追加する**

`backend/app/config/auth.py`へ次を追加する。

```python
AUTH_CSRF_EXEMPT_PATHS: str = ""
```

middlewareではcomma-separated pathをtrimし、空要素を除外する。pathは完全一致で扱い、prefix matchingはしない。

- [x] **Step 8.6: 純ASGI `CSRFMiddleware`を実装する**

`backend/app/bootstrap/csrf.py`の実装方針:

- unsafe methodsは`{"POST", "PUT", "PATCH", "DELETE"}`。
- 対象pathは`/api`と`/api/`配下。
- 除外pathは`AUTH_CSRF_EXEMPT_PATHS`から読み取る。Phase 2時点の`.env.example`では空文字にし、除外pathがないことを明示する。
- `BaseHTTPMiddleware`は使わない。UoWがContextVarに依存しているため、子taskを生成しない純ASGI middlewareとして実装する。
- cookie/header double-submit比較はUTF-8 bytesで`secrets.compare_digest()`する。
- session cookieがある場合だけ`AuthUsecaseInterface.validate_session_csrf()`を呼ぶ。
- client IP/user-agentはTask 4のhelperで解決する。
- 失敗時はerror envelopeの403を返す。
- middleware内部の予期しない例外はlogし、`json_error_response(500, "INTERNAL_SERVER_ERROR", "Internal server error")`をASGI responseとして返す。

実装骨子:

```python
class CSRFMiddleware:

    def __init__(self, app):
        self._app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or not self._requires_csrf(scope):
            await self._app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        try:
            error_response = await self._validate(request)
        except Exception:
            logger.exception("CSRF middleware failed")
            response = json_error_response(
                500,
                "INTERNAL_SERVER_ERROR",
                "Internal server error",
            )
            await response(scope, receive, send)
            return
        if error_response is not None:
            await error_response(scope, receive, send)
            return
        await self._app(scope, receive, send)
```

- [x] **Step 8.7: `create_app()`へmiddlewareを登録する**

`backend/app/bootstrap/create_app.py`で、app作成後かつroute setup前にCSRF middlewareを追加する。middlewareが`app.state.injector`へアクセスできる必要があるため、実装時にFastAPI middlewareの実行順とstate参照をunit testで固定する。

- [x] **Step 8.8: route個別dependencyを削除し、旧dependency testを整理する**

`auth_controller.py`から`dependencies=[Depends(require_csrf)]`を削除する。`require_csrf`関数は削除し、`backend/tests/unit/controllers/test_auth_dependencies.py`から`require_csrf`専用testを削除する。同等のCSRF coverageは`backend/tests/unit/bootstrap/test_csrf_middleware.py`へ移す。`require_current_session`とclient IP/user-agent helperのtestは残す。

- [x] **Step 8.9: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/bootstrap/test_csrf_middleware.py tests/unit/config/test_auth_settings.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_controller_dependency.py tests/integration/test_auth_controller.py -q
```

Expected:

- auth controllerのregister/login/logoutはCSRFなしで直接handlerへ到達しない。
- 既存integrationのCSRF必須テストがmiddleware経由で成功する。

### Task 9: session touchを間引く

**Review ID:** `P2-15`

**Files:**
- Modify: `backend/app/config/auth.py`
- Modify: `backend/app/usecases/auth_usecase.py`
- Modify: `backend/tests/unit/config/test_auth_settings.py`
- Modify: `backend/tests/unit/usecases/test_auth_usecase.py`
- Modify: `backend/tests/integration/test_auth_controller.py`
- Modify: `backend/.env.example`
- Modify: `backend/AGENTS.md`

- [x] **Step 9.1: touch interval settingのRED testを書く**

`backend/tests/unit/config/test_auth_settings.py`へ次を追加する。

- `AUTH_SESSION_TOUCH_INTERVAL_SECONDS`の既定値が300である。
- envから0を指定できる。
- `AUTH_SESSION_IDLE_TTL_SECONDS`を小さくした場合でも`AuthSettings()`の生成は失敗しない。
- `effective_session_touch_interval_seconds()`は、設定値がidle TTLの半分以上なら`idle_ttl // 2`へclampした値を返す。
- clampが発生した場合は起動時またはusecase初回利用時にwarning logを出す。

- [x] **Step 9.2: touch skipのRED testを書く**

`backend/tests/unit/usecases/test_auth_usecase.py`へ次を追加する。

- `auth_session.last_seen_at`から300秒未満のrequestでは`touch_session()`を呼ばず、元のsessionで`AuthenticatedSessionContext`を返す。
- 300秒以上経過したrequestでは`touch_session()`を呼ぶ。
- 設定値0では従来通り毎回touchする。
- inactive userの場合のsession revokeはtouch intervalに関係なく維持する。

- [x] **Step 9.3: settingとusecase分岐を実装する**

`AuthSettings`へ次を追加する。

```python
AUTH_SESSION_TOUCH_INTERVAL_SECONDS: int = 300
```

`AuthSettings`へ`effective_session_touch_interval_seconds()`を追加し、正のtouch intervalがidle TTLの半分以上なら`idle_ttl // 2`へclampする。`AuthUsecase.authenticate_session()`ではeffective intervalを使い、`now - auth_session.last_seen_at`がinterval未満なら`touch_session()`をskipする。intervalが0以下なら毎回touchする。clampが発生した場合は`AuthUsecase`のloggerでwarningを出す。

- [x] **Step 9.4: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/config/test_auth_settings.py tests/unit/usecases/test_auth_usecase.py tests/integration/test_auth_controller.py -q
```

Expected:

- 既存の`/api/auth/me` integration testが成功する。
- sessionが期限切れになる条件は既存通り維持される。

### Task 10: register email列挙方針を設定と文書で明確にする

**Review ID:** `P2-16`

**Files:**
- Modify: `backend/AGENTS.md`

- [x] **Step 10.1: 方針を確認する**

Run: なし。

Decision:

- Phase 2ではメール確認フローを実装しないため、email列挙を完全には隠さない。
- 409 statusを維持したままcode/messageだけgenericにしても、攻撃者には登録済みであることが分かるため、`AUTH_REVEAL_EMAIL_TAKEN`のような設定は追加しない。
- status/timing差まで隠す完全対策はemail verification、非同期招待制register、または「常に202で受付し、既存/新規をメール側だけで分岐する」設計のPhaseで扱う。

- [x] **Step 10.2: AGENTS.mdへ設計判断を書く**

`backend/AGENTS.md`へ次を明記する。

- このテンプレートはPhase 2時点ではregister成功時に即sessionを発行するため、duplicate emailを完全に秘匿しない。
- code/messageだけをgenericにする設定は追加しない。409 statusが残る限り列挙耐性にならないためである。
- 完全な列挙耐性が必要な派生プロジェクトでは、email verificationまたはinvite flowを設計し、register responseを非同期受付型へ変更する。

- [x] **Step 10.3: ドキュメント差分を確認する**

```bash
rtk rg -n "列挙|enumeration|duplicate|409" backend/AGENTS.md documents/plans/20260802-phase2-auth-security.md
rtk rg -n "AUTH_REVEAL_EMAIL_TAKEN" backend/app backend/.env.example backend/AGENTS.md
```

Expected:

- `AUTH_REVEAL_EMAIL_TAKEN`がapp設定、`.env.example`、`backend/AGENTS.md`に残っていない。
- duplicate emailの限界が`backend/AGENTS.md`に明記されている。

### Task 11: database engineの資格情報秘匿を補正する

**Review carry-over:** Phase 1 M-itemsからの認証セキュリティ補正

**Files:**
- Modify: `backend/app/libraries/database_engine.py`
- Modify: `backend/tests/unit/libraries/test_database_engine.py`
- Modify: `documents/plans/20260802-phase2-auth-security.md`

- [x] **Step 11.1: database URL parameter秘匿のRED testを書く**

`backend/tests/unit/libraries/test_database_engine.py`へ次を追加する。

- `build_engine_and_session_factory()`で作られるengineの`hide_parameters`が`True`である。

- [x] **Step 11.2: database engineを実装する**

`database_engine.py`:

- `engine_kwargs`に`"hide_parameters": True`を追加する。

- [x] **Step 11.3: targeted testsをGREENにする**

```bash
cd backend
rtk uv run pytest tests/unit/libraries/test_database_engine.py -q
```

Expected:

- DB parameter秘匿のtestが成功する。

### Task 12: ドキュメントと設定例をPhase 2仕様へ同期する

**Files:**
- Modify: `backend/AGENTS.md`
- Modify: `backend/.env.example`
- Modify: `documents/plans/20260802-phase2-auth-security.md`

- [x] **Step 12.1: `backend/AGENTS.md`を更新する**

追記する内容:

- 本番cookieは`AUTH_COOKIE_SECURE`未設定ならSecureになる。local HTTPだけ`.env`で`AUTH_COOKIE_SECURE=false`を明示する。
- proxy配下では`AUTH_TRUSTED_PROXY_IPS`へ信頼できる直近proxyのIP/CIDRだけを書く。任意のXFFは信じない。
- unsafe `/api` requestはCSRF middlewareが既定で検証する。新規unsafe endpointへ個別`Depends(require_csrf)`を書かない。
- routing前にCSRF middlewareが走るため、CSRFなしの`POST /api/unknown`は404ではなく403になる。これはunsafe API requestを先に拒否する意図的な契約である。
- CSRF除外pathを追加する場合は、なぜCSRFでなく別のstate検証で守られるのかを計画書に書く。
- password-only userとOAuth-only userを区別するため、`users.password_hash`はnullableである。password loginでは`None`を必ず認証不可にする。
- Argon2 hash/verifyは専用executorで実行し、`AUTH_PASSWORD_HASH_CONCURRENCY`で同時実行数を制限する。既定値4はArgon2 m=64MiBを前提に約256MiBまでを目安にする。worker数やmemory limitを見ずに上げない。
- password hash過負荷時は503ではなくqueue待ちによるレイテンシ増加として現れる。
- login/register失敗rate limitはIP、email+IP、email単独の3 bucketである。bucketへの記録は失敗時だけ行い、成功時にIP bucketを消してはいけない。
- register成功rate limitは`AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP`で別bucketとして扱う。
- `AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP` / `AUTH_RATE_LIMIT_ATTEMPTS_PER_IP`はPhase 2で削除され、`AUTH_RATE_LIMIT_FAILURES_*`へ改名される。既存`.env`の旧キーは`extra="ignore"`で無視されるため、移行時に必ず置き換える。
- register duplicate emailの扱いはPhase 2時点では完全秘匿ではない。
- `AuthSettings.ENVIRONMENT`は削除され、auth cookie securityには使わない。環境別docs制御は`Config.ENVIRONMENT`だけが担う。

- [x] **Step 12.2: `.env.example`を更新する**

追加/更新するキー:

```env
AUTH_COOKIE_SECURE=false
AUTH_TRUSTED_PROXY_IPS=
AUTH_PASSWORD_HASH_CONCURRENCY=4
AUTH_RATE_LIMIT_FAILURES_PER_EMAIL_IP=5
AUTH_RATE_LIMIT_FAILURES_PER_IP=20
AUTH_RATE_LIMIT_FAILURES_PER_EMAIL=20
AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP=10
AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS=3600
AUTH_SESSION_TOUCH_INTERVAL_SECONDS=300
AUTH_CSRF_EXEMPT_PATHS=
```

各キーにlocal/productionでの推奨コメントを付ける。

- [x] **Step 12.3: 計画書の進捗欄を更新する**

本計画の「進捗サマリー」「実行結果」「未対応事項」を更新する。

### Task 13: Phase 2結合回帰と品質ゲートを実行する

**Files:**
- Inspect: backend全体
- Inspect: frontend全体
- Modify: `documents/plans/20260802-phase2-auth-security.md`

- [x] **Step 13.1: backend unit testsを実行する**

```bash
cd backend
rtk uv run pytest tests/unit -q
```

Expected:

- unit testsがすべて成功する。

- [x] **Step 13.2: PostgreSQL付きintegration testsを実行する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-upgrade
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test rtk uv run pytest tests/integration -q
```

Expected:

- integration testsがすべて成功する。
- skipが0件である。

- [x] **Step 13.3: Alembic整合を確認する**

```bash
cd backend
ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test rtk uv run python manage.py db-check
```

Expected:

- pending schema changeなしで成功する。

- [x] **Step 13.4: backend formattingを実行し、checkする**

```bash
cd backend
rtk uv run isort .
rtk uv run yapf -ir app/ tests/ alembic/ manage.py
rtk uv run isort . --check-only
rtk uv run yapf -dr app/ tests/ alembic/ manage.py
```

Expected:

- isort/yapf checkがexit 0。
- Alembic generated migrationへ意図しないformat-only差分が出ていない。

- [x] **Step 13.5: manual smokeを実施する**

backendを起動する。

```bash
cd backend
rtk uv run python manage.py serve --host 127.0.0.1 --port 8000 &
SERVER_PID=$!
```

別terminalで確認する。

```bash
rtk curl -i http://127.0.0.1:8000/api/healthz
rtk curl -i http://127.0.0.1:8000/api/auth/me
rtk curl -i -X POST http://127.0.0.1:8000/api/auth/login
```

Expected:

- `/api/healthz`は200。
- 未認証`/api/auth/me`は401 error envelopeかつ`Cache-Control: no-store`。
- CSRFなし`POST /api/auth/login`は403 error envelope。

確認後、起動したserverを停止する。

```bash
kill "$SERVER_PID"
```

- [x] **Step 13.6: frontend品質ゲートを実行する**

Phase 2ではfrontend実装を変更しないが、root `AGENTS.md`の品質ゲートに従って確認する。

```bash
cd frontend
rtk npm run check
rtk npm test
rtk npm run build
```

Expected:

- `npm run check`が成功する。
- `npm test`が成功する。
- `npm run build`が成功する。

- [x] **Step 13.7: repository diffを確認する**

```bash
rtk git diff --check
rtk git status --short
```

Expected:

- whitespace errorがない。
- 変更ファイルがPhase 2範囲に収まっている。
- `git add`は実行しない。

## 進捗サマリー

- [x] Task 1: baselineとPhase 2境界を固定する
- [x] Task 2: naming conventionと`password_hash` nullable化を先に固定する
- [x] Task 3: Argon2 hash/verifyをthread化する
- [x] Task 4: trusted proxy対応のclient IP解決を導入する
- [x] Task 5: Secure cookieの既定値を安全側へ反転する
- [x] Task 6: rate limiterをinterface化し、失敗時記録へ変更する
- [x] Task 7: `SessionCsrfStatus`を導入し、三値boolを廃止する
- [x] Task 8: CSRF検証をmiddleware化し、route単位のオプトインを廃止する
- [x] Task 9: session touchを間引く
- [x] Task 10: register email列挙方針を設定と文書で明確にする
- [x] Task 11: database engineの資格情報秘匿を補正する
- [x] Task 12: ドキュメントと設定例をPhase 2仕様へ同期する
- [x] Task 13: Phase 2結合回帰と品質ゲートを実行する

## 完了条件

- [x] `SQLModel.metadata.naming_convention`が設定され、初期migrationのPK/FK名と一致している。
- [x] `users.password_hash`がmodel/migrationともにnullableである。
- [x] password loginで`password_hash is None`のユーザーは認証不可であり、dummy hash verifyによるtiming等化を維持している。
- [x] `PasswordHashExecutor`が専用executorでArgon2計算をevent loop外へ逃がし、`AUTH_PASSWORD_HASH_CONCURRENCY`で同時実行数を制限している。
- [x] password hash同時実行数を超えたrequestは即時503にならず、executor queueで待って完了する。
- [x] trusted proxy未設定時は`X-Forwarded-For`を無視する。
- [x] trusted proxy設定時だけ、XFF chainから正しいclient IPを採用する。
- [x] cookie Secureは`AUTH_COOKIE_SECURE`未設定時に`True`である。
- [x] local HTTPは`.env.example`の`AUTH_COOKIE_SECURE=false`で明示的にopt-outする。
- [x] `AuthSettings.ENVIRONMENT`が削除され、auth cookie secure判定が`ENVIRONMENT`へ依存していない。
- [x] integration test fixtureが`AUTH_COOKIE_SECURE=false`を明示している。
- [x] unsafe `/api` requestは純ASGI CSRF middlewareで既定検証される。
- [x] register/login/logout controllerからroute個別の`Depends(require_csrf)`が消えている。
- [x] `validate_session_csrf()`が`SessionCsrfStatus`を返し、`bool | None`や`is False`比較が残っていない。
- [x] rate limiterがIP、email+IP、email単独bucketを持つ。
- [x] login/registerの失敗時だけrate limit bucketへ記録される。
- [x] login成功時に該当email+IP bucketだけがresetされ、IP bucketとemail単独bucketは消えない。
- [x] register成功時は`AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP`で作成rateが制限される。
- [x] register成功rate limitは`AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS`の専用windowで評価される。
- [x] 旧`AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP` / `AUTH_RATE_LIMIT_ATTEMPTS_PER_IP`設定がapp設定と`.env.example`から消えている。
- [x] 認証済みrequestのsession touchが`AUTH_SESSION_TOUCH_INTERVAL_SECONDS`以内ではskipされる。
- [x] register duplicate emailの挙動と限界が`backend/AGENTS.md`に明記され、守れていない設定分岐を追加していない。
- [x] 401 error responseに`Cache-Control: no-store`が付く。
- [x] SQLAlchemy engineが`hide_parameters=True`で作成される。
- [x] backend unit testsが成功する。
- [x] PostgreSQL付きbackend integration testsがskip 0件で成功する。
- [x] `python manage.py db-check`がpending schema changeなしで成功する。
- [x] frontend `npm run check`、`npm test`、`npm run build`が成功する。
- [x] isort/yapf checkが成功する。
- [x] `git diff --check`がcleanである。
- [x] `git add`、`git commit`、`git push`を実行していない。

## 実行結果

実行中。完了した項目から順に記録する。

- 実行日時
  - 2026-08-02
- branch / HEAD
  - branch: `feature/db-auth`
  - HEAD: `9212ad9`
- 変更ファイル一覧
- DB schema変更方針へのユーザー確認結果
  - ユーザーから「Worktree は使わず、現在のブランチに変更を加えて良い。git add や git commit は禁止」と指示あり。
  - Phase 2計画に含まれる初期migration更新とtest DB検証の範囲で実装を進める。既存local開発DB `app` の破壊的再作成は行わない。
- targeted RED/GREEN結果
  - Task 2 targeted: `tests/unit/models/test_metadata.py tests/unit/models/test_auth_models.py tests/unit/services/test_auth_repository.py tests/unit/usecases/test_auth_usecase.py -q` は `15 passed`。
  - Task 2 migration consistency: `tests/integration/test_migration_consistency.py -q` は `1 passed, 1 warning`。
  - Task 3 targeted: `tests/unit/config/test_auth_settings.py tests/unit/libraries/test_password_hasher.py tests/unit/usecases/test_auth_usecase.py tests/unit/bootstrap/test_create_app.py tests/unit/bootstrap/test_container.py -q` は `27 passed, 1 warning`。
  - Task 4/5 targeted: DB指定付きで `tests/unit/config/test_auth_settings.py tests/unit/libraries/test_client_ip.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_controller_helpers.py tests/unit/bootstrap/test_container.py tests/unit/bootstrap/test_dependencies.py tests/unit/controllers/test_auth_controller_dependency.py tests/integration/test_auth_controller.py -q` は `73 passed, 4 warnings`。
  - Task 6 targeted: DB指定付きで `tests/unit/config/test_auth_settings.py tests/unit/libraries/test_auth_rate_limiter.py tests/unit/bootstrap/test_container.py tests/unit/usecases/test_auth_usecase.py tests/integration/test_auth_controller.py -q` は `57 passed, 4 warnings`。
  - Task 7 targeted: DB指定付きで `tests/unit/models/test_auth_csrf.py tests/unit/usecases/test_auth_usecase.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_controller_dependency.py tests/integration/test_auth_controller.py -q` は `55 passed, 4 warnings`。
  - Task 8 targeted: DB指定付きで `tests/unit/bootstrap/test_csrf_middleware.py tests/unit/bootstrap/test_error_handlers.py tests/unit/config/test_auth_settings.py tests/unit/controllers/test_auth_dependencies.py tests/unit/controllers/test_auth_controller_dependency.py tests/integration/test_auth_controller.py -q` は `71 passed, 4 warnings`。
  - Task 9 targeted: DB指定付きで `tests/unit/config/test_auth_settings.py tests/unit/usecases/test_auth_usecase.py tests/integration/test_auth_controller.py -q` は `54 passed, 4 warnings`。
  - Task 10 docs grep: `AUTH_REVEAL_EMAIL_TAKEN` は `backend/app`、`backend/.env.example`、`backend/AGENTS.md` で0件。duplicate emailの限界は `backend/AGENTS.md` に明記済み。
  - Task 11 targeted: `tests/unit/libraries/test_database_engine.py -q` は `2 passed`。
- backend unit test結果
  - `tests/unit -q`: `130 passed, 1 warning`
  - review fixes後: `tests/unit -q`: `147 passed, 1 warning`
- PostgreSQL付きbackend integration test結果とskip件数
  - baseline: `ALEMBIC_DATABASE_URL=postgresql://app:app@localhost:5432/app_test uv run python manage.py db-upgrade` 成功。
  - baseline: `TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest -q` は `126 passed, 4 warnings`。skip 0件。
  - final: `tests/integration -q` は `45 passed, 4 warnings`。skip 0件。
  - review fixes後: `tests/integration -q` は `45 passed, 4 warnings`。skip 0件。
- `db-check`結果
  - Task 2: `No new upgrade operations detected.`
  - Final: `No new upgrade operations detected.`
  - review fixes後: `No new upgrade operations detected.`
- formatting結果
  - `uv run isort .` 実行済み。
  - `uv run yapf -ir app/ tests/ alembic/ manage.py` 実行済み。
  - `uv run isort . --check-only`: 成功。
  - `uv run yapf -dr app/ tests/ alembic/ manage.py`: 成功。
- manual smoke結果
  - backend serverを `127.0.0.1:8000` で起動し確認後に停止済み。
  - `GET /api/healthz`: 200 `{"success":true,"message":"ok"}`
  - `GET /api/auth/me`: 401 error envelope、`Cache-Control: no-store`
  - `POST /api/auth/login` CSRFなし: 403 `CSRF_VALIDATION_FAILED`
  - `rtk curl` は接続結果を詳細表示できず code 7 になったため、デバッグ用途として raw `curl` で確認した。
- frontend品質ゲート結果
  - `npm run check`: 成功、全ファイル `unchanged`。
  - `npm test`: 7 files / 15 tests passed。
  - `npm run build`: 成功。`%VITE_SITE_URL%` 未定義 warning は既存の Vite build warning として表示。
- 未実行コマンドがある場合は理由
  - なし。

## 未対応事項

- `P0-4`: register UI。Phase 3で`P2-30`などのfrontend基盤後に扱う。
- `P1-17`、`P1-18`、`P1-19`: frontend auth guard/query key/global 401/403処理。Phase 3で扱う。
- `P2-2`: `auth_sessions.issued_at`追加。Phase 5またはDB改善Phaseで扱う。
- `P2-3`: IP address型のINET化。別migration設計が必要なためPhase 5へ残す。
- `P2-5`: repository not-found例外統一。Phase 5へ残す。
- `P2-7`: `DATABASE_URL` / `ALEMBIC_DATABASE_URL`統一。Phase 4またはPhase 5で扱う。
- `P2-10`: `expires_at` / audit `created_at` indexとsession pruning。Phase 5で扱う。
- `P2-20`: Config/AuthSettings全体の様式統一。Phase 4以降で扱う。
- `P2-23`: ruff/mypy/CI導入。Phase 4で扱う。
- `P2-25`: docker-compose開発体験改善。Phase 4で扱う。
- `P2-35` / `P3-8`: sample APIのREST化とCRUD模範実装化。Phase 4で扱う。
- `P3-12`: cookie helper統合と`__Host-` prefix。OAuth短命cookie設計と一緒に扱う。
- pre-session CSRF cookieの信頼境界強化。Phase 2ではsessionなしdouble-submitを現行通り許可する。`__Host-` prefix、cookie helper統合、OAuth state cookie設計と一緒に再検討する。
- `AUTH_CSRF_EXEMPT_PATHS`のprefix/regex対応。Phase 2では完全一致だけを扱う。将来`/api/auth/oauth/{provider}/callback`のようなpath parameter付きunsafe callbackを除外する場合は、prefixまたはroute pattern対応を設計する。
- CSRF middlewareと`require_current_session`のrequest-scoped auth context統合。Phase 2後は認証済みunsafe requestでmiddlewareとhandlerが別々にUoW transactionを開くため、将来のrequest-scoped cacheまたはauth context共有で`1 request 1 session`へ戻す。
- register email列挙の完全解消。email verificationまたはinvite flow導入時にresponse契約を再設計する。
- 405 error code名、`api_error`命名整理、UoW専用例外型などPhase 1レビューの非セキュリティ細部。Phase 4以降で扱う。
