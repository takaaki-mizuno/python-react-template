# Backend (FastAPI)

FastAPI ベースの Python バックエンド。Single source of truth は **ルートの `/AGENTS.md`** であり、本ファイルはその差分 (Backend 固有) を記述する。

## 技術スタック

- Python 3.12+
- パッケージ管理: **uv** (`uv.lock` を正)
- Web フレームワーク: FastAPI 0.128+
- ORM / モデル: SQLModel
- DI: Injector
- CLI: Typer (`manage.py`)
- 非同期 DB ドライバ: asyncpg (PostgreSQL)
- 設定: python-dotenv
- Lint / Format / Typecheck: ruff + isort + yapf + mypy

## ディレクトリ構成

```
backend/
├── manage.py                # Typer CLI エントリ
├── pyproject.toml           # 依存・ツール設定
├── uv.lock
├── app/
│   ├── bootstrap/           # アプリ起動・DI コンテナ初期化
│   ├── config/              # 環境変数 / 設定オブジェクト
│   ├── controllers/         # FastAPI ルータ (HTTP 層)
│   ├── interfaces/          # 抽象インターフェース (リポジトリ等)
│   ├── libraries/           # 横断的ユーティリティ
│   ├── models/              # SQLModel エンティティ
│   ├── services/            # 永続化・外部連携
│   └── usecases/            # ビジネスロジック (アプリケーション層)
└── static/                  # frontend ビルド成果物の配置先 (生成物)
```

レイヤ依存方向は **controllers → usecases → services / models** (一方向)。
controllers から services を直接呼ぶのは禁止 (テスト容易性のため usecases を経由)。

## 主要コマンド

```bash
# サーバ起動 (ENVIRONMENT=local/development では reload 既定有効)
python manage.py serve
python manage.py serve --host 0.0.0.0 --port 8000 --reload
python manage.py serve --host 0.0.0.0 --port 8000 --no-reload --workers 2 --log-level info

# 依存追加
uv add <package>
uv add --dev <package>     # 開発依存

# 同期 (lock からインストール)
uv sync

# Lint / Format
uv run ruff check .
uv run isort . --check-only
uv run yapf -dr app/ tests/ alembic/ manage.py
uv run mypy app manage.py

# テスト
uv run pytest tests/unit
TEST_DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/app_test uv run pytest tests/integration -q -ra
```

## コードスタイル

- import: isort のセクション順 (stdlib / 3rd party / local)
- フォーマット: yapf (設定は `pyproject.toml`)
- 型ヒント: 関数シグネチャに必須。`Any` は最終手段
- 命名: `snake_case` (関数/変数), `PascalCase` (クラス), `SCREAMING_SNAKE_CASE` (定数)

## 設定

- `AuthSettings`は`CoreModule`のproviderで一度だけ生成し、Injectorのsingletonとして共有する
- controllerは`Depends(get_auth_settings)` dependency経由で起動時snapshotを取得し、requestごとに`AuthSettings`を再生成しない
- `backend/.env`または認証関連環境変数を変更した場合は、backend process/containerを再起動する
- 設定hot reloadは提供しない。必要になった場合は全consumerを同時更新できる別設計として計画する

## モデル / DB

- 新規テーブル追加時はまず `documents/plans/` に ER 設計を残す
- スキーマ変更時はマイグレーション戦略を**事前にユーザー確認**
- sample CRUD のような user-owned resource は `sample_items` の実装をコピー元にする
- auth 領域の永続化は PostgreSQL を正とし、SQLite in-memory は auth の DB integration test には使わない
- auth migration の主要コマンドは `python manage.py db-upgrade` / `python manage.py db-downgrade`。manage.py 経由と bare `alembic` 経由のどちらも `DATABASE_URL` の明示設定を必須とし、既定値だけで DDL を実行しない
- Alembic revision 生成は `DATABASE_URL=postgresql+asyncpg://... python manage.py db-revision --message "... " --autogenerate --rev-id YYYYMMDD_NNNN` を使い、`DATABASE_URL` を明示する
- `db-revision --autogenerate` は DB が head であることを前提にする。生成後に timezone-aware column / expression index / JSONB / FK `ON DELETE` / server default を必ず手で確認する
- 初期 revision を書き換える場合、既存 DB に残る旧 PK/FK 名は Alembic autogenerate / `db-check` だけでは検出できない。正典確認は fresh test DB を作り直して初期 migration から適用し、`pg_constraint` または targeted test で制約名を確認する
- この template は未適用 migration chain を squash した単一の初期 schema revision を正とする。既存派生プロジェクトで適用済み revision を書き換える場合は、適用済み DB と未適用 DB の互換性を別計画で扱う

## API 設計

- REST 規約に従う。設計時は `.claude/skills/restful-api-design` を参照
- public API JSON は request / response とも camelCase を正とする。Pydantic `populate_by_name=True` は内部互換であり、docs や curl 例では camelCase だけを書く
- UseCase は HTTP response DTO を返さない。UseCase は domain model / domain result / domain error を返し、Controller が request DTO と response DTO へ変換する
- controller は `request.app.state.injector.get(...)` を直接呼ばず、`Depends` dependency で依存を受ける
- unsafe `/api` request は純 ASGI の CSRF middleware が既定で検証する。新規 unsafe endpoint に個別 `Depends(require_csrf)` を書かない
- routing 前に CSRF middleware が走るため、CSRF なしの `POST /api/unknown` は 404 ではなく 403 になる。これは unsafe API request を先に拒否する意図的な契約である
- CSRF 除外 path を `AUTH_CSRF_EXEMPT_PATHS` に追加する場合は、なぜ CSRF ではなく別の state 検証で守られるのかを計画書に書く
- auth の CSRF は cookie/header の timing-safe 比較に加え、session がある unsafe request では `auth_sessions.csrf_token_hash` と照合する
- auth の session 検証は `require_current_session` dependency から usecase へ委譲し、controller に DB session を持たせない
- auth controller / usecase / interface は `AuthenticatedSessionContext` を `app.models.auth_context` から import する
- HTTP error は error envelope で返す。新規 controller は `api_error()` または共通例外 handler を使う
- in-memory rate limiter は single-process の最小防御であり、複数 worker / 複数 instance の本番運用では共有 store へ置き換える
- login/register 失敗 rate limit は IP、email+IP、email 単独の 3 bucket で判定する。bucket への記録は失敗時だけ行い、成功時に IP bucket や email 単独 bucket を消してはいけない
- duplicate email など register 由来の失敗は、login の email 単独 bucket へ記録しない。register 409 だけで任意アカウントを email 単位にロックアウトできる経路を作らないためである
- rate limit 到達後の request は audit log INSERT を行わず即時に 429 へ変換する。通常の認証失敗は監査するが、block 後の連打で DB 書き込みを増幅させない
- register 成功 rate limit は `AUTH_RATE_LIMIT_REGISTRATIONS_PER_IP` と `AUTH_RATE_LIMIT_REGISTRATION_WINDOW_SECONDS` の別 bucket で扱う
- in-memory rate limiter は触った bucket だけを trim し、`AUTH_RATE_LIMIT_MAX_BUCKETS_PER_SCOPE` で scope ごとの bucket 数を bounded にする。上限到達時は active bucket を silent eviction せず、oldest bucket から expired bucket を必要な分だけ償却 reclaim する。expired 掃除後も満杯なら新規 bucket は作らず fail-open で warning を出す。request ごとの全 bucket 走査や shared overflow bucket を追加しない
- bucket 上限到達後の fail-open は全体封鎖を避けるための single-process 向けトレードオフであり、飽和中の新規キーは per-email 防御の追跡対象外になる。本番でこのリスクを許容できない場合は、Redis 等の共有 store または O(1) メモリの rate limiter へ置き換える
- `AUTH_RATE_LIMIT_ATTEMPTS_PER_EMAIL_IP` / `AUTH_RATE_LIMIT_ATTEMPTS_PER_IP` は Phase 2 で削除され、`AUTH_RATE_LIMIT_FAILURES_*` へ改名された。旧キーは `extra="ignore"` で無視されるため、既存 `.env` は必ず置き換える
- production では `/docs`、`/redoc`、`/openapi.json` を公開しない
- `Status` は healthz などの限定用途に使う。CRUD success response の模範にはしない

## Phase 5 認証永続化規約

- `DATABASE_URL` が DB 接続設定の正であり、Alembic もここから async URL を導出する。`ALEMBIC_DATABASE_URL` は使わない
- `users.is_active` は凍結・停止を表し、`users.deleted_at` は退会または論理削除を表す
- アプリケーション認可は code-managed RBAC を使う。role / permission catalog は `app/config/authorization.py` を正とし、DB には assignment table として `user_roles(id, user_id, role_code, assigned_at, assigned_by_user_id, created_at, updated_at)` だけを保存する。`user_roles` は `id UUID PK` と unique `(user_id, role_code)` を持つ。endpoint は role ではなく permission code で守り、`admin` role は `admin:access` permission を含む初期 role として扱う
- `GET /api/auth/me`、password login、register、OIDC login は `roles` / `permissions` を返す。public response は安定順に sort する
- `require_permission()` / `require_any_permission()` は Backend の認可境界である。Frontend の roles / permissions は表示制御と route guard 用であり、Backend の permission dependency を省略してはいけない
- `PUT /api/admin/users/{user_id}/roles` は unsafe `/api` request として CSRF middleware の対象にする。個別 CSRF dependency や CSRF exempt path は追加しない
- inactive user は role 管理 API / `authz-grant-role` CLI の対象に含める。deleted user は `USER_NOT_FOUND` として扱う
- `authz-sync` は存在しない。catalog 整合性は `authz-check-config`、DB 上の orphan role assignment は `authz-check-assignments` で確認する。retired role の orphan assignment 削除は `authz-prune-unknown-role-assignments --yes` を使い、rename では明示 remap migration/script を使う。初期 admin 付与や復旧は `authz-grant-role --email <email> --role admin` を使う
- 通常の active user query は必ず `deleted_at IS NULL` を含める。削除済み user を観測してよい lookup は `find_user_by_id_for_authentication()` のように用途名で明示する
- 削除済み user は login、`/api/auth/me`、session authentication で認証不可。session authentication で deleted / inactive user を観測した場合は、その user の全 active sessions を `revoke_sessions_for_user()` で revoke し、観測 request / session に対して専用 audit event を 1 件だけ残す。missing user は user id の正当性を保証できないため、従来どおり観測 session だけを revoke する
- `uq_users_email_lower_active` は `deleted_at IS NULL` の partial unique index であり、削除済み user の email は再登録可能。active user 同士の重複は DB が拒否する
- Phase 5 は公開 account deletion API を追加しない。`DELETE /api/auth/me`、退会 UI、削除後 email 保持/匿名化、本人確認再要求は Phase 6 で設計する
- physical delete 時は `auth_sessions.user_id` が CASCADE、`auth_audit_logs.user_id` / `session_id` が SET NULL になる
- DB の `created_at` / `updated_at` は全 table で `TIMESTAMPTZ` のログ・切り分け用 column とし、business logic の sort / retention / expiry / deletion 判定には使わない。business timestamp は `UnixTimestampMillis` / DB `BIGINT` で保存し、単位は Unix epoch からの経過ミリ秒である。DB comment には `Unix timestamp in milliseconds.` を必ず含める
- timestamp の source はアプリケーション clock に統一する。`created_at` / `updated_at` / business timestamp に DB server default や `updated_at` trigger は追加しない。boolean flag の server default はこの timestamp 方針とは別に扱う
- user / sample item の public API 互換名は DB column 名と一致しない場合がある。`createdAt` は `registered_at`、`updatedAt` は `modified_at`、`lastLoginAt` は `last_logged_in_at` から組み立てる。`modified_at` は profile / role / resource content の業務上の変更時刻であり、login activity では更新しない。login activity は `last_logged_in_at` だけを更新する
- user timestamp の使い分け: `registered_at` は登録時刻、`modified_at` は admin user fields / role assignment / logical deletion の変更時刻、`last_logged_in_at` は最終 login 時刻、`deleted_at` は logical deletion 時刻、`created_at` / `updated_at` は logging / troubleshooting 用。新しい user-owned resource でも public `updatedAt` が必要な場合は `updated_at` ではなく business timestamp の `modified_at` 相当を追加する
- `AuthSession.issued_at` は absolute TTL の起点、`created_at` は作成監査時刻。expiry 計算に `created_at` を使わない。OIDC reauth freshness は `auth_sessions.last_oidc_authenticated_at` と `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` で判定する
- auth session / audit log の `ip_address` は PostgreSQL `INET` を維持する意図的逸脱であり、Python model / repository boundary は `str | None` を保つ
- repository は domain error を投げ、HTTP error を投げない。`revoke_session()` は missing session を成功扱いにする冪等 command
- `mark_user_deleted()`、`revoke_sessions_for_user()`、`USER_MARKED_DELETED` は Phase 6 account deletion / role revocation / password change 用の契約である。`mark_user_deleted()` は `deleted_at IS NULL` の user を初めて削除状態にした場合だけ `USER_MARKED_DELETED` audit log を同じ repository 操作内で作成する。すでに削除済みの user では `deleted_at` を上書きせず、audit log も追加しない
- session cookie prefix は `AUTH_SESSION_COOKIE_PREFIX` だけで制御する。`__Host-` を使う場合は Secure、Path=/、Domain 未指定が必須。`AUTH_SESSION_COOKIE_PREFIX=__Host-` と `AUTH_COOKIE_SECURE=false` の組み合わせは settings validation で拒否する。CSRF cookie 名は frontend が読むため常に `csrf_token`
- `python manage.py db-prune-auth --audit-logs-before <ISO8601> --expired-sessions-before <ISO8601> --oidc-states-before <ISO8601>` で `occurred_at` が threshold より前の auth audit log、`expires_at` が threshold より前の session、期限切れ OIDC authorization state を削除する。複数指定時は audit log、expired session、OIDC authorization state の順に実行するが、それぞれ独立した repository 操作であり、ある commit 後に後続 operation が失敗した場合は部分成功になり得る
- audit log session retention: `auth_audit_logs.session_id` は `ON DELETE SET NULL` であり、session を物理削除しても audit log row は残るが `session_id` は `NULL` になる。audit 保持期間中に session id が必要な運用では session retention を audit log retention 以上にする。`NULL` を許容する運用では、削除済み session token の後続 replay は既知 session として監査できないことも受け入れる
- 派生プロジェクト向け互換性メモ: `AuthRepositoryInterface.delete_expired_sessions()` は実動作を明確にするため `delete_sessions_expired_before()` へ改名済み。外部から repository interface を直接呼んでいる場合は新名へ移行する
- known rejected session replay は bounded audit として扱う。`authenticate_session()` と `validate_session_csrf()` は既知だが active ではない session token を観測した場合、`SESSION_REJECTED` audit log を 5 分 window で aggregate し、`detail_json.replay_count`、`detail_json.last_replayed_at`、`detail_json.last_ip_address`、`detail_json.last_user_agent`、`detail_json.distinct_ip_count`、`detail_json.recent_ip_addresses` を更新する。repository は session id ごとの PostgreSQL `pg_try_advisory_xact_lock` を使い、lock 取得時だけ read-modify-write を行う。lock が busy の場合は CSRF middleware 経路で DB connection を待たせず、その replay 1 件の記録をスキップするため、強い正確性より availability を優先した契約である。このため `replay_count` は実 replay 数の下限値であり、並行 flood 時ほど過少になり得る。`distinct_ip_count` は capped な `recent_ip_addresses` 窓内での近似で、同じ IP が窓から落ちた後に再登場すると新規として数えるため過大側に振れ得る。raw `SESSION_REJECTED` row は aggregate anchor に流用せず、`detail_json.replay_count` を持つ row だけを更新する。window lookup は既存 `session_id` index から狭める前提で、template 規模では composite index を追加しない。in-memory throttle は複数 worker / instance で audit signal が割れるため採用しない。lock object id は UUID の下位 31 bit から作るため衝突確率は低いが、衝突時は busy lock と同じく記録を skip し得る best-effort audit である。unknown random token は audit log を作らない。deleted / inactive user の active session を初回に revoke する `SESSION_REVOKED_DELETED_USER` / `SESSION_REVOKED_INACTIVE_USER` はこの bounded replay では抑制しない

## Phase 6 Account Deletion 規約

- `DELETE /api/auth/me` が self-service account deletion の正規 endpoint。認証済み session と CSRF middleware validation を必須にする
- request body は camelCase の `confirmEmail` と optional `password`。`confirmEmail` は current user email と一致させるが、誤操作防止であり認証要素ではない。session hijack 耐性は CSRF middleware と cookie security に依存する
- password user (`users.password_hash IS NOT NULL`) は現在の password 再認証を要求する。OAuth-only user (`password_hash IS NULL`) は OAuth reauthentication 実装まで `confirmEmail` のみで削除を許可する
- OAuth-only user (`password_hash IS NULL`) の削除は OAuth provider reauthentication 実装まで `confirmEmail` のみで許可している。`confirmEmail` は認証要素ではないため、session と CSRF token の両方が奪取された場合は追加の本人確認なしに不可逆削除できる。顧客データ、課金、業務データを扱う派生プロジェクトでは、account deletion 公開前に OAuth reauthentication、削除猶予期間、または復元 workflow を設計する
- account deletion の password 再認証判定は既存 login rate limiter の IP bucket と email+IP bucket だけを読む。email 単独 bucket は任意 IP からの login 失敗でログイン済み正規ユーザーの退会を妨害できるため、退会再認証 429 の判定には使わない
- account deletion の password 再認証失敗は既存 login rate limiter の IP bucket と email+IP bucket に記録し、`ACCOUNT_DELETION_REAUTH_FAILED` audit log を current user / current session / request IP / user_agent 付きで残す
- 成功時は `users.deleted_at` を設定し、`users.is_active` は変更しない。対象 user の全 session を revoke し、所有する `sample_items` を削除する
- 成功時の `USER_MARKED_DELETED` audit log は `mark_user_deleted()` が最初の削除時だけ同じ repository 操作内で作成し、公開 account deletion 経由では current session id と request IP を残す。`mark_user_deleted()` の `session_id` / `ip_address` は省略不可の keyword-only argument とし、監査 context なしで呼ぶ場合も `None` を明示する
- 削除済み user の email は audit/history のため保持するが、`uq_users_email_lower_active` により同一 email の再登録は許可する。同一 email の再登録後は active email uniqueness conflict を解消しない限り旧 deleted user を復元できない
- user row の logical deletion と sample item の physical deletion は意図的に非対称である。user identity/audit history は保持し、sample content は保持要件がないため削除する
- 新しい user-owned resource を追加する場合は、resource 追加と同じ変更で `AccountDeletionUsecase` と `tests/unit/usecases/test_account_deletion_coverage.py` の両方を更新する
- `test_account_deletion_coverage.py` は SQLModel metadata に読み込まれた `users` への直接 FK table から cleanup 方針未決の user-owned table を検出する。間接所有、FK なしの `user_id` column、metadata に import されていない model は検出しないため、実際に削除されることは `test_account_deletion_usecase.py` と repository / integration tests で検証する

## Sample CRUD 複製手順

新しい user-owned CRUD resource は `/api/samples` をコピー元にする。標準ファイルは次の構成にする。

- `app/models/<resource>.py`: SQLModel table、domain dataclass、cursor が必要なら cursor model
- `app/models/<resource>_schemas.py`: request / response DTO。public JSON は camelCase
- `app/models/<resource>_errors.py`: domain errors
- `app/interfaces/services/<resource>_repository_interface.py`
- `app/services/<resource>_repository.py`: SQLModel と `UnitOfWorkInterface` を使う永続化実装
- `app/interfaces/usecases/<resource>_usecase_interface.py`
- `app/usecases/<resource>_usecase.py`: HTTP を知らない application logic
- `app/controllers/<resource>_controller.py`: auth context、request DTO、response DTO、error envelope 変換
- `alembic/versions/<revision>.py`: migration
- `tests/unit/models/`、`tests/unit/services/`、`tests/unit/usecases/`、`tests/unit/controllers/`、`tests/integration/`

`PATCH` は `exclude_unset=True` と `model_fields_set` を使い、省略と `null` 明示を区別する。empty body は no-op 200 として扱う。

## テスト

- Pytest を使用 (依存に未追加なら `uv add --dev pytest pytest-asyncio` から)
- pytest は `--import-mode=importlib` を既定にし、unit / integration に同名 test module があっても衝突しないようにする。衝突回避目的で `tests/**/__init__.py` を追加しない
- 単体テスト: `tests/unit/`、結合テスト: `tests/integration/` を推奨
- DB を使う integration test は実 PostgreSQL を使用し、DB の挙動をモックしない
- integration test は `TEST_DATABASE_URL` が指す PostgreSQL を使う。未設定なら skip ではなく fail する
- test 間 cleanup は存在する対象 table の `TRUNCATE ... CASCADE` で保証する
- Docker Compose backend は `backend-dev` target と anonymous `/app/backend/.venv` volume を使う。lock 更新後に container 依存が古い場合は `docker compose down -v` で dependency volume を作り直す。PostgreSQL の実データは `docker/postgres/data/` の bind mount を正とし、Docker named volume には置かない

## Phase 2 認証セキュリティ規約

- 本番 cookie は `AUTH_COOKIE_SECURE` 未設定なら Secure になる。local HTTP だけ `.env` で `AUTH_COOKIE_SECURE=false` を明示する。本番で `false` を使わない
- auth cookie の Secure 判定に `ENVIRONMENT` を使わない。docs 制御などの環境別挙動は `Config.ENVIRONMENT` だけが担う
- proxy 配下では `AUTH_TRUSTED_PROXY_IPS` に信頼できる直近 proxy の IP/CIDR だけを書く。不正値と `0.0.0.0/0` / `::/0` は起動時の settings validation で落とす。任意の `X-Forwarded-For` は信じず、XFF は右から走査し、不正 token に当たった場合は direct peer へ fallback する
- password-only user と OAuth-only user を区別するため、`users.password_hash` は nullable である。password login では `None` を必ず認証不可にし、dummy hash verify で timing 差を広げない
- Argon2 hash/verify は専用 `PasswordHashExecutor` で実行し、`AUTH_PASSWORD_HASH_CONCURRENCY` で同時実行数を制限する。既定値 4 は Argon2 m=64MiB を前提に約 256MiB までを目安にする。worker 数や memory limit を見ずに上げない
- password hash 過負荷時は 503 ではなく executor queue 待ちによるレイテンシ増加として現れる
- 認証済み request の session touch は `AUTH_SESSION_TOUCH_INTERVAL_SECONDS` で間引く。設定値が idle TTL に対して長すぎる場合は実効値を `AUTH_SESSION_IDLE_TTL_SECONDS // 2` に clamp する
- Phase 2 時点では register 成功時に即 session を発行するため、duplicate email を完全には秘匿しない。409 status が残る限り、code/message だけを generic にしても列挙耐性にならないため、その設定分岐は追加しない
- 完全な register email 列挙耐性が必要な派生プロジェクトでは、email verification または invite flow を設計し、register response を非同期受付型へ変更する

## Phase 1 基盤規約

- transaction 境界は `UnitOfWorkInterface` に置く。repository に `transaction()` を追加しない
- nested `UnitOfWorkInterface.transaction()` は savepoint ではなく外側 transaction へ join する
- 別 instance の `UnitOfWorkInterface.transaction()` / `session_scope()` を同一 async context の transaction 内で開くことは禁止。実装は fail fast する
- 1つの UoW transaction session を `asyncio.gather()` / `create_task()` で並行利用しない
- `AuthSettings.ENVIRONMENT` は Phase 2 で削除された。auth cookie security には環境名を使わない
- local 開発で docs を見たい場合は、`backend/.env.example` を元に `backend/.env` を作り、`ENVIRONMENT=local` を明示する
- production Dockerfile の `CMD` は `manage.py serve --no-reload` を明示する

## 関連スキル

- `python-development` — Python 全般
- `database-schema-design` — モデル設計
- `restful-api-design` — API 設計

## Phase 8 OAuth/OIDC 規約

- OAuth/OIDC provider は `AUTH_OIDC_ENABLED_PROVIDERS` と provider id 別 env で追加する。provider id は小文字英数字、`-`、`_` のみを許可し、provider 固有の env suffix は大文字化して使う。JSON を単一 env に詰め込まない。
- Redirect URI は `AUTH_OIDC_REDIRECT_BASE_URL` と provider の callback path からだけ生成する。request の `Host`、`X-Forwarded-*`、`base_url` を redirect URI 生成に使わない。IdP には例として `http://localhost:8000/api/auth/oidc/google/callback` または本番 origin の同 path を登録する。
- `trusted verified email` は `AUTH_OIDC_PROVIDER_<ID>_TRUST_VERIFIED_EMAIL=true` の provider だけで信頼する。`email_verified=true` かつ trusted provider の場合だけ自動作成・自動 link の候補にする。
- 新規 OAuth user 作成は `AUTH_OIDC_PROVIDER_<ID>_AUTO_PROVISION=enabled | link-only` で切り替える。`link-only` は既存 user への link だけを許可し、新規 user を作らない。
- 既存 user への link は `AUTH_OIDC_PROVIDER_<ID>_LINK_MODE=auto | manual | disabled` で制御する。`auto` のみ verified email 一致で自動 link する。`manual` は今回の実装では `OIDC_IDENTITY_LINK_REQUIRED` で拒否し、明示 link UI は後続計画で扱う。
- 自動作成・自動 link・login success/failure・reauth success/failure は audit event に残す。ただし provider subject、authorization code、`access_token`、`refresh_token`、raw provider error は audit に残さない。
- token 非保存を正とする。`access_token` / `refresh_token` は DB、audit log、URL、frontend state に保存しない。保存するのは provider subject と allowlist 済み ID token claims だけである。
- ID token の署名 alg は安全 allowlist と discovery metadata の積集合だけを許可する。`none` と HS* は無条件で拒否する。JWKS は未知 `kid` の場合だけ cooldown 付きで再取得し、署名不正だけで外向き HTTP を増幅させない。
- OAuth/OIDC state は DB-backed にし、browser binding cookie と組み合わせて callback を検証する。browser binding cookie は `oidc_binding_<state_lookup_id>`、`HttpOnly`、`SameSite=Lax`、auth cookie と同じ Secure 判定、state TTL と同じ max-age を使い、callback consume 後または terminal failure 後に削除する。
- `purpose=login` callback は成功時に保存済み internal redirect path へ戻し、失敗時は `/login?oidcError=<machine-code>` へ戻す。`purpose=account_deletion_reauth` は成功時に `oidcReauth=success`、失敗時に `oidcError=<machine-code>` を保存済み settings path に merge する。
- OIDC redirect query code の対応表は以下を正典とする。`OIDC_PROVIDER_ACCESS_DENIED` は IdP 同意画面のキャンセル等の terminal failure、`OIDC_IDENTITY_UNAVAILABLE` は provider subject または email collision が inactive / deleted user を指す場合に使う。`OIDC_IDENTITY_LINK_DISABLED` と `OIDC_PROVISIONING_DISABLED` は email 登録有無で出し分けられるため、password register の 409 と同じ enumeration 許容範囲として扱う。

| domain error | redirect query code | login redirect | reauth redirect | audit event |
|---|---|---|---|---|
| `OidcProviderNotConfiguredError` | `OIDC_PROVIDER_NOT_CONFIGURED` | `/login` | `/app/settings` | なし |
| `OidcAuthorizationRateLimitedError` | `OIDC_AUTHORIZATION_RATE_LIMITED` | `/login` | `/app/settings` | なし |
| `OidcStateMismatchError` | `OIDC_STATE_MISMATCH` | `/login` | state context を解決できない場合は `/login` | なし |
| `OidcBrowserBindingMismatchError` | `OIDC_BROWSER_BINDING_MISMATCH` | `/login` | state context を解決できない場合は `/login` | なし |
| `OidcTokenExchangeError` | `OIDC_TOKEN_EXCHANGE_FAILED` | `/login` | saved settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcProviderAccessDeniedError` | `OIDC_PROVIDER_ACCESS_DENIED` | `/login` | state context を解決できる場合は保存済み settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcClaimsValidationError` | `OIDC_CLAIMS_VALIDATION_FAILED` | `/login` | saved settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcEmailNotVerifiedError` | `OIDC_EMAIL_NOT_VERIFIED` | `/login` | saved settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcProvisioningDisabledError` | `OIDC_PROVISIONING_DISABLED` | `/login` | saved settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcIdentityLinkRequiredError` | `OIDC_IDENTITY_LINK_REQUIRED` | `/login` | saved settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcIdentityLinkDisabledError` | `OIDC_IDENTITY_LINK_DISABLED` | `/login` | saved settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcIdentityUnavailableError` | `OIDC_IDENTITY_UNAVAILABLE` | `/login` | saved settings path | `OIDC_LOGIN_FAILED` / `OIDC_REAUTH_FAILED` |
| `OidcReauthAuthenticationRequiredError` | `OIDC_REAUTH_AUTHENTICATION_REQUIRED` | `/login` | `/login` | なし |
| `OidcReauthSubjectMismatchError` | `OIDC_REAUTH_SUBJECT_MISMATCH` | `/login` | saved settings path | `OIDC_REAUTH_FAILED` |
| `OidcReauthAuthTimeRequiredError` | `OIDC_REAUTH_AUTH_TIME_REQUIRED` | `/login` | saved settings path | `OIDC_REAUTH_FAILED` |
| `OidcReauthStaleError` | `OIDC_REAUTH_STALE` | `/login` | saved settings path | `OIDC_REAUTH_FAILED` |
| `OidcProviderUnavailableError` | `OIDC_PROVIDER_UNAVAILABLE` | `/login` | start は `/app/settings`、callback は保存済み settings path | start はなし / callback は failure audit |
| `OidcProviderMetadataError` | `OIDC_PROVIDER_METADATA_INVALID` | `/login` | start は `/app/settings`、callback は保存済み settings path | start はなし / callback は failure audit |
| unknown exception | `OIDC_UNEXPECTED_ERROR` | `/login` | callback context があれば保存済み settings path | `logger.exception`; valid state context 後だけ failure audit |

- OIDC authorization start は `AUTH_OIDC_AUTHORIZATION_STARTS_PER_IP` で rate limit する。rate limit で拒否された request は state row を作らず、callback failure audit も作らない。
- OIDC state pruning は `db-prune-auth --oidc-states-before <ISO8601>` で明示実行する。保持期間 env は用意しないため、運用ジョブ側で閾値を決める。
- OAuth-only account deletion は `auth_sessions.last_oidc_authenticated_at` と `AUTH_OIDC_REAUTH_FRESHNESS_SECONDS` で判定する。削除 reauth flow は `prompt=login` / `max_age=0` を送り、provider `auth_time` が missing、stale、future leeway 超過の場合は fresh とみなさない。
- `auth_time` 非対応 IdP では OAuth-only self-service deletion は通さない。Backend は `ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` を返し、linked providers が空の場合は frontend が support/admin deletion message を表示する。
- Account deletion 成功時は `auth_identities` を同一 transaction で物理削除する。削除済み user が provider subject unique index を占有し、同じ provider subject で再登録できなくなることを避ける。
- `api_error()` は既存呼び出し互換を保ったまま optional `details` を扱う。`ACCOUNT_DELETION_OIDC_REAUTH_REQUIRED` の `error.details` には linked providers の public metadata (`providerId`, `displayName`) だけを含める。
- OIDC failure audit は bounded にする。有効な未消費 state に到達した通常 failure だけ `OIDC_LOGIN_FAILED` または `OIDC_REAUTH_FAILED` を 1 件記録し、invalid / replayed / rate-limited callback では audit insert を増幅させない。
